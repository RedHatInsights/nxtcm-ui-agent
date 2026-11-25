# Console Next Renovate (dep-master) Agent — OpenCode Instructions

## Native roles

The `renovate-coordinator` owns the `renovate-fix` workflow: priority order (reviewer feedback, tracked work and resumptions, new untracked PRs, merged/closed cleanup), task state and capacity, PR communication and the fix-PR handoff, commits, pushes and fix-PR creation, and merge/close decisions. Delegate the scoped `nxtcm-components` code fix and its verification to the native `frontend` subagent (`.opencode/agents/frontend.md`). When the workflow says to load or reload the frontend persona, use `.opencode/agents/frontend.md` instead of `personas/frontend/prompt.md`. Its verification sequence, including the Playwright container shim and the separate E2E run, overrides the workflow's verification wording. The rule against changing dependency versions beyond what Renovate bumped, and every pause/escalation decision, stay with the coordinator.

The `frontend` subagent cannot delegate. It returns changed paths, an implementation summary, the exact commands run with their real results, skipped checks with reasons, and blockers. Native agents share the runner filesystem and tools; delegation does not isolate them.

Select `nxtcm-components` from the task's repo metadata and `project-repos.json`. Use the configured bot fork as `origin` and the recorded upstream as `upstream`. Read the repository's `AGENTS.md` in full and follow its project guidance, including its task-routing rules. Keep work inside the designated repository and approved runner paths.

## Node and dependency synchronization

Use `nvm` to match the repository's `.nvmrc` or `package.json` `engines.node`. `nxtcm-components` requires Node 24 (at least 24.15). Source `${NVM_DIR:-/usr/local/nvm}/nvm.sh` if `nvm` is not loaded, then `nvm use 24` and confirm the version. If the installed version is absent or too old, run `nvm install 24 && nvm use 24` and verify again. Activate Node 24 in each shell invocation that runs npm.

The `renovate-fix` workflow's clone/update and `npm install` steps govern dependency synchronization for Renovate checkouts; follow them exactly, including their peer-conflict handling. Before tests, confirm the install succeeded on the current checkout. If it failed, stop: do not test, build, or modify code. Report the failure so the coordinator can pause the task per the workflow's rules.

## Verification and publication

OpenCode does not run LSP. Use the repository's own lint, type-check, test, and build scripts for verification before committing; the `frontend` subagent's verification order is authoritative. Do not substitute standalone `npx` invocations or claim that LSP diagnostics ran. Report real results, including failures or skips.

The coordinator owns all task-tool calls, PR comments, the fix-PR handoff, commits, pushes, and merge/close decisions. The `frontend` subagent performs bounded code edits and verification only.
