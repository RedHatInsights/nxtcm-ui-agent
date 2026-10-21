#!/usr/bin/env python3
"""GH PR status for renovate-fix — always retry CI failures; skip conflict-only PRs."""

import gh_pr_status

_orig_enrich_gh = gh_pr_status.enrich_gh


def _always_retry_ci(_enriched):
    """Partial CI fixes must get another session; ignore last_addressed gate."""
    return True


def _enrich_skip_conflicted(task):
    """Suppress conflict-only PRs — Renovate rebases on its own; CI re-surfaces after rebase.

    If a reviewer also commented on a conflicted PR, keep the task visible so it
    reaches P1 (feedback bucket). Only return None when conflict is the sole issue
    and there is no new human feedback.
    """
    result = _orig_enrich_gh(task)
    if result is None:
        return None
    issues = result.get("issues", [])
    if "conflict" not in issues:
        return result
    if gh_pr_status.has_new_feedback(result):
        result["issues"] = [i for i in issues if i != "conflict"]
        return result
    return None


gh_pr_status.ci_failure_needs_session = _always_retry_ci
gh_pr_status.enrich_gh = _enrich_skip_conflicted
gh_pr_status.main()
