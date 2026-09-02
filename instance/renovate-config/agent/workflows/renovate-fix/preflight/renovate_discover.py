"""Renovate PR discovery helpers for renovate-fix workflow preflight."""

from __future__ import annotations

import json
import re
import subprocess
import sys

from gh_pr_status import classify_gh, gh_pr

TASK_KEY_PREFIX = "renovate-fix:"
VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
FROM_TO_RE = re.compile(
    r"from\s+v?(\d+)\.(\d+)\.(\d+)\s+to\s+v?(\d+)\.(\d+)\.(\d+)",
    re.IGNORECASE,
)
RENOVATE_TABLE_RE = re.compile(
    r"`?(\d+)\.(\d+)\.(\d+)`?\s*(?:→|->)\s*`?(\d+)\.(\d+)\.(\d+)`?",
)


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
    return lowered in ("renovate[bot]", "renovate") or "renovate" in lowered


def label_names(labels: list) -> set[str]:
    """Normalize PR label objects or strings to lowercase names."""
    names: set[str] = set()
    for label in labels or []:
        if isinstance(label, dict):
            names.add(str(label.get("name", "")).lower())
        else:
            names.add(str(label).lower())
    return names - {""}


def _compare_versions(old: tuple[int, int, int], new: tuple[int, int, int]) -> str | None:
    if new[0] > old[0]:
        return "major"
    if new[1] > old[1]:
        return "minor"
    if new[2] > old[2]:
        return "patch"
    return None


def _bump_from_version_pair(old: tuple[int, int, int], new: tuple[int, int, int]) -> str | None:
    return _compare_versions(old, new)


def parse_semver_bump_from_text(text: str) -> str | None:
    """Infer major/minor/patch from version pairs in text."""
    if not text:
        return None

    match = FROM_TO_RE.search(text)
    if match:
        old = tuple(int(x) for x in match.group(1, 2, 3))
        new = tuple(int(x) for x in match.group(4, 5, 6))
        return _bump_from_version_pair(old, new)

    match = RENOVATE_TABLE_RE.search(text)
    if match:
        old = tuple(int(x) for x in match.group(1, 2, 3))
        new = tuple(int(x) for x in match.group(4, 5, 6))
        return _bump_from_version_pair(old, new)

    matches = VERSION_RE.findall(text)
    if len(matches) < 2:
        return None
    old = tuple(int(x) for x in matches[0])
    new = tuple(int(x) for x in matches[-1])
    return _bump_from_version_pair(old, new)


def classify_bump(labels: list, title: str = "", body: str = "") -> str:
    """Classify semver bump tier. Unknown defaults to major (safe — comment only)."""
    names = label_names(labels)
    if "major" in names:
        return "major"
    if "minor" in names:
        return "minor"
    if "patch" in names:
        return "patch"
    for text in (body, title):
        parsed = parse_semver_bump_from_text(text)
        if parsed:
            return parsed
    return "major"


def has_actionable_issues(issues: list[str]) -> bool:
    """True if PR has CI failures or merge conflicts."""
    if not issues:
        return False
    if "conflict" in issues:
        return True
    return any(i.startswith("ci_fail") for i in issues)


def is_draft(pr: dict) -> bool:
    return bool(pr.get("isDraft"))


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
                "number,title,labels,url,headRefName,isDraft,author,body",
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
    """Fetch CI state and bump classification for a Renovate PR."""
    number = pr.get("number")
    if not number:
        return None
    data = gh_pr(upstream, number)
    if not data:
        return None
    _, issues = classify_gh(data)
    if not has_actionable_issues(issues):
        return None
    bump = classify_bump(pr.get("labels") or [], pr.get("title", ""), pr.get("body", ""))
    issue_str = ",".join(issues) if issues else "clean"
    return {
        "repo_key": repo_key,
        "upstream": upstream,
        "number": number,
        "title": pr.get("title", ""),
        "url": pr.get("url", ""),
        "head_ref": pr.get("headRefName", ""),
        "bump_type": bump,
        "issues": issues,
        "issue_str": issue_str,
        "task_key": task_key(repo_key, number),
    }


def tracked_renovate_keys(tasks: list[dict]) -> set[str]:
    """Return external_keys for active Renovate tasks."""
    keys: set[str] = set()
    for task in tasks:
        key = task.get("external_key", "")
        if key.startswith(TASK_KEY_PREFIX):
            keys.add(key)
    return keys


def format_pr_line(entry: dict) -> str:
    upstream = entry["upstream"]
    num = entry["number"]
    lines = [
        f"  PR {upstream}#{num} [{entry['issue_str']}] bump={entry['bump_type']}",
        f"  title: {entry['title']}",
        f"  head_ref: {entry['head_ref']}",
        f"  task_key: {entry['task_key']}",
        f"  url: {entry['url']}",
    ]
    return "\n".join(lines)


def discover_failing_renovate_prs(repos: dict, tasks: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Discover failing Renovate PRs bucketed by major vs auto-fix vs already tracked.

    Returns (major_entries, auto_fix_entries, tracked_entries).
    """
    from common import upstream_repo

    tracked = tracked_renovate_keys(tasks)
    major: list[dict] = []
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
                continue
            if entry["bump_type"] == "major":
                major.append(entry)
            else:
                auto_fix.append(entry)

    return major, auto_fix, already_tracked
