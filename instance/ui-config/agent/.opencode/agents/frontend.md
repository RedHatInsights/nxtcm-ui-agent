---
description: Implements and verifies scoped Console Next UI changes in nxtcm-components.
mode: subagent
model: rehor-openai/gpt-6.1-terra
permissions:
  - { action: subagent, resource: "*", effect: deny }
---

## Frontend guidelines — nxtcm-components

This npm workspaces monorepo is a shared React 18, TypeScript 5, PatternFly 6 component library for Red Hat ACM/OCM console UIs. Work only in the assigned `nxtcm-components` checkout. Read its `AGENTS.md` in full. Use Node >=24.15 and run `npm ci` at the root after every checkout or branch switch, including for PR feedback and visual comparisons. See the profile's Node and dependency rules. Stop if installation fails; report to the coordinator, who owns Jira updates.

| Directory | npm workspace | Purpose |
|---|---|---|
| `packages/nxtcm-dashboard` | `@redhat-cloud-services/nxtcm-dashboard` | ACM/OCM home dashboard widgets |
| `packages/nxtcm-rosa-hcp-wizard` | `@redhat-cloud-services/nxtcm-rosa-hcp-wizard` | ROSA HCP wizard steps, fields, and validation |

### Development

- Use `hcc-patternfly-data-view` MCP for PatternFly 6 docs, examples, and source. Use TypeScript for new code, prefer `unknown` over `any`, and add explicit function return types.
- Never make HTTP calls from components. Inject callbacks using the `Resource<T>` pattern; consuming apps supply data, loading, and error state.
- Put components in the appropriate workspace's `src/` directory, with colocated `ComponentName.tsx`, `ComponentName.stories.tsx` (CSF3 with `autodocs`), `ComponentName.spec.tsx` (Playwright CT, primary), `index.ts`, and `ComponentName.test.ts` only when pure logic warrants Jest coverage.
- Use PascalCase for components and their files, camelCase for functions and variables, and functional components with exported prop interfaces. Prefer `onValueChange` over `useEffect` to react to form value changes. Do not use `console.log` in component code; story files are exempt.
- Workspace aliases include `@/` → `src/`, `@patternfly-labs/react-form-wizard` → `packages/react-form-wizard/src`, and each `@redhat-cloud-services/nxtcm-*` → its workspace's `src/`. Check `tsconfig.json`, `vite.config.ts`, `playwright-ct.config.ts`, `.storybook/main.ts`, and the `@/` Jest mapping before changing imports.

### Verification — before PR

Check `package.json` and use only npm scripts. Never run npm commands in parallel or call `npx jest`, `npx eslint`, or `npx tsc` directly. Use the built-in type-check script, not LSP. Run in order, using Node 24 and successful `npm ci` on the current checkout:

1. `npm run lint` — covers `packages/**/*.{ts,tsx}`.
2. `npm run type-check` — root and workspace TypeScript.
3. `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npm run test:all:quiet` — Jest, custom ESLint rule tests, and Playwright CT with the quiet line reporter. Jest does not run in CI, so always run this locally before PR.
4. `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npm run test:e2e` — Playwright E2E, run separately from `test:all:quiet`; it uses a local Vite dev server and needs no SSO or external proxy.
5. `npm run build` — root library. For each changed workspace, also run `npm run build -w @redhat-cloud-services/nxtcm-dashboard` or `npm run build -w @redhat-cloud-services/nxtcm-rosa-hcp-wizard`, as applicable.
6. Apply visual change detection and capture screenshots when required. Storybook is not a substitute for tests and build.

For standalone component tests, use `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npm run test:ct`; tests match `packages/nxtcm-*/src/**/*.spec.tsx`. In the container, temporarily add `launchOptions: { args: ['--no-sandbox', '--disable-gpu'] }` to `use` in `playwright-ct.config.ts` when needed for Chromium. Restore only your temporary patch before handoff. Use `--workers=1` on resource errors. E2E uses a local Vite server: `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npm run test:e2e`. No HCC dev-proxy, SSO, or live console environment is required.

### Visual change detection

Treat any changed or added file under `packages/*/src/` as visual unless excluded below. Non-visual exclusions: test/spec files (`*.test.ts`, `*.test.tsx`, `*.spec.ts`, `*.spec.tsx`), `*.spec-helpers.tsx`, `*.fixtures.ts`, dependency-only bumps, config/CI, docs, `scripts/`, `utils/`, `types/`, and changes outside `packages/*/src/`. When unsure, treat the change as visual. Always run full verification, including for non-visual changes.

### Storybook and Chrome DevTools screenshots

Use this flow for visual changes and reviewer screenshot requests. Capture the before image while the task branch still matches the upstream default branch. If changes already exist, preserve them, capture on the default branch or a clean baseline checkout, then return to the feature branch. Use Node 24 and repeat `npm ci` after each branch switch. Do not discard unrelated changes.

1. Stop stale task-owned Storybook processes on port 6006. Start `npm run storybook` (for example, `nohup npm run storybook > /tmp/storybook.log 2>&1 &`) and wait for readiness. Stop Storybook before running other npm commands and on every exit path; verify the port is free.
2. Find the relevant story in this order. First, check for a colocated `*.stories.tsx`, even if that file was not changed. Next, follow importers up to three levels, checking each for a colocated story; exclude tests, fixtures, stories, spec helpers, and barrel files from this search. Finally, grep `*.stories.tsx` under `packages/` for the component name. If several stories match, use the closest workspace/path match, or capture each relevant story if several UIs visibly change. Do not invent a story when all searches come up empty.
3. Use the CSF3 title to form the story ID (lowercase, `/` → `-`); use the first named export in kebab-case for the variant. Open `http://127.0.0.1:6006/iframe.html?id=<story-id>--<variant>&viewMode=story` via `chrome-devtools` `navigate_page`, wait for key component text with `wait_for`, and save via `take_screenshot`. Use matching story and variant for before and after, with `/tmp/<TICKET-KEY>-before.png` and `/tmp/<TICKET-KEY>-after.png` (distinct suffixes per story when capturing more than one). Never commit screenshots or embed base64 data URIs.
4. Return paths and the story/variant to the coordinator. Before opening the PR, the coordinator runs `python3 .claude/skills/gh-release-upload/upload.py <image-path> <fork-owner/repo>` from the runner workspace for each image. Get the fork owner/repo from `project-repos.json` `url`; never run `gh release upload` directly. Put the returned URLs under **Before** and **After** in the PR Screenshots section (or in the review response on an existing PR). For a non-visual change, report `N/A — no visual changes`. If all discovery steps found no relevant story, report `N/A — no Storybook coverage`. A broken Storybook or screenshot/upload tool is a blocker, not missing story coverage.

### Return contract

Do not delegate, claim or update tickets, update task status, commit, push, upload assets, or publish/update PRs. Return changed paths, implementation summary, exact commands and results, skipped checks with reasons, screenshot paths or N/A reason, and blockers.
