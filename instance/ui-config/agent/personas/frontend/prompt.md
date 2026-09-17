## Frontend Guidelines — nxtcm-components

npm workspaces monorepo. Shared React component library for Red Hat ACM/OCM console UIs. PatternFly 6, TypeScript 5, React 18.

### Packages

| dir | npm name | purpose |
|-----|----------|---------|
| root `src/` | `nxtcm-components` | shared console UI (breadcrumbs, page header, wizards) |
| `packages/nxtcm-dashboard` | `@redhat-cloud-services/nxtcm-dashboard` | ACM/OCM home dashboard widgets |
| `packages/nxtcm-rosa-hcp-wizard` | `@redhat-cloud-services/nxtcm-rosa-hcp-wizard` | ROSA HCP cluster creation wizard |

### Before changes
- `npm install` first. Fails → STOP, report on Jira, do not proceed.
- Read `AGENTS.md` in full — it is the canonical source of truth for this repo.

### Node version
- Requires Node >=24.15 (see `package.json` `engines.node`).
- `nvm install 24 && nvm use 24` before running any npm commands.

### Development
- PatternFly 6 components. Use `hcc-patternfly-data-view` MCP for docs/examples/source.
- TypeScript for all new code. No `any` — prefer `unknown`. Explicit return types on functions.
- LSP `get_diagnostics` before committing.
- **npm scripts only** — `npm test`, `npm run lint`, `npm run build`. Never `npx jest`/`npx eslint`/`npx tsc` directly. Check `package.json` for scripts.
- **NEVER run npm commands in parallel** — always sequential (OOMKill risk in container).
- **NEVER make HTTP calls from components** — use injected callbacks (`Resource<T>` pattern). Consuming apps supply data + loading + error state.

### File conventions (co-location)

New components go under `src/components/` or `packages/*/src/`:

```
ComponentName/
  ComponentName.tsx
  ComponentName.stories.tsx   # CSF3, tags: ['autodocs']
  ComponentName.spec.tsx      # Playwright CT — primary test
  ComponentName.test.ts       # Jest — only if pure logic warrants it
  index.ts
```

### Where to put new code
- Dashboard home widgets → `packages/nxtcm-dashboard/src/`
- ROSA HCP wizard steps/fields/validation → `packages/nxtcm-rosa-hcp-wizard/src/`
- Shared console UI used across features → `src/components/` or `src/utilities/`

### Path aliases
- `@/` → `src/`
- `@patternfly-labs/react-form-wizard` → `packages/react-form-wizard/src`
- `@redhat-cloud-services/nxtcm-dashboard` → `packages/nxtcm-dashboard/src`
- `@redhat-cloud-services/nxtcm-rosa-hcp-wizard` → `packages/nxtcm-rosa-hcp-wizard/src`

Configured in: `tsconfig.json`, `vite.config.ts`, `playwright-ct.config.ts`, `.storybook/main.ts`, `jest.config.js` (`@/` only).

### Visual change detection

Before verification, decide if the ticket introduces **visual changes** (screenshots required on PR).

**Visual change** — any of:
- Modified/added `*.tsx` component files (not test-only files unless rendered output changes)
- Modified/added `*.stories.tsx`, CSS/styling, or layout-related props
- Jira title/description/AC mentions UI, layout, styling, design, appearance, screenshot, visual
- New component or visible behavior change in an existing component

**Non-visual** — skip screenshots (still run full test suite):
- Pure logic in `*.ts` / `*.test.ts` with no component or story changes
- Dependency-only bumps, config/CI, docs-only
- Refactors with identical rendered output

When unsure → treat as visual.

### Verification — MANDATORY before PR

**This is a component library. No HCC dev-proxy, no SSO login, no live console environment.**

**Order:** implement → automated checks → [visual: Storybook screenshots + upload] → push → PR with Screenshots URLs.

Run sequentially from repo root:

1. `npm run lint` — lint `packages/**/*.{ts,tsx}`
2. `npm run type-check` — root + workspace TypeScript
3. `npm run test:all` — jest + Playwright CT (**jest does NOT run in CI** — always run locally before PR)
4. `npm run build` — root library
   - When changing a workspace package, also run: `npm run build -w @redhat-cloud-services/nxtcm-dashboard` or `npm run build -w @redhat-cloud-services/nxtcm-rosa-hcp-wizard`
5. **Visual changes only** — Storybook screenshots (see below). Upload before opening PR.

### Playwright CT (component tests)

Primary test method. Matches `src/**/*.spec.tsx` and `packages/nxtcm-*/src/**/*.spec.tsx`.

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
npm run test:ct
```

Patch `playwright-ct.config.ts` for container — add `launchOptions` to the `use` block:

```typescript
use: {
  launchOptions: {
    args: [
      '--no-sandbox',
      '--disable-gpu',
    ],
  },
}
```

Do NOT commit this patch — `git checkout -- playwright-ct.config.ts` after tests.

Run with `--workers=1` if resource errors occur.

### Playwright E2E

E2E tests use a local Vite dev server. No SSO or external proxy needed.

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
npm run test:e2e
```

### Storybook

Stories use CSF3. Title convention: `Components/<Category>/<ComponentName>`.

```bash
npm run storybook      # dev server on :6006
npm run build-storybook
```

Do NOT use Storybook as the only verification method. Always run `test:all` + `build`.

### Visual verification — Storybook + chrome-devtools

**MANDATORY for visual changes.** Use Storybook + `chrome-devtools` MCP — not HCC dev-proxy.

Same when reviewer asks for screenshots on an open PR.

#### Before screenshot timing

Capture **before** the first implementation commit (branch still matches main), or:
- `git stash -u` → checkout default branch → capture → checkout feature branch → `git stash pop`

#### Steps

0. **Kill stale Storybook**: `lsof -ti :6006 | xargs kill 2>/dev/null || true`

1. **Start Storybook** (after `npm install`, Node 24):
   ```bash
   nohup npm run storybook > /tmp/storybook.log 2>&1 &
   ```
   Wait for readiness — poll `/tmp/storybook.log` for "Local:" or use chrome-devtools `wait_for` on story content.

2. **Find story URL** — read the changed `*.stories.tsx`:
   - CSF3 `title` → story ID: lowercase, `/` → `-` (e.g. `Components/Dashboard/Widget` → `components-dashboard-widget`)
   - Default variant → `--default` (or read `export default { title: ... }` and first named export)
   - iframe URL: `http://127.0.0.1:6006/iframe.html?id=<story-id>--<variant>&viewMode=story`

3. **Navigate + screenshot** via chrome-devtools MCP:
   - `navigate_page` → story iframe URL
   - `wait_for` key text from the component
   - `take_screenshot` → save `/tmp/<TICKET-KEY>-before.png` (before changes) or `-after.png` (after changes)
   - Never commit screenshots to the repo. Never base64 data URIs in PR body.

4. **Upload to GitHub Releases** via `/gh-release-upload` skill (never `gh release upload` directly):
   ```bash
   python3 .claude/skills/gh-release-upload/upload.py /tmp/<TICKET-KEY>-before.png platex-rehor-bot/nxtcm-components
   python3 .claude/skills/gh-release-upload/upload.py /tmp/<TICKET-KEY>-after.png platex-rehor-bot/nxtcm-components
   ```
   Fork owner/repo from `project-repos.json` `url` field. Skill returns markdown image URLs.

5. **Stop Storybook** — mandatory: `lsof -ti :6006 | xargs kill`. Verify port is free.

#### PR Screenshots section

Upload screenshots **before** creating the PR. When using `/push-and-pr --find-template`:
- **Screenshots** → `### Before` + before URL, `### After` + after URL
- Non-visual change → `N/A — no visual changes`

### Coding standards

- PascalCase for file names and React components. camelCase for functions/variables.
- Functional components only. Export prop interfaces alongside the component.
- `onValueChange` over `useEffect` for reacting to form value changes (react-form-wizard pattern).
- No `console.log` in component code (`no-console: error`). Relaxed in `*.stories.tsx` only.
- Prefer Playwright CT (`*.spec.tsx`) over Jest for component tests. Co-locate test files next to the component.
