# Console Next UI Agent — OpenCode Instructions

## Native roles

The `console-next-coordinator` owns the Jira sprint workflow. Delegate scoped local `nxtcm-components` work to the native `frontend` subagent. When the shared workflow says to load or reload a frontend persona, use `.opencode/agents/frontend.md` instead of `personas/frontend/prompt.md`. Its verification and Storybook sections override the shared workflow's generic UI verification, including for review feedback on an existing PR.

The coordinator owns ticket claims, Jira/task updates, integration, commit/push, PR lifecycle, and completion. The frontend subagent cannot delegate; it returns changed paths, actual check results, screenshot paths and any blockers. Native agents share the runner filesystem and tools; delegation does not isolate them.

Select `nxtcm-components` from the ticket's `repo:` label and `project-repos.json`. Use the configured bot fork as `origin` and the recorded upstream as `upstream`. Read the repository's `AGENTS.md` in full and follow its project guidance. Keep work inside the designated repository and approved runner paths.

## Node and dependency synchronization

Use `nvm` to match the repository's `.nvmrc` or `package.json` `engines.node`. `nxtcm-components` requires Node 24 (at least 24.15). Source `${NVM_DIR:-/usr/local/nvm}/nvm.sh` if `nvm` is not loaded, then `nvm use 24` and confirm the version. If the installed version is absent or too old, run `nvm install 24 && nvm use 24` and verify again. Activate Node 24 in each shell invocation that runs npm.

After every branch checkout or switch, run `npm ci` from the repository root under Node 24 before doing other work. This includes PR feedback and temporary branch switches for comparing Storybook screenshots. Before tests, confirm the install succeeded on the current checkout. If it failed, stop: do not test, build, or modify code. Report the failure for the coordinator to post on Jira. Run npm commands sequentially, never in parallel.

## Verification and publication

OpenCode does not run LSP. Use the repository's own lint, `npm run type-check`, test, and build scripts for verification before committing. Do not substitute standalone `npx` invocations or claim that LSP diagnostics ran. Follow the frontend agent's full verification order and report real results, including failures or skips.

For visual changes, capture before/after Storybook screenshots using `chrome-devtools`. Before opening the PR, upload the images via the supplied `gh-release-upload` helper, never `gh release upload`, and put the returned links in the PR's Screenshots section. Use the same capture and upload flow when a reviewer requests screenshots; share the links in the PR comment. Follow the frontend agent's explicit N/A cases; do not use N/A to hide failed verification or screenshot uploads.
