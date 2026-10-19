#!/usr/bin/env python3
"""GH PR status for renovate-fix — skip PRs with merge conflicts (Renovate rebases them)."""

import gh_pr_status

_orig_enrich_gh = gh_pr_status.enrich_gh


def _enrich_skip_conflicted(task):
    """Skip conflicted PRs — Renovate rebases on its own; CI-only issues re-surface after rebase."""
    result = _orig_enrich_gh(task)
    if result is not None and "conflict" in result.get("issues", []):
        return None
    return result


gh_pr_status.enrich_gh = _enrich_skip_conflicted
gh_pr_status.main()
