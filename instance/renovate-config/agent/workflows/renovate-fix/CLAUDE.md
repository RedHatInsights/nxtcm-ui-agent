# Renovate Fix Workflow

Monitor failing Renovate dependency PRs on configured repos. Auto-fix CI failures. Humans still merge after CI is green. Renovate rebase handles conflicts on the Renovate PR; after handoff, fix-PR conflicts with the base branch are the bot's job (rebase the fork tip).

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
- `last_addressed=now` means the current UTC datetime as an ISO 8601 string (e.g. `"2026-10-06T17:00:00Z"`)

Active statuses: `in_progress`, `pr_open`, `pr_changes`. Suspended: `paused` (see below). Terminal: `archived`, `done`.

**`paused` has sub-modes distinguished by `paused_reason`:**
- `transient:*` — temporary blocker (network, registry); auto-retried next cycle via AUTO-FIX
- `blocked:*` — structural blocker (peer dep conflict, unfixable API); waiting for human action; does NOT auto-retry
- any other non-empty value (e.g. `"Paused via dashboard"`) — manual or unclassified pause; does NOT auto-retry; requires human to resume or close the task
- (empty) — no reason recorded; treated as retryable for backwards compatibility

**Ignore core Jira / Primary Label sections** — this workflow never uses Jira or Atlassian MCP.

## Fix PR handoff (communication + CI)

**Before** `metadata.fix_pr` exists: Renovate PR is the work surface (comments, CI, checkout).

**After** `metadata.fix_pr` exists:
- **All bot posts** go to the fix PR (status, blockers, replies). Do not comment on the Renovate PR again (except the one-time handoff comment in Fix Workflow step 12).
- **Actionable feedback** is expected on the fix PR. Preflight only surfaces fix-PR comments as FEEDBACK. Soft redirect: if a human somehow comments on the Renovate PR after handoff and you notice it outside preflight, reply once on the Renovate PR pointing at the fix PR, then do any code work on the fix branch.
- **CI FAILING** in preflight is driven by the **fix PR** checks (bot commits live there). Renovate PR CI is ignored once a fix PR exists.
- **Lifecycle** (MERGED/CLOSED → Priority 4) still comes from the **Renovate PR**.
- **Checkout** always uses the fork tip (`origin/<headRefName>`), never `gh pr checkout` of the Renovate PR.

## Priority 1 — Reviewer Comments

Pick first task from **`### FEEDBACK`** or **`### BLOCKED FEEDBACK`** bucket in GH PR Status. A human responded — address it before doing anything else.

**`### BLOCKED FEEDBACK`** contains previously paused (blocked) tasks that have received new human comments since the last addressed timestamp. Always `task_update(status="in_progress")` before doing any new work on these tasks to re-activate them. Terminal Renovate PRs (MERGED/CLOSED) are excluded — Priority 4 owns those.

**Also check `### CI FAILING` for hidden feedback**: Before CI repair, look at `pr_comments` in preflight. If there are human comments since `last_addressed`, treat as P1 first.

1. Read the reviewer's comment carefully.
2. If they request a code change or indicate the previous blocker is resolved (e.g. "fork was created for you, try to open a PR from your fork"):
   - **`metadata.fix_pr` is set**: Fix Workflow steps 1–2 first (nvm + clone/fetch remotes), then **Checkout fork tip**, then steps 4–5, change, verify (step 8), commit, `git push origin HEAD:<headRefName>`. Do not open a second PR. Reply on the **fix PR**.
   - **No fix PR yet**: Fix Workflow steps 1–5 (Renovate checkout), change, verify (step 8), commit, push + open fix PR (steps 10–12). That persists `metadata.fix_pr` and posts the handoff on Renovate. Reply on the PR where they commented (Renovate, until handoff completes).
   - Checkout / push failure rules: see **Checkout fork tip** and Fix Workflow push-failure rules. Do **not** set `last_addressed` or claim success unless the push (and create, when needed) succeeded. Then reply and `task_update(last_addressed=now)`.
   - If `npm install` fails (step 4): post on the active communication PR (fix PR if set, else Renovate). `task_update(status="paused", paused_reason="blocked: npm install failed during P1 response: <stderr summary>", last_addressed=now)`. Stop.
3. If they provide guidance on an unfixable situation (e.g. "close this PR", "pin to older version"): do not change dependency versions. Reply on the active communication PR (fix PR if set, else Renovate) explaining what they must do (bot can't close the Renovate PR or change Renovate pins). `task_update(last_addressed=now)`.
4. If informational with no action: brief ack on the active communication PR. `task_update(last_addressed=now)`.

## Priority 2 — Tracked Work and Resumptions

**`### CI FAILING` (GH PR Status) takes precedence over `### AUTO-FIX` resume entries.** Check CI FAILING first; only fall through to AUTO-FIX resume if CI FAILING is empty.

- A task in `### CI FAILING` in GH PR Status — active tracked task that still needs attention; pick the first entry.
- A `resume:paused` entry in `### AUTO-FIX` in Renovate Discovery — previously started and suspended; eligible because the `paused_reason` starts with `transient:` or has no recorded reason (treated as safe to retry). Tasks with `blocked:*` reasons or manual pauses (any other non-empty reason) never appear here — they are filtered out by the preflight and require human action to resume.

Finish existing commitments before taking on new work.

For `resume:paused` entries: call `task_update(status="in_progress")` before starting Fix Workflow — the task was suspended; mark it active before doing work.

Then run the **Fix Workflow** below. If `metadata.fix_pr` is set, step 3 uses **Checkout fork tip** (not Renovate `gh pr checkout`).

## Priority 3 — New Untracked PRs

Pick first `new` or `resume:done` entry from `### AUTO-FIX` in Renovate Discovery. Only pick up fresh work when P1 and P2 are both empty.

A `resume:done` entry means the task previously reached a terminal `done` state (e.g. was closed without going through the outcome-report path). Re-activate it the same way as a `done` task below — do NOT create a duplicate with `task_add` unless `task_update` is rejected.

**Capacity**: `task_check_capacity(instance_id=...)` before `task_add` (and before re-activating a `done` task). No capacity → check whether the bot has already posted an "at capacity" comment on this PR (`gh pr view <N> --repo <upstream> --comments --json comments` and scan for a comment authored by the bot with that text). If no such comment exists, post: "At capacity — will pick this up on a future cycle when a slot opens." Then stop. Do not post again if the comment is already there.

**Track the task** — look up by `external_key` via `task_get(external_key="renovate-fix:<repo-key>#<N>", source_type="github")`:
- Task exists and is `archived` or `done` → call `task_update(status="in_progress", title="<PR title>", metadata={...same fields as task_add below...})` to re-activate; if the framework rejects updating a terminal task, fall back to `task_add`
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

## Checkout fork tip

Used whenever `metadata.fix_pr` is set (P1 follow-up, P2 CI repair, Fix Workflow step 3). Shallow clones are single-branch — a plain `git fetch origin` will **not** create `origin/<headRefName>`.

From `./repos/<repo-key>/` after steps 1–2:

```bash
head_ref=<metadata.head_ref or task.branch>
git fetch origin "${head_ref}:refs/remotes/origin/${head_ref}"
git checkout -B "${head_ref}" "origin/${head_ref}"
```

- Fetch/checkout fails → stop. Do **not** reply as success. Do **not** set `last_addressed`.
  - Transient (network): `task_update(status="paused", paused_reason="transient: fix PR checkout failed: <stderr summary>")`
  - Permanent (branch deleted / missing on fork): `task_update(status="paused", paused_reason="blocked: fix PR checkout failed: <stderr summary>")`. Post on the fix PR if possible.
- Push after changes: `git push origin HEAD:${head_ref}` — same rules as Fix Workflow push-failure (do **not** `paused`+`transient:` on push; that strands the task after handoff because Discovery only resumes paused work when the Renovate PR still looks actionable):
  - Auth/permission (HTTP 403, remote rejected): `task_update(status="paused", paused_reason="blocked: fork push rejected — check bot fork access")`. Post on the fix PR. Stop — do not auto-retry.
  - Transient (network): `task_update(metadata.last_step="push_failed")`, post on the fix PR, keep `in_progress` (no `last_addressed`). Next cycle re-enters via fix-PR `### CI FAILING` or active-task status.

## Fix Workflow

Used by P2 (tracked/resumed tasks) and P3 (new tasks). Task tracking is handled above — go directly to step 1.

1. `nvm install 24 && nvm use 24`
2. Clone or update `./repos/<repo-key>/`:
   - Not exists → `git clone --depth 1 <url from project-repos.json>`
   - Ensure upstream remote exists (idempotent, covers both fresh clone and existing repo):
     `git remote get-url upstream 2>/dev/null || git remote add upstream <upstream-url from project-repos.json>`
   - `git fetch origin && git fetch upstream` (fork workflow)
   - After checkout, deepen if rebase needs history: `git fetch --deepen=50` or `git fetch --unshallow`
3. Checkout the work branch from `./repos/<repo-key>/`:
   - **`metadata.fix_pr` is set** → **Checkout fork tip** (above). Never `gh pr checkout` the Renovate PR.
   - **No fix PR yet** → `gh pr checkout <N> --repo <upstream>` (Renovate PR). If that fails (branch deleted, access denied, merge in progress): `task_update(status="paused", paused_reason="blocked: gh pr checkout failed: <stderr summary>")`. Post a PR comment if the failure is permanent (e.g. branch deleted). Stop — do not attempt npm install or any further steps.
4. `npm install` — if it fails, inspect the error:
   - **Peer dependency conflict**: Renovate only bumps one package at a time, which can leave transitive deps in an incompatible state. The bot can safely resolve these narrow conflicts via `overrides` without making version decisions that belong to Renovate. Attempt a safe fix before escalating:
     1. Identify which package is conflicting and why (read the npm error output carefully).
     2. If the conflict is in a **transitive/indirect** dep: add or update a `overrides` entry in `package.json` to pin the transitive dep to a compatible version. Re-run `npm install`.
     3. If the conflict is in a **direct** dep that Renovate manages (i.e. it appears in Renovate's bump): **do not touch it** — go straight to escalation below.
     4. If the fix succeeds: continue Fix Workflow. If no safe fix exists or `npm install` still fails after attempting a fix: post a PR comment identifying the specific conflict (package name, required vs. installed version) and what a human needs to decide. `task_update(status="paused", paused_reason="blocked: peer conflict: <package> requires <X>, found <Y>")`. Stop — wait for reviewer's next action.
   - **Other structural failure** (incompatible engines, missing package): post a PR comment explaining why the fix can't proceed and what a human needs to decide. `task_update(status="paused", paused_reason="blocked: npm install failed: <stderr summary>")`. Stop — wait for reviewer action or PR closure.
   - **Transient failure** (network error, registry timeout, rate limit): `task_update(status="paused", paused_reason="transient: npm install failed: <stderr summary>")`, no PR comment. Stop. Auto-retried next cycle.
5. Read `AGENTS.md` + reload `personas/frontend/prompt.md`
6. Diagnose CI failures from preflight (`ci_fail:*` checks). Once a fix PR exists these are the **fix PR** checks. Preflight suppresses **Renovate-only** conflict (no fix PR yet). After handoff, fix-PR `conflict` stays visible — rebase the fork tip onto the base branch, push, and continue. If multiple `ci_fail:*` issues are listed, fix all of them in this cycle — verification in step 8 confirms before pushing.
7. Fix code/lockfile/config — **do NOT change dependency versions beyond what Renovate already bumped**
   - Expect breaking API/type changes on large upgrades; fix call sites/tests as needed while keeping Renovate's version pin
   - **If a fix genuinely doesn't exist** (e.g. the new version has no compatible API for what the codebase does): post on the active communication PR (fix PR if set, else Renovate). `task_update(status="paused", paused_reason="blocked: <reason>")`. Stop — wait for reviewer to decide.
8. Run the **Verification sequence** defined in `personas/frontend/prompt.md` (already reloaded in step 5). Do NOT use `npm run test:all:quiet` from `AGENTS.md` — it bundles CT and cannot be shimmed in this container.
   If any verification step fails: return to step 7, fix the underlying issue, and re-run from the failing step. If the failure is unrelated to the version bump (pre-existing) or has no fix, treat it as a blocker (see step 7 blocked case).
9. Stage and commit all changed files. Always include `package-lock.json` if it changed (e.g. after an `npm install` with `overrides`). If `package.json` was modified (e.g. `overrides` entry added), include it too. Use a message that reflects the nature of the fix:
   - Code/type/test fix: `fix(deps): resolve CI for renovate bump <package>`
   - Overrides-only fix: `fix(deps): add overrides to resolve peer conflict for <package>`
10. Push the fix to the **bot's fork** (`origin`) and open a new PR from it targeting the Renovate PR's base branch:
    ```bash
    # origin is the bot's fork (project-repos.json "url" field); push the fix branch there
    git push origin HEAD:<headRefName>

    # Determine the base branch from the Renovate PR (do NOT hardcode 'main')
    upstream_path=$(git remote get-url upstream | sed 's|.*github\.com[:/]||; s|\.git$||')
    base_branch=$(gh pr view <N> --repo "$upstream_path" --json baseRefName --jq .baseRefName)

    # Determine fork owner via gh CLI — works for both HTTPS and SSH remotes
    fork_owner=$(gh api user --jq .login)

    # Create the fix PR (gh pr create exits non-zero if a PR already exists — that is expected)
    gh pr create \
      --repo "$upstream_path" \
      --head "${fork_owner}:${headRefName}" \
      --base "$base_branch" \
      --title "fix(deps): resolve CI for Renovate bump (${headRefName})" \
      --body "CI fix for Renovate PR #<N> (<upstream-pr-url>). <summary of what was fixed>" || true

    # Retrieve the open fix PR (new or pre-existing) — need url + number for metadata
    # Use '// empty' so jq returns '' instead of 'null' when the array is empty
    fix_pr_json=$(gh pr list \
      --repo "$upstream_path" \
      --head "${fork_owner}:${headRefName}" \
      --state open \
      --json url,number --jq '.[0] // empty')
    fix_pr_url=$(echo "$fix_pr_json" | jq -r '.url // empty')
    fix_pr_number=$(echo "$fix_pr_json" | jq -r '.number // empty')

    # If still empty, the PR was not created and does not exist — treat as a real failure
    if [ -z "$fix_pr_url" ] || [ -z "$fix_pr_number" ]; then
      # Post a PR comment and pause the task
      task_update(status="paused", paused_reason="blocked: gh pr create failed and no open fix PR found")
      exit 1
    fi
    ```
11. **Required:** `task_update(status="pr_open", last_addressed=now, metadata.last_step="ci_fix_pushed", metadata.fix_pr={"url": "<fix_pr_url>", "repo": "<upstream_path>", "number": <fix_pr_number>, "host": "github"})` — without this, preflight cannot hand CI/comments to the fix PR. (P1 "no fix PR yet" must run this step too, not only `last_addressed`.)
12. **One-time handoff** on the **Renovate PR** (#N): brief note that the fix PR is open, what was fixed / verification summary, and that **further review and discussion should continue on the fix PR**. After this, all bot communication is on the fix PR. Also post the same summary on the **fix PR** as the working thread.

On push failure to `origin` — inspect the error before deciding:
- **Auth/permission error** (HTTP 403, "remote rejected"): `task_update(status="paused", paused_reason="blocked: fork push rejected — check bot fork access")`. Post on the active communication PR. Stop — do not retry.
- **Transient error** (network timeout, temporary server error): `task_update(metadata.last_step="push_failed")`, post on the active communication PR, keep `in_progress`. Will retry next cycle via `### CI FAILING` (fix PR checks once `metadata.fix_pr` is set).

**CI still red after push**: next cycle re-enters via `### CI FAILING` on the **fix PR** once handed off (this workflow always retries CI — partial fixes continue).

## Priority 4 — Merged / Closed PR Cleanup

Unlike P1–P3, P4 processes **all** matching items in one pass.

**Close the bot fix PR** before archiving. This is the only PR the bot closes. Do not close the Renovate PR. Do not delete the fork branch or the Renovate branch.

**Per-task bindings** — at the start of each P4 item, clear close state so a prior task cannot leak:
```bash
fix_repo=""; fix_pr_number=""; fix_pr_url=""; allow_archive_without_close=0
```

**Resolve `<fix-repo>` / `<fix-number>`** — same preference order as preflight `resolve_fix_pr` (URL first):
1. Prefer `metadata.fix_pr.url` → parse `github.com/<owner>/<repo>/pull/<n>` into `fix_repo` + `fix_pr_number`.
2. Else use `metadata.fix_pr.number` with `metadata.fix_pr.repo`. If `repo` has no `/` (bare key), resolve via `project-repos.json` upstream. Never pass a bare key to `gh`.
3. If `metadata.fix_pr` is set but steps 1–2 cannot resolve a concrete `owner/repo` + number → **do not archive** (`continue`). Do not fall through to “nothing to close.”
4. If `metadata.fix_pr` is missing entirely: rediscover. Set `upstream_path` from `metadata.prs[0].repo` or `project-repos.json` (fresh each task — do not reuse a prior shell value).
   ```bash
   head_ref=<metadata.head_ref or task.branch>
   if [ -z "$upstream_path" ] || [ -z "$head_ref" ]; then
     continue  # do not archive
   fi
   fork_owner=$(gh api user --jq .login) || continue
   if ! fix_pr_json=$(gh pr list \
     --repo "$upstream_path" \
     --head "${fork_owner}:${head_ref}" \
     --state open \
     --json url,number --jq '.[0] // empty'); then
     continue  # do not archive
   fi
   if [ -z "$fix_pr_json" ]; then
     allow_archive_without_close=1  # exit 0 + empty → no open fix PR
   else
     fix_pr_url=$(echo "$fix_pr_json" | jq -r '.url // empty')
     fix_pr_number=$(echo "$fix_pr_json" | jq -r '.number // empty')
     fix_repo="$upstream_path"
     if [ -z "$fix_pr_number" ] || [ -z "$fix_repo" ]; then
       continue  # do not archive
     fi
   fi
   ```

**Close sequence** (must honor exit codes):
```bash
if [ "$allow_archive_without_close" = "1" ]; then
  :  # rediscovery proved no open fix PR — archive allowed
elif [ -z "$fix_pr_number" ] || [ -z "$fix_repo" ]; then
  continue  # unresolved — do NOT archive
else
  if ! fix_state=$(gh pr view "$fix_pr_number" --repo "$fix_repo" --json state --jq .state); then
    continue
  fi
  if [ "$fix_state" = "OPEN" ]; then
    if ! gh pr close "$fix_pr_number" --repo "$fix_repo" \
        --comment "Closing because Renovate PR #<N> was merged or closed."; then
      continue
    fi
  fi
fi
```

**Failure rule (active and paused alike):** Only archive after a successful close, when the fix PR is already `MERGED`/`CLOSED`, or when rediscovery exits 0 with empty stdout (`allow_archive_without_close=1`). Unresolvable `metadata.fix_pr`, failed `gh`, or empty bindings without that flag → do **not** call `task_outcome_report` / `task_remove`.

**Active task cleanup**: When the **GH PR Status section** (`### MERGED` / `### CLOSED` buckets in script 02 output) shows tracked Renovate tasks as merged or closed, for each one:

1. Close the bot fix PR (resolve + close sequence above). On failure → skip archive for this task and continue to the next P4 item.
2. `memory_store` useful learnings if the Renovate PR was merged (`category=learning`, tags=`dependency-upgrade`, `renovate`, repo filter)
3. `task_outcome_report(external_key=..., source_type="github", artifacts=[PR artifact], evidence=[PR merged/closed state as kind="state"], notes=...)` then `task_remove(external_key=..., source_type="github")`
4. Do NOT delete Renovate branches (Renovate manages cleanup)

**Paused task cleanup**: Script 02 only checks active tasks — a paused task whose PR merged or closed never surfaces in `### MERGED` / `### CLOSED` automatically. Run this after the active cleanup above (or immediately when GH PR Status is all CLEAN):
- Call `task_list(instance_id=..., status="paused")` (`task_list` does not accept `source_type`; filter by `external_key` prefix instead).
- For each returned task whose `external_key` starts with `renovate-fix:`, extract the upstream repo and PR number from `metadata.prs[0]` (or parse `external_key` as `renovate-fix:<repo-key>#<N>` and look up the repo-key in `project-repos.json` to get the upstream URL).
- Call `gh pr view <N> --repo <upstream> --json state`.
- If `MERGED`: close the bot fix PR (same resolve + close sequence and **failure rule** as above). Only on success (or already closed / no open fix PR) → outcome-report → archive (steps 2–3 above).
- If `CLOSED`: close the bot fix PR (same failure rule). Only on success (or already closed / no open fix PR) → archive with `task_outcome_report` + `task_remove` (no `memory_store` needed unless there are useful learnings).
- If still `OPEN`: leave as-is — the task remains paused until a human acts or Renovate rebases. Do not close the fix PR.

Once both cleanups are done (or there was nothing to do) → stop with no work.

## Rules

### Security override — Fork push and fix PR (supersedes core)

Core Security Rules say "NEVER push to branches other than `bot/<TICKET-KEY>`" and "NEVER open a new PR". **Neither rule applies to this workflow.**

For renovate-fix only:
- **Required**: push the fix to the **bot's fork** (`origin` remote, same branch name as `headRefName`), then open a PR from the fork to `upstream/main` via `gh pr create`
- **Forbidden**: push directly to the upstream Renovate branch (`headRefName` on `headRepositoryOwner/headRepository`); use `/push-and-pr` skill; create `bot/` branches
- **Still forbidden**: push to `main`/`master` on either the fork or upstream

This override is intentional and authorized: the bot does not have write access to the upstream repo.

### Other rules

- **ONE item/cycle** — fix one PR issue, then stop
- **Never merge PRs** — humans merge after CI green
- **Close the bot fix PR** when its Renovate PR is merged or closed (Priority 4). Never close the Renovate PR. Never delete the fork branch.
- **After handoff**, communicate and repair CI on the **fix PR** only; Renovate PR is lifecycle + initial discovery.
- **Never create Jira tickets** or use Jira MCP tools
- **Never modify `.github/workflows/`**
- **Ignore Renovate bot comments** as actionable feedback (`renovate[bot]` is a bot author)
- **Do NOT re-fetch** data already in preflight input
- Reload `personas/frontend/prompt.md` before fixing nxtcm-components
- Use `gh pr comment` for human-facing updates (normal language, not caveman mode)
- If the fix PR drifts from main, rebase the fork tip and push; next cycle uses fix-PR CI FAILING if checks stay red
