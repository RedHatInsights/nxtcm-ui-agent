# Renovate Fix Workflow

Monitor failing Renovate dependency PRs on configured repos. Auto-fix CI for any Renovate PR with failing checks or merge conflicts (all semver tiers). Humans still merge after CI is green.

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

**Ignore core Jira / Primary Label sections** — this workflow never uses Jira or Atlassian MCP.

## Priority 1 — Auto-Fix Failing Renovate PRs

Pick first PR from `### AUTO-FIX` section OR first `CI FAILING` / `CONFLICTS` tracked task.

**Capacity**: `task_check_capacity(instance_id=...)` before `task_add`. No capacity → PR comment "at capacity, will retry", leave untracked, stop.

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
    "prs": [{"repo": "<upstream>", "number": N, "url": "...", "host": "github"}],
    "head_ref": "<headRefName>",
    "head_owner": "<headRepositoryOwner.login>",
    "head_repo": "<headRepository.name>"
  }
)
```

### Fix workflow

1. `nvm install 24 && nvm use 24`
2. Clone or update `./repos/<repo-key>/`:
   - Not exists → `git clone --depth 1 <url from project-repos.json>` then immediately:
     `git remote add upstream <upstream-url from project-repos.json>`
   - Either way, ensure upstream remote exists before fetching:
     `git remote get-url upstream 2>/dev/null || git remote add upstream <upstream-url from project-repos.json>`
   - `git fetch origin && git fetch upstream` (fork workflow)
   - After `gh pr checkout`, deepen if rebase needs history: `git fetch --deepen=50` or `git fetch --unshallow`
3. Checkout Renovate branch: `gh pr checkout <N> --repo <upstream>` from `./repos/<repo-key>/`
4. `npm install` — fails → PR comment + `task_update` paused_reason, stop
5. Read `AGENTS.md` + reload `personas/frontend/prompt.md`
6. Diagnose CI failure from preflight (`ci_fail:*` checks).
   **If the issue list also contains `conflict`**: the CI failure may be caused by or compounded by the merge conflict. Perform the P2 rebase first (fetch upstream, rebase onto default branch, resolve conflicts preserving Renovate's version pins, force-push) before attempting any code fixes. If the rebase fails, stop and update `paused_reason`.
7. Fix code/lockfile/config — **do NOT change dependency versions beyond what Renovate already bumped**
   - Expect breaking API/type changes on large upgrades; fix call sites/tests as needed while keeping Renovate's version pin
8. Verify sequentially (persona rules — **never run in parallel**):
   - `npm run lint`
   - `npm run type-check`
   - `npm run test:unit` (jest only — skip if the script doesn't exist, jest does not run in CI)
   - Playwright CT — **must apply the container browser shim first** (see `personas/frontend/prompt.md` Playwright CT section for the stash + patch sequence); run `npm run test:ct` inside the shim block, then restore the file
   - `npm run build` (+ workspace builds if packages changed)
9. Commit: `fix(deps): resolve CI for renovate bump <package>`
10. Push to the **PR head repository** (NOT fork `origin`, NOT `bot/<KEY>`):
    ```bash
    # Prefer head_owner/head_repo from preflight metadata; else resolve:
    gh pr view <N> --repo <upstream> --json headRefName,headRepository,headRepositoryOwner,isCrossRepository
    # Push remote = headRepositoryOwner/headRepository (usually upstream, not the bot fork)
    git remote get-url head-pr 2>/dev/null || git remote add head-pr "https://github.com/<head_owner>/<head_repo>.git"
    git push head-pr HEAD:<headRefName>
    ```
    Or if already on that branch and `head-pr` tracks it: `git push head-pr HEAD`
11. `task_update` → `status="pr_open"`, `last_addressed=now`, `metadata.last_step="ci_fix_pushed"`
12. Post brief PR comment: what was fixed + verification run

On push failure → `metadata.last_step="push_failed"`, PR comment, keep `in_progress` for retry. Do **not** use `/push-and-pr` or create a new PR.

**CI still red after push**: next cycle re-enters via `### CI FAILING` (this workflow always retries CI — partial fixes continue).

## Priority 2 — Merge Conflicts

For `CONFLICTS` bucket on any Renovate PR:

1. Checkout PR branch
2. Rebase onto default branch: resolve via `gh repo view <upstream> --json defaultBranchRef --jq .defaultBranchRef.name`, then `git fetch --unshallow 2>/dev/null || git fetch --deepen=50; git fetch upstream && git rebase upstream/<default>`
3. Resolve conflicts — preserve Renovate's dependency version changes
4. Force push to PR head repo (same `head-pr` remote as P1 step 10): `git push --force-with-lease head-pr HEAD:<headRefName>`
5. Re-run verification (same sequence as P1 step 8: lint → type-check → test:unit → CT with shim → build)
6. `task_update` `last_addressed=now`

## Priority 3 — Merged / Closed PR Cleanup

When preflight shows `MERGED` or `CLOSED` for a tracked Renovate task:

1. `memory_store` useful learnings if merged (`category=learning`, tags=`dependency-upgrade`, `renovate`, repo filter)
2. `task_update` → `status="archived"`
3. Do NOT delete Renovate branches (Renovate manages cleanup)

If all sections empty and GH PR Status shows all CLEAN → stop with no work.

## Rules

### Security override — Renovate head pushes (supersedes core)

Core Security Rules say "NEVER push to branches other than `bot/<TICKET-KEY>`". **That rule does not apply to this workflow.**

For renovate-fix only:
- **Required**: push / `--force-with-lease` to the Renovate PR head ref on the PR **head repository** (`head_owner`/`head_repo` + `headRefName` / `metadata.head_ref`)
- **Forbidden**: create `bot/` branches, open a new PR, or use `/push-and-pr`
- **Still forbidden**: push to `main`/`master`

This override is intentional and authorized for dependency CI repair on existing Renovate PRs.

### Other rules

- **ONE item/cycle** — fix one PR issue, then stop
- **Never merge PRs** — humans merge after CI green
- **Never create Jira tickets** or use Jira MCP tools
- **Never modify `.github/workflows/`**
- **Ignore Renovate bot comments** as actionable feedback (`renovate[bot]` is a bot author)
- **Do NOT re-fetch** data already in preflight input
- Reload `personas/frontend/prompt.md` before fixing nxtcm-components
- Use `gh pr comment` for human-facing updates (normal language, not caveman mode)
- Renovate may rebase/force-update its branches later and overwrite bot commits — re-fix on next cycle if CI fails again
