#!/usr/bin/env python3
"""Discover failing Renovate PRs on configured repos."""

import sys
from pathlib import Path

# Helpers live in ../lib (not preflight/) so discovery does not execute them.
_wf_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_wf_root / "lib"))

from common import get_tasks, load_project_repos, output_result
from renovate_discover import discover_failing_renovate_prs, format_pr_line


def main():
    tasks = get_tasks()
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

    output_result("start", "\n".join(lines).rstrip())


if __name__ == "__main__":
    main()
