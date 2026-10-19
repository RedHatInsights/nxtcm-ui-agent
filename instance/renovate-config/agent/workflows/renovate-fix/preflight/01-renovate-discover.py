#!/usr/bin/env python3
"""Discover failing Renovate PRs on configured repos."""

import sys
import urllib.parse
from pathlib import Path

# Helpers live in ../lib (not preflight/) so discovery does not execute them.
_wf_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_wf_root / "lib"))

from common import (
    INSTANCE_ID,
    MEMORY_URL,
    get_capacity,
    http_get,
    load_project_repos,
    load_state,
    output_result,
    save_state,
)
from renovate_discover import discover_failing_renovate_prs, format_pr_line


def main():
    # Fetch tasks with explicit error detection: if the task API is unavailable
    # we cannot safely determine which PRs are already tracked or paused, so skip
    # rather than risk treating a tracked (or paused) PR as new untracked work.
    state = load_state()
    if "tasks" in state:
        tasks = state["tasks"]
    else:
        instance_param = (
            f"&instance_id={urllib.parse.quote(INSTANCE_ID)}" if INSTANCE_ID else ""
        )
        data = http_get(
            f"{MEMORY_URL}/api/tasks?exclude_status=archived&limit=50{instance_param}"
        )
        if data is None:
            output_result(
                "skip",
                "Renovate discovery: task API unavailable — skipping to avoid treating tracked work as new",
            )
            return
        tasks = data.get("items", [])
        save_state({"tasks": tasks})

    repos = load_project_repos()
    if not repos:
        output_result("skip", "Renovate discovery: no repos in project-repos.json")
        return

    auto_fix, tracked = discover_failing_renovate_prs(repos, tasks)
    total_failing = len(auto_fix) + len(tracked)

    if total_failing == 0:
        output_result("skip", "Renovate discovery: no failing Renovate PRs")
        return

    lines = [f"## Renovate Discovery ({total_failing} failing PRs)", ""]

    if auto_fix:
        lines.append(f"### AUTO-FIX ({len(auto_fix)})")
        for entry in auto_fix:
            lines.append(format_pr_line(entry))
            lines.append("")

    if tracked:
        lines.append(f"### Already tracked (see GH PR Status below) ({len(tracked)})")
        for entry in tracked:
            lines.append(f"  {entry['task_key']} PR {entry['upstream']}#{entry['number']} [{entry['issue_str']}]")
        lines.append("")

    if not auto_fix:
        output_result(
            "skip",
            f"Renovate discovery: {len(tracked)} failing PR(s) already tracked (see GH PR Status)",
        )
        return

    # Capacity pre-check: avoid starting a session when we're at capacity and there
    # is no free work to process.
    #
    # Only resume:paused (transient) entries are already committed in-flight tasks —
    # they do not need a new capacity slot and should always proceed.
    # New entries and resume:done entries (re-activating a terminal task) both require
    # a free slot, same as adding a brand-new task.
    needs_slot = [e for e in auto_fix if e.get("existing_status") != "paused"]
    free_resume = [e for e in auto_fix if e.get("existing_status") == "paused"]
    if needs_slot and not free_resume:
        active_n, max_n = get_capacity()
        if active_n >= max_n:
            output_result(
                "skip",
                f"Renovate discovery: at capacity ({active_n}/{max_n}) — "
                f"{len(needs_slot)} PR(s) pending; will retry when a slot opens",
            )
            return

    output_result("start", "\n".join(lines).rstrip())


if __name__ == "__main__":
    main()
