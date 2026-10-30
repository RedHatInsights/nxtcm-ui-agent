#!/usr/bin/env python3
"""GH PR status for renovate-fix — always retry CI; skip conflict-only PRs.

Extends the shared gh_pr_status.main() with renovate-fix-specific behaviours:
  1. Always retry CI failures (ignore last_addressed gate).
  2. Surface paused tasks that have received new human feedback since they were
     last addressed — these appear in a ### BLOCKED FEEDBACK section so the agent
     treats them as P1 even though the task is not in an active status. Paused
     tasks whose Renovate PR is already MERGED/CLOSED are excluded (Priority 4
     owns close/archive; P1 must not steal the one-item cycle).
  3. Once metadata.fix_pr exists, hand CI + actionable comments to the fix PR
     (Renovate PR remains the MERGED/CLOSED lifecycle signal).
"""

import sys
from pathlib import Path

# Helpers live in ../lib (not preflight/) so discovery does not execute them.
_wf_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_wf_root / "lib"))

import gh_pr_status  # noqa: E402
from common import INSTANCE_ID, get_tasks, upstream_repo  # noqa: E402
from common import output_result as _output_result  # noqa: E402
from fix_pr_feedback import apply_fix_pr_handoff  # noqa: E402

_orig_enrich_gh = gh_pr_status.enrich_gh


def _always_retry_ci(_enriched):
    """Partial CI fixes must get another session; ignore last_addressed gate."""
    return True


def _enrich_with_fix_pr(task):
    """Enrich Renovate lifecycle, then hand live CI/feedback to fix PR when present."""
    return apply_fix_pr_handoff(
        _orig_enrich_gh(task),
        gh_pr_comments=gh_pr_status.gh_pr_comments,
        gh_pr=gh_pr_status.gh_pr,
        classify_gh=gh_pr_status.classify_gh,
        upstream_repo=upstream_repo,
    )


def _enrich_skip_conflicted(task):
    """Suppress Renovate-only conflict PRs — Renovate rebases on its own.

    After handoff, ``conflict`` in issues comes from the **fix PR**. The bot
    must rebase that itself — never suppress those. Only drop conflict when
    there is no fix PR yet (pure Renovate conflict wait) and no new feedback.
    """
    result = _enrich_with_fix_pr(task)
    if result is None:
        return None
    issues = result.get("issues", [])
    if "conflict" not in issues:
        return result
    # Fix PR exists → conflict is the bot's problem; keep the task visible.
    if (task.get("metadata") or {}).get("fix_pr"):
        return result
    if gh_pr_status.has_new_feedback(result):
        result["issues"] = [i for i in issues if i != "conflict"]
        return result
    return None


gh_pr_status.ci_failure_needs_session = _always_retry_ci
gh_pr_status.enrich_gh = _enrich_skip_conflicted

_captured: dict = {}


def _capture_output(status: str, content: str) -> None:
    _captured["status"] = status
    _captured["content"] = content


gh_pr_status.output_result = _capture_output
gh_pr_status.main()

blocked_feedback_lines: list[str] = []

if INSTANCE_ID:
    all_tasks = get_tasks()
    paused_tasks = [
        t for t in all_tasks
        if t.get("status") == "paused"
        and (t.get("external_key") or "").startswith("renovate-fix:")
    ]
    paused_with_feedback = []
    for task in paused_tasks:
        enriched = _enrich_with_fix_pr(task)
        if not enriched or not gh_pr_status.has_new_feedback(enriched):
            continue
        # Renovate PR already terminal → Priority 4 owns close/archive.
        issues = enriched.get("issues") or []
        if "merged" in issues or "closed" in issues:
            continue
        paused_with_feedback.append(enriched)

    if paused_with_feedback:
        blocked_feedback_lines = [
            f"### BLOCKED FEEDBACK ({len(paused_with_feedback)})",
            "(Previously paused tasks with new human comments — treat as P1)",
            "",
        ]
        for e in paused_with_feedback:
            blocked_feedback_lines.append(gh_pr_status.fmt_task(e))
            blocked_feedback_lines.append("")

active_status = _captured.get("status", "skip")
active_content = _captured.get("content", "")

if blocked_feedback_lines:
    extra = "\n".join(blocked_feedback_lines)
    final_content = extra + "\n\n" + active_content if active_content else extra
    _output_result("start", final_content)
else:
    _output_result(active_status, active_content)
