"""Include human feedback from the bot's fix PR in renovate-fix preflight.

Tasks track the Renovate PR in ``metadata.prs`` and the bot-opened fix PR in
``metadata.fix_pr``. This module appends those comments (and review bodies) onto
the enriched task without folding the fix PR's CI/merge state into the task.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_GH_PR_URL = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", re.IGNORECASE)

# Match shared classify_gh: empty-body CHANGES_REQUESTED is still actionable.
_ACTIONABLE_EMPTY_REVIEW_STATES = frozenset({"CHANGES_REQUESTED"})


def resolve_fix_pr(
    fix_pr: dict | None,
    *,
    upstream_repo: Callable[[str], tuple[str, str]] | None = None,
) -> tuple[str, int] | None:
    """Return ``(owner/repo, number)`` for the fix PR.

    Prefers the GitHub URL when present (always ``owner/repo``). Falls back to
    structured ``repo`` + ``number``, resolving bare repo keys via
    ``upstream_repo`` the same way shared ``enrich_gh`` does.
    """
    if not fix_pr:
        return None

    url = fix_pr.get("url") or ""
    match = _GH_PR_URL.search(url)
    if match:
        return match.group(1), int(match.group(2))

    repo = fix_pr.get("repo")
    number = fix_pr.get("number")
    if not repo or number is None:
        return None
    try:
        num = int(number)
    except (TypeError, ValueError):
        return None

    repo_s = str(repo)
    if upstream_repo is not None:
        up, _host = upstream_repo(repo_s)
        if up:
            return up, num
        return None
    if "/" in repo_s:
        return repo_s, num
    return None


def _already_tracked(enriched: dict, owner_repo: str, number: int) -> bool:
    """True if this PR is already in enriched['prs'] (avoid duplicate fetch)."""
    for pr in enriched.get("prs") or []:
        if int(pr.get("num") or 0) != number:
            continue
        repo = str(pr.get("repo") or "")
        if repo == owner_repo or repo.endswith(f"/{owner_repo}") or owner_repo.endswith(f"/{repo}"):
            return True
    return False


def collect_fix_pr_comments(
    fix_pr: dict | None,
    *,
    gh_pr_comments: Callable[[str, int], list[dict]],
    gh_pr: Callable[[str, int], dict | None],
    skip_if_tracked: dict | None = None,
    upstream_repo: Callable[[str], tuple[str, str]] | None = None,
) -> list[dict]:
    """Fetch issue/review comments from the fix PR, tagged for the agent."""
    resolved = resolve_fix_pr(fix_pr, upstream_repo=upstream_repo)
    if not resolved:
        return []
    owner_repo, number = resolved
    if skip_if_tracked is not None and _already_tracked(skip_if_tracked, owner_repo, number):
        return []

    comments: list[dict] = []
    for c in gh_pr_comments(owner_repo, number) or []:
        body = c.get("b", "")
        comments.append({**c, "b": f"[fix PR #{number}] {body}"})

    data = gh_pr(owner_repo, number)
    if data:
        for rv in data.get("reviews") or []:
            rstate = rv.get("state", "")
            body = (rv.get("body") or "").strip()
            if not body and rstate not in _ACTIONABLE_EMPTY_REVIEW_STATES:
                continue
            display = body if body else "(no review summary)"
            comments.append(
                {
                    "a": (rv.get("author") or {}).get("login", "?"),
                    "t": (rv.get("submittedAt") or "")[:16],
                    "b": f"[fix PR #{number}] [REVIEW {rstate or '?'}] {display}",
                }
            )
    return comments


def append_fix_pr_feedback(
    enriched: dict | None,
    *,
    gh_pr_comments: Callable[[str, int], list[dict]],
    gh_pr: Callable[[str, int], dict | None],
    upstream_repo: Callable[[str], tuple[str, str]] | None = None,
) -> dict | None:
    """Merge fix-PR comments into ``enriched['pr_comments']`` for feedback detection."""
    if enriched is None:
        return None
    task = enriched.get("task") or {}
    fix_pr = (task.get("metadata") or {}).get("fix_pr")
    extra = collect_fix_pr_comments(
        fix_pr,
        gh_pr_comments=gh_pr_comments,
        gh_pr=gh_pr,
        skip_if_tracked=enriched,
        upstream_repo=upstream_repo,
    )
    if not extra:
        return enriched
    merged = dict(enriched)
    merged["pr_comments"] = list(enriched.get("pr_comments") or []) + extra
    return merged
