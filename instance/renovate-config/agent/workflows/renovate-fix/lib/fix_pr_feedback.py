"""Fix-PR handoff for renovate-fix preflight.

Tasks track the Renovate PR in ``metadata.prs`` and the bot-opened fix PR in
``metadata.fix_pr``.

Once a fix PR exists:
  - CI / conflict / review issues come from the fix PR (bot's commits live there).
  - Actionable feedback comments come from the fix PR only.
  - Renovate PR state still drives MERGED/CLOSED lifecycle.

Before a fix PR exists, behaviour is unchanged (Renovate PR only).
"""

from __future__ import annotations

import re
from collections.abc import Callable

_GH_PR_URL = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", re.IGNORECASE)

# Match shared classify_gh: empty-body CHANGES_REQUESTED is still actionable.
_ACTIONABLE_EMPTY_REVIEW_STATES = frozenset({"CHANGES_REQUESTED"})

_RENOVATE_LIVE_ISSUE_PREFIXES = ("ci_fail", "konflux_urls", "review:", "review_comment:")
_RENOVATE_LIVE_ISSUES = frozenset({"conflict"})


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


def _comment_time(comment: dict) -> str:
    """Timestamp key for chronological sort (oldest-first for fmt_comments)."""
    return (comment.get("t") or comment.get("created") or "")[:16]


def _is_renovate_live_issue(issue: str) -> bool:
    if issue in _RENOVATE_LIVE_ISSUES:
        return True
    return any(issue.startswith(p) for p in _RENOVATE_LIVE_ISSUE_PREFIXES)


def _fix_live_issues(fix_issues: list[str]) -> list[str]:
    """Keep CI/conflict/review from the fix PR; never adopt its MERGED/CLOSED."""
    out = []
    for issue in fix_issues:
        if issue in ("merged", "closed"):
            continue
        if issue.startswith("konflux_urls:"):
            out.append(issue)
            continue
        if issue.startswith("ci_fail") or issue == "conflict" or issue.startswith(("review:", "review_comment:")):
            out.append(issue)
    return out


def apply_fix_pr_handoff(
    enriched: dict | None,
    *,
    gh_pr_comments: Callable[[str, int], list[dict]],
    gh_pr: Callable[[str, int], dict | None],
    classify_gh: Callable[..., tuple[str, list[str]]],
    upstream_repo: Callable[[str], tuple[str, str]] | None = None,
) -> dict | None:
    """After Renovate enrich: hand CI + actionable feedback to the fix PR when present.

    Renovate MERGED/CLOSED always win for lifecycle. Fix PR MERGED/CLOSED are
    ignored so archiving still waits on the Renovate PR.
    """
    if enriched is None:
        return None

    task = enriched.get("task") or {}
    fix_pr = (task.get("metadata") or {}).get("fix_pr")
    resolved = resolve_fix_pr(fix_pr, upstream_repo=upstream_repo)
    if not resolved:
        return enriched

    owner_repo, number = resolved
    if _already_tracked(enriched, owner_repo, number):
        return enriched

    issues = list(enriched.get("issues") or [])
    renovate_terminal = "merged" in issues or "closed" in issues

    data = gh_pr(owner_repo, number)
    fix_comments = collect_fix_pr_comments(
        fix_pr,
        gh_pr_comments=gh_pr_comments,
        gh_pr=gh_pr,
        upstream_repo=upstream_repo,
    )

    merged = dict(enriched)
    # After handoff, only fix-PR comments are actionable (communication contract).
    merged["pr_comments"] = sorted(fix_comments, key=_comment_time)
    merged["fix_pr"] = {"repo": owner_repo, "num": number, "host": "github"}

    if renovate_terminal:
        return merged

    # Strip Renovate live issues; replace with fix-PR signal (or a retry marker).
    kept = [i for i in issues if not _is_renovate_live_issue(i)]

    if data is None:
        # Fix PR unreachable — do not fall through to green Renovate CI as CLEAN.
        # Force another cycle via CI FAILING until the fix PR can be read.
        kept.append("ci_fail:fix_pr_status_unavailable")
        merged["issues"] = kept
        return merged

    state, fix_issues = classify_gh(data, last_addressed=task.get("last_addressed", ""))
    live = _fix_live_issues(fix_issues)
    kept.extend(live)
    merged["issues"] = kept

    # Annotate for agent/debug: which PR drove CI.
    pr_results = list(enriched.get("prs") or [])
    pr_results.append(
        {
            "repo": owner_repo,
            "num": number,
            "host": "github",
            "state": state,
            "issues": live,
            "data": data,
            "role": "fix_pr",
        }
    )
    merged["prs"] = pr_results
    return merged


def append_fix_pr_feedback(
    enriched: dict | None,
    *,
    gh_pr_comments: Callable[[str, int], list[dict]],
    gh_pr: Callable[[str, int], dict | None],
    upstream_repo: Callable[[str], tuple[str, str]] | None = None,
) -> dict | None:
    """Backward-compatible alias: comments-only merge (no CI handoff)."""
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
    combined = list(enriched.get("pr_comments") or []) + extra
    merged["pr_comments"] = sorted(combined, key=_comment_time)
    return merged
