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


def parse_task_key(external_key: str) -> tuple[str, int] | None:
    """Parse renovate-fix:repo-key#N into (repo_key, pr_number)."""
    if not external_key.startswith(TASK_KEY_PREFIX):
        return None
    rest = external_key[len(TASK_KEY_PREFIX) :]
    if "#" not in rest:
        return None
    repo_key, num_str = rest.rsplit("#", 1)
    try:
        return repo_key, int(num_str)
    except ValueError:
        return None


def is_renovate_author(login: str) -> bool:
    """Return True if the GitHub login belongs to Renovate."""
    if not login:
        return False
    lowered = login.lower()
    return lowered in ("renovate[bot]", "renovate")


def has_actionable_issues(issues: list[str]) -> bool:
    """True if PR has CI failures or merge conflicts."""
    if not issues:
        return False
    if "conflict" in issues:
        return True
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


def tracked_renovate_keys(tasks: list[dict]) -> set[str]:
    """Return external_keys for Renovate tasks (any non-archived status)."""
    keys: set[str] = set()
    for task in tasks:
        key = task.get("external_key", "")
        if key.startswith(TASK_KEY_PREFIX):
            keys.add(key)
    return keys


def format_pr_line(entry: dict) -> str:
    upstream = entry["upstream"]
    num = entry["number"]
    head = f"{entry.get('head_owner', '')}/{entry.get('head_repo', '')}".strip("/")
    lines = [
        f"  PR {upstream}#{num} [{entry['issue_str']}]",
        f"  title: {entry['title']}",
        f"  head_ref: {entry['head_ref']}",
        f"  head_repo: {head or '(resolve via gh pr view)'}",
        f"  task_key: {entry['task_key']}",
        f"  url: {entry['url']}",
    ]
    return "\n".join(lines)


def discover_failing_renovate_prs(repos: dict, tasks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Discover failing Renovate PRs for auto-fix vs already tracked.

    Returns (auto_fix_entries, tracked_entries). Any Renovate PR with CI
    failures or conflicts is eligible for auto-fix.
    """
    from common import upstream_repo

    tracked = tracked_renovate_keys(tasks)
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
                auto_fix.append(entry)

    return auto_fix, already_tracked
