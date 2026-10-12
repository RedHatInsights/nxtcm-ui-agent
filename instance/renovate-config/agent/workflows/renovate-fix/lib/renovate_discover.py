"""Renovate PR discovery helpers for renovate-fix workflow preflight."""

from __future__ import annotations

import json
import subprocess
import sys

from gh_pr_status import classify_gh, gh_pr

TASK_KEY_PREFIX = "renovate-fix:"


def task_key(repo_key: str, pr_number: int) -> str:
    """Build deterministic external_key for a Renovate PR task."""
    return f"{TASK_KEY_PREFIX}{repo_key}#{pr_number}"


def is_renovate_author(login: str) -> bool:
    """Return True if the GitHub login belongs to Renovate."""
    if not login:
        return False
    lowered = login.lower()
    return lowered in ("renovate[bot]", "renovate", "app/renovate")


def has_actionable_issues(issues: list[str]) -> bool:
    """True if PR has CI failures with no outstanding merge conflict.

    Conflict-only PRs are skipped — Renovate rebases on its own.
    PRs with conflict + CI failure are also skipped — CI cannot be fixed
    on a conflicted branch (conflict markers look like TS errors, lockfile
    may be corrupt). Wait for Renovate to rebase; CI failures re-surface
    cleanly on the next preflight cycle.
    """
    if not issues:
        return False
    if "conflict" in issues:
        return False
    return any(i.startswith("ci_fail") for i in issues)


def is_draft(pr: dict) -> bool:
    return bool(pr.get("isDraft"))


def _head_owner_repo(pr: dict) -> tuple[str, str]:
    """Extract head repository owner/name from gh PR JSON fields."""
    owner_obj = pr.get("headRepositoryOwner") or {}
    owner = owner_obj.get("login") or ""
    repo_obj = pr.get("headRepository") or {}
    name = repo_obj.get("name") or ""
    return owner, name


def list_open_prs(upstream: str) -> list[dict]:
    """List open PRs on upstream repo via gh CLI."""
    try:
        proc = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                upstream,
                "--state",
                "open",
                "--limit",
                "100",
                "--json",
                "number,title,url,headRefName,isDraft,author,"
                "headRepository,headRepositoryOwner,isCrossRepository",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            print(f"ERR gh pr list {upstream}: {proc.stderr.strip()}", file=sys.stderr)
            return []
        return json.loads(proc.stdout or "[]")
    except Exception as exc:
        print(f"ERR gh pr list {upstream}: {exc}", file=sys.stderr)
        return []


def filter_renovate_prs(prs: list[dict]) -> list[dict]:
    """Keep only open Renovate-authored PRs."""
    result = []
    for pr in prs:
        if is_draft(pr):
            continue
        author = (pr.get("author") or {}).get("login", "")
        if is_renovate_author(author):
            result.append(pr)
    return result


def enrich_renovate_pr(upstream: str, repo_key: str, pr: dict) -> dict | None:
    """Fetch CI state for a Renovate PR; return None if not actionable."""
    number = pr.get("number")
    if not number:
        return None
    data = gh_pr(upstream, number)
    if not data:
        return None
    _, issues = classify_gh(data)
    if not has_actionable_issues(issues):
        return None
    issue_str = ",".join(issues) if issues else "clean"
    head_owner, head_repo = _head_owner_repo(pr)
    return {
        "repo_key": repo_key,
        "upstream": upstream,
        "number": number,
        "title": pr.get("title", ""),
        "url": pr.get("url", ""),
        "head_ref": pr.get("headRefName", ""),
        "head_owner": head_owner,
        "head_repo": head_repo,
        "is_cross_repository": bool(pr.get("isCrossRepository")),
        "issues": issues,
        "issue_str": issue_str,
        "task_key": task_key(repo_key, number),
    }


# Statuses surfaced by gh_pr_status.main(). Tasks in these statuses are handled
# by Script 02 and should NOT re-enter the Script 01 AUTO-FIX queue.
_ACTIVE_STATUSES = frozenset({"in_progress", "pr_open", "pr_changes"})


def _is_auto_retryable(task: dict) -> bool:
    """Return True if a paused task should re-enter AUTO-FIX for a retry.

    paused_reason prefixes:
      "transient:*" — network/registry error, safe to retry automatically.
      "blocked:*"   — structural failure (peer dep, unfixable API); wait for
                      human action. Do NOT re-queue.
    Tasks with no paused_reason prefix default to retryable for backwards compat.
    """
    reason = task.get("paused_reason") or ""
    if reason.startswith("blocked:"):
        return False
    return True


def tracked_renovate_keys(tasks: list[dict]) -> set[str]:
    """Return external_keys of tasks that Script 02 (GH PR Status) already covers.

    Active tasks (in_progress / pr_open / pr_changes) are enriched by Script 02
    and must not appear in AUTO-FIX.

    Paused tasks with a transient failure reason re-enter AUTO-FIX for automatic
    retry. Paused tasks with a structural (blocked:*) failure reason are waiting
    for human action and must also stay out of AUTO-FIX to avoid retry spam.
    """
    keys: set[str] = set()
    for task in tasks:
        status = task.get("status")
        key = task.get("external_key", "")
        if not key.startswith(TASK_KEY_PREFIX):
            continue
        if status in _ACTIVE_STATUSES:
            keys.add(key)
        elif status == "paused" and not _is_auto_retryable(task):
            # Blocked paused task — keep it out of AUTO-FIX; human must act.
            keys.add(key)
    return keys


def format_pr_line(entry: dict) -> str:
    upstream = entry["upstream"]
    num = entry["number"]
    head_owner = entry.get("head_owner", "")
    head_repo = entry.get("head_repo", "")
    existing_status = entry.get("existing_status")
    existing_reason = entry.get("existing_paused_reason", "")
    if existing_status:
        status_note = f" resume:{existing_status}"
        if existing_reason:
            status_note += f" ({existing_reason})"
    else:
        status_note = " new"
    lines = [
        f"  PR {upstream}#{num} [{entry['issue_str']}]{status_note}",
        f"  title: {entry['title']}",
        f"  head_ref: {entry['head_ref']}",
        f"  head_owner: {head_owner or '(resolve via gh pr view)'}",
        f"  head_repo: {head_repo or '(resolve via gh pr view)'}",
        f"  is_cross_repository: {entry.get('is_cross_repository', False)}",
        f"  task_key: {entry['task_key']}",
        f"  url: {entry['url']}",
    ]
    return "\n".join(lines)


def _task_status_map(tasks: list[dict]) -> dict[str, dict]:
    """Return {external_key: {status, paused_reason}} for all Renovate tasks."""
    result = {}
    for task in tasks:
        key = task.get("external_key", "")
        if not key.startswith(TASK_KEY_PREFIX):
            continue
        status = task.get("status")
        if not status:
            continue
        result[key] = {
            "status": status,
            "paused_reason": task.get("paused_reason") or "",
        }
    return result


def discover_failing_renovate_prs(repos: dict, tasks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Discover failing Renovate PRs for auto-fix vs already tracked.

    Returns (auto_fix_entries, tracked_entries). Only PRs with CI failures
    and no outstanding merge conflict are eligible for auto-fix. Conflicted
    PRs (with or without CI failures) are excluded — Renovate rebases them;
    the CI-only failure will surface on the next preflight cycle.

    auto_fix entries include an `existing_status` field (e.g. "paused") when a
    task already exists but is not active — so the agent knows to resume via
    task_update rather than creating a duplicate with task_add.
    """
    from common import upstream_repo

    tracked = tracked_renovate_keys(tasks)
    all_statuses = _task_status_map(tasks)
    auto_fix: list[dict] = []
    already_tracked: list[dict] = []

    for repo_key in repos:
        upstream, host = upstream_repo(repo_key)
        if not upstream or host != "github":
            continue

        for pr in filter_renovate_prs(list_open_prs(upstream)):
            entry = enrich_renovate_pr(upstream, repo_key, pr)
            if not entry:
                continue
            if entry["task_key"] in tracked:
                already_tracked.append(entry)
            else:
                # Carry existing status/reason so agent can resume instead of re-adding.
                existing = all_statuses.get(entry["task_key"])
                if existing:
                    entry["existing_status"] = existing["status"]
                    if existing["paused_reason"]:
                        entry["existing_paused_reason"] = existing["paused_reason"]
                auto_fix.append(entry)

    return auto_fix, already_tracked
