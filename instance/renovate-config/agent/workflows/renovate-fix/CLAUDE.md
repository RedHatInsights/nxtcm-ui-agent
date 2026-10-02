# Renovate Fix Workflow

Monitor failing Renovate dependency PRs on configured repos. Auto-fix CI failures. Humans still merge after CI is green. Merge conflicts are handled by Renovate itself.

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

Active statuses: `in_progress`, `pr_open`, `pr_changes`. Suspended: `paused` (see below). Terminal: `archived`, `done`.

**`paused` has two sub-modes distinguished by `paused_reason`:**
- `transient:*` — temporary blocker (network, registry); auto-retried next cycle via AUTO-FIX
- `blocked:*` — structural blocker (peer dep conflict, unfixable API); waiting for human action; does NOT auto-retry

**Ignore core Jira / Primary Label sections** — this workflow never uses Jira or Atlassian MCP.

## Priority 1 — Reviewer Comments

Pick first task from `### FEEDBACK` bucket in GH PR Status. A human responded — address it before doing anything else.

1. Read the reviewer's comment carefully.
2. If they request a code change: run Fix Workflow steps 1–5 first (nvm/clone/checkout/npm install/load AGENTS.md + prompt.md) to prepare the local branch, make the change, run verification (see Fix Workflow step 8), commit, push to PR head repo (see Fix Workflow step 10), post a brief response comment. `task_update(last_addressed=now)`.
3. If they provide guidance on an unfixable situation (e.g. "close this PR", "pin to older version"): do not change dependency versions. Post a comment acknowledging and explaining what action is needed from them (the bot can't close PRs or change Renovate's version pins). `task_update(last_addressed=now)`.
4. If the comment is informational with no action needed: post a brief acknowledgement. `task_update(last_addressed=now)`.

## Priority 2 — Tracked Work and Resumptions

Pick the first of:
- A task in `### CI FAILING` in GH PR Status (active tracked task needs attention)
- A `resume:paused` entry in `### AUTO-FIX` in Renovate Discovery (previously started, suspended due to transient failure)

Finish existing commitments before taking on new work.

For `resume:paused` entries: call `task_update(status="in_progress")` before starting Fix Workflow — the task was suspended; mark it active before doing work.

Then run the **Fix Workflow** below.

## Priority 3 — New Untracked PRs

Pick first `new` entry from `### AUTO-FIX` in Renovate Discovery. Only pick up fresh work when P1 and P2 are both empty.

**Capacity**: `task_check_capacity(instance_id=...)` before `task_add`. No capacity → post PR comment "at capacity, will retry" only if the bot has not already posted that exact message on this PR; stop.

**Track the task** — look up by `external_key` via `task_list(instance_id=..., external_key="renovate-fix:<repo-key>#<N>")`:
- Task exists and is `archived` or `done` → call `task_update(status="in_progress", branch="<headRefName>", title="<PR title>", metadata={...same fields as task_add below...})` to re-activate; if the framework rejects updating a terminal task, fall back to `task_add`
- Task does not exist → call `task_add`:
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

Then run the **Fix Workflow** below.

## Fix Workflow

Used by P2 (tracked/resumed tasks) and P3 (new tasks). Task tracking is handled above — go directly to step 1.

1. `nvm install 24 && nvm use 24`
2. Clone or update `./repos/<repo-key>/`:
   - Not exists → `git clone --depth 1 <url from project-repos.json>` then immediately:
     `git remote add upstream <upstream-url from project-repos.json>`
   - Either way, ensure upstream remote exists before fetching:
     `git remote get-url upstream 2>/dev/null || git remote add upstream <upstream-url from project-repos.json>`
   - `git fetch origin && git fetch upstream` (fork workflow)
   - After `gh pr checkout`, deepen if rebase needs history: `git fetch --deepen=50` or `git fetch --unshallow`
3. Checkout Renovate branch: `gh pr checkout <N> --repo <upstream>` from `./repos/<repo-key>/`
4. `npm install` — if it fails, inspect the error:
   - **Structural failure** (peer dependency conflict, incompatible engines, missing package): post a PR comment explaining why the fix can't proceed and what a human needs to decide. `task_update(status="paused", paused_reason="blocked: npm install failed: <stderr summary>")`. Stop — wait for reviewer action or PR closure.
   - **Transient failure** (network error, registry timeout, rate limit): `task_update(status="paused", paused_reason="transient: npm install failed: <stderr summary>")`, no PR comment. Stop. Auto-retried next cycle.
5. Read `AGENTS.md` + reload `personas/frontend/prompt.md`
6. Diagnose CI failure from preflight (`ci_fail:*` checks). The issue list will not contain `conflict` at this point — the preflight filter excludes conflicted PRs entirely (they wait for Renovate to rebase; the CI failure re-surfaces cleanly on the next cycle).
7. Fix code/lockfile/config — **do NOT change dependency versions beyond what Renovate already bumped**
   - Expect breaking API/type changes on large upgrades; fix call sites/tests as needed while keeping Renovate's version pin
   - **If a fix genuinely doesn't exist** (e.g. the new version has no compatible API for what the codebase does): post a PR comment explaining the blocker. `task_update(status="paused", paused_reason="blocked: <reason>")`. Stop — wait for reviewer to decide.
8. Run the **Verification sequence** defined in `personas/frontend/prompt.md` (already reloaded in step 5). Do NOT use `npm run test:all:quiet` from `AGENTS.md` — it bundles CT and cannot be shimmed in this container.
   If any verification step fails: return to step 7, fix the underlying issue, and re-run from the failing step. If the failure is unrelated to the version bump (pre-existing) or has no fix, treat it as a blocker (see step 7 blocked case).
9. Commit: `fix(deps): resolve CI for renovate bump <package>`
10. Push to the **PR head repository** (NOT fork `origin`, NOT `bot/<KEY>`):
    ```bash
    # head_owner, head_repo, head_ref, is_cross_repository are in preflight metadata for P3 tasks.
    # For P2 tasks (coming from task metadata), resolve if not stored:
    gh pr view <N> --repo <upstream> --json headRefName,headRepository,headRepositoryOwner,isCrossRepository
    # Push remote = headRepositoryOwner/headRepository (usually upstream, not the bot fork)
    git remote get-url head-pr 2>/dev/null || git remote add head-pr "https://github.com/<head_owner>/<head_repo>.git"
    git push head-pr HEAD:<headRefName>
    ```
11. `task_update(status="pr_open", last_addressed=now, metadata.last_step="ci_fix_pushed")`
12. Post brief PR comment: what was fixed + verification run

On push failure → `metadata.last_step="push_failed"`, PR comment, keep `in_progress` for retry. Do **not** use `/push-and-pr` or create a new PR.

**CI still red after push**: next cycle re-enters via `### CI FAILING` (this workflow always retries CI — partial fixes continue).

## Priority 4 — Merged / Closed PR Cleanup

When preflight shows `MERGED` or `CLOSED` for a tracked Renovate task:

1. `memory_store` useful learnings if merged (`category=learning`, tags=`dependency-upgrade`, `renovate`, repo filter)
2. `task_update` → `status="archived"`
3. Do NOT delete Renovate branches (Renovate manages cleanup)

If all sections empty and GH PR Status shows all CLEAN → stop with no work.

## Rules

### Security override — Renovate head pushes (supersedes core)

Core Security Rules say "NEVER push to branches other than `bot/<TICKET-KEY>`". **That rule does not apply to this workflow.**

For renovate-fix only:
- **Required**: push to the Renovate PR head ref on the PR **head repository** (`head_owner`/`head_repo` + `headRefName` / `metadata.head_ref`)
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
