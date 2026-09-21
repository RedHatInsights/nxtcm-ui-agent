#!/usr/bin/env python3
"""GH PR status for renovate-fix — always re-enter on CI failure."""

import gh_pr_status


def _always_retry_ci(_enriched):
    """Partial CI fixes must get another session; ignore last_addressed gate."""
    return True


gh_pr_status.ci_failure_needs_session = _always_retry_ci
gh_pr_status.main()
