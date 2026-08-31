# Renovate Fix Workflow

Monitor failing Renovate dependency PRs on configured repos. Auto-fix CI for minor/patch bumps. Major bumps get a review-request comment only — no code changes.

## Cycle Loop

ONE item/cycle. Read preflight input (Renovate Discovery + GH PR Status sections).

**Status updates** via `bot_status_update(instance_id=...)`:
- Cycle start: `working`, "Starting cycle — checking Renovate PRs..."
- Pick PR: include `external_key` + `repo`
- Cycle end: `idle`, "Cycle complete. Sleeping..." or "No Renovate work found. Sleeping..."
- Error: `error`, "<what went wrong>"

**Task identity** — always use:
- `source_type="github"` (NOT default `"jira"`)
- `external_key="renovate-fix:<repo-key>#<pr-number>"` (e.g. `renovate-fix:nxtcm-components#42`)
- Pass `instance_id` to all `task_list`, `task_add`, `task_check_capacity`, `bot_status_update` calls

Active statuses: `in_progress`, `pr_open`, `pr_changes`. Terminal: `archived`, `paused`, `done`.

## Priority 0 — Major Version PRs (comment only)

For each PR in `### MAJOR` preflight section OR tracked task with `metadata.bump_type=major`:

1. Check `metadata.major_comment_posted` — if true, skip (no repeat comments)
2. Read PR body via `gh pr view <N> --repo <upstream> --json body,title`
3. Post PR comment via `gh pr comment <N> --repo <upstream> --body "..."` with:
   - Package name and old → new version
   - Semver tier: **major**
   - Summary of CI failures from preflight
   - Breaking-change notes from Renovate PR body (release notes section if present)
   - Explicit ask: *"This is a major dependency update. Please confirm if you want this merged; the bot will not auto-fix major bumps."*
4. `task_add` or `task_update`:
   - `source_type="github"`
   - `external_key="renovate-fix:<repo-key>#<N>"`
   - `status="paused"`, `paused_reason="major_version_pending_review"`
   - `metadata`: `{"bump_type": "major", "major_comment_posted": true, "renovate": true, "prs": [{"repo": "<upstream>", "number": N, "host": "github"}]}`
5. **Do NOT** checkout, commit, or push

If human later approves via PR comment ("please fix", "go ahead", "merge") → treat as feedback in P1 only if they explicitly request the bot to fix CI. Default: major stays paused until human merges or fixes manually.

## Priority 1 — Auto-Fix Failing Renovate PRs (minor/patch)

Pick first PR from `### AUTO-FIX` section OR first `CI FAILING` / `CONFLICTS` tracked task (non-major).

**Skip** if `metadata.bump_type=major` or PR appears in MAJOR section.

### Track task

If not tracked:
```
task_add(
  instance_id=...,
  external_key="renovate-fix:<repo-key>#<N>",
  source_type="github",
  repo="<repo-key>",
  branch="<headRefName from preflight>",
  status="in_progress",
  title="<PR title>",
  metadata={
    "renovate": true,
    "bump_type": "minor|patch",
    "prs": [{"repo": "<upstream>", "number": N, "url": "...", "host": "github"}],
    "head_ref": "<headRefName>"
  }
)
```

### Fix workflow

1. `nvm install 24 && nvm use 24`
2. Clone or update `./repos/<repo-key>/`:
   - Not exists → `git clone --depth 1 <url from project-repos.json>`
   - `git fetch origin && git fetch upstream` (fork workflow)
3. Checkout Renovate branch: `gh pr checkout <N> --repo <upstream>` from `./repos/<repo-key>/`
4. `npm install` — fails → PR comment + `task_update` paused_reason, stop
5. Read `AGENTS.md` + reload `personas/frontend/prompt.md`
6. Diagnose CI failure from preflight (`ci_fail:*` checks)
7. Fix code/lockfile/config — **do NOT change dependency versions beyond what Renovate already bumped**
8. Verify sequentially (persona rules):
   - `npm run lint`
   - `npm run type-check`
   - `npm run test:all`
   - `npm run build` (+ workspace builds if packages changed)
9. Commit: `fix(deps): resolve CI for renovate bump <package>`
10. Push to Renovate head branch (NOT `bot/<KEY>`):
    ```bash
    git push origin HEAD:<headRefName>
    ```
    Or `git push origin <headRefName>` if already on branch
11. `task_update` → `status="pr_open"`, `last_addressed=now`, `metadata.last_step="ci_fix_pushed"`
12. Post brief PR comment: what was fixed + verification run

On push failure → `metadata.last_step="push_failed"`, PR comment, keep `in_progress` for retry.

## Priority 2 — Merge Conflicts (non-major only)

For `CONFLICTS` bucket on minor/patch Renovate PRs:

1. Checkout PR branch
2. Rebase onto default branch: `git fetch upstream && git rebase upstream/main` (or master)
3. Resolve conflicts — preserve Renovate's dependency version changes
4. Force push to PR head: `git push --force-with-lease origin <headRefName>`
5. Re-run verification (lint → type-check → test:all → build)
6. `task_update` `last_addressed=now`

## Priority 3 — Merged PR Cleanup

When preflight shows `MERGED` for a tracked Renovate task:

1. `memory_store` useful learnings (`category=learning`, tags=`dependency-upgrade`, `renovate`, repo filter)
2. `task_update` → `status="archived"`
3. Do NOT delete Renovate branches (Renovate manages cleanup)

## Priority 4 — Discover New PRs

If preflight `### AUTO-FIX` or `### MAJOR` lists untracked PRs and higher priorities empty:

- Create task (P0 for major → paused after comment; P1 for minor/patch → in_progress)
- Work one PR this cycle, stop

If all sections empty and GH PR Status shows all CLEAN → stop with no work.

## Rules

- **ONE item/cycle** — fix one PR issue, then stop
- **Never auto-fix or push to major-version PRs** unless human explicitly requests in PR comment
- **Never merge PRs** — humans merge after CI green
- **Never create Jira tickets** or use Jira MCP tools
- **Never modify `.github/workflows/`**
- **Ignore Renovate bot comments** as actionable feedback (`renovate[bot]` is a bot author)
- **Do NOT re-fetch** data already in preflight input
- Reload `personas/frontend/prompt.md` before fixing nxtcm-components
- Use `gh pr comment` for human-facing updates (normal language, not caveman mode)
