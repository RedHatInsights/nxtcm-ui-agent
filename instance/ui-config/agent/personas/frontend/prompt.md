## Frontend Guidelines — nxtcm-components

npm workspaces monorepo. Shared React component library for Red Hat ACM/OCM console UIs. PatternFly 6, TypeScript 5, React 18.

### Packages

| dir | npm name | purpose |
|-----|----------|---------|
| `packages/nxtcm-dashboard` | `@redhat-cloud-services/nxtcm-dashboard` | ACM/OCM home dashboard widgets |
| `packages/nxtcm-rosa-hcp-wizard` | `@redhat-cloud-services/nxtcm-rosa-hcp-wizard` | ROSA HCP cluster creation wizard |

### Before changes
- After every branch checkout or switch, make sure you are running the project's Node.js version, then run `npm ci` from the repository root before doing any other work. This includes returning for PR review feedback and temporary visual-comparison branch switches.
- Before tests, confirm that `npm ci` succeeded after the most recent branch checkout; run it first if not. Fails → STOP, report on Jira, do not proceed.
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

New components go under `packages/*/src/`:

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
- Shared console UI used across features → `packages/nxtcm-dashboard/src/` or `packages/nxtcm-rosa-hcp-wizard/src/`

### Path aliases
- `@/` → `src/`
- `@patternfly-labs/react-form-wizard` → `packages/react-form-wizard/src`
- `@redhat-cloud-services/nxtcm-dashboard` → `packages/nxtcm-dashboard/src`
- `@redhat-cloud-services/nxtcm-rosa-hcp-wizard` → `packages/nxtcm-rosa-hcp-wizard/src`

Configured in: `tsconfig.json`, `vite.config.ts`, `playwright-ct.config.ts`, `.storybook/main.ts`, `jest.config.js` (`@/` only).

### Visual change detection

Before verification, decide if the ticket introduces **visual changes** (screenshots required on PR).

**Visual change** — screenshots required if any modified/added file lives under `packages/*/src/` and is not excluded below.

**Non-visual** — skip screenshots (still run full test suite) if every changed file under `packages/*/src/` is one of:
- A test or spec file: `*.test.ts`, `*.test.tsx`, `*.spec.ts`, `*.spec.tsx`
- A spec-helper: `*.spec-helpers.tsx`
- A fixture file: `*.fixtures.ts`

Also non-visual: dependency-only bumps, config/CI (`vite.config.ts`, `playwright*.config.ts`, etc.), docs, `scripts/`, `utils/`, `types/`, or changes that touch nothing under `packages/*/src/`.

When unsure → treat as visual.

### Verification — MANDATORY before PR

**This is a component library. No HCC dev-proxy, no SSO login, no live console environment.**

**Order — all steps are mandatory, run sequentially:**

1. `npm run lint` — lint `packages/**/*.{ts,tsx}`
2. `npm run type-check` — root + workspace TypeScript
3. `npm run test:all` — jest + Playwright CT (**jest does NOT run in CI** — always run locally before PR)
4. `npm run build` — root library
   - When changing a workspace package, also run: `npm run build -w @redhat-cloud-services/nxtcm-dashboard` or `npm run build -w @redhat-cloud-services/nxtcm-rosa-hcp-wizard`
5. **Run visual change detection** (see section above). If the change is visual: capture Storybook screenshots and upload them before opening the PR. If non-visual: write `N/A — no visual changes` in the PR Screenshots section. Either way, do not skip this step.
6. Push branch and open PR with Screenshots section populated.

### Playwright CT (component tests)

Primary test method. Matches `packages/nxtcm-*/src/**/*.spec.tsx`.

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
    ]
  }
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

1. **Start Storybook** (after `npm ci`, Node 24):
   ```bash
   nohup npm run storybook > /tmp/storybook.log 2>&1 &
   ```
   Wait for readiness — poll `/tmp/storybook.log` for "Local:" or use chrome-devtools `wait_for` on story content.

2. **Find story URL** — resolve which story renders the change (do not require a story-file diff):

   **Discovery order — MUST follow all steps before giving up:**
   1. Co-located story — if you changed `Foo.tsx` / `Foo.spec.tsx`, look for `Foo.stories.tsx` next to it (even if that story file was not modified).
   2. **Else traverse upward through the import graph** (max 3 levels). Starting from the changed file(s), find what imports them and repeat — stopping when you find files with a co-located `*.stories.tsx`:
      ```bash
      grep -rl "fileBaseName" packages/ --include="*.ts" --include="*.tsx" | grep -v "\.spec\.\|\.spec-helpers\.\|\.test\.\|\.fixtures\.\|\.stories\.\|index\."
      ```
      Replace `fileBaseName` with the changed file's name minus its extension. For each result that has a co-located story, use that story. For results without a story, run the grep again using *their* basenames — but skip `index.ts` / `index.tsx` files (barrel files fan out too broadly). Stop after 3 levels whether or not stories are found.
   3. **Else consumer stories** — if traversal found no stories, run a name-grep as a fallback:
      ```bash
      grep -rl "ComponentName" packages/ --include="*.stories.tsx"
      ```
      Replace `ComponentName` with the changed component's name. If the grep returns files:
      - **One result** → use it.
      - **Multiple results** → pick the file that shares the most path segments with the changed file (same package first, then same subdirectory). If the change visibly affects multiple distinct UIs (e.g. a shared component used across several steps), screenshot each relevant story and note which stories were captured in the PR. Otherwise screenshot only the closest match.
   4. Else no Storybook coverage — only reach this if all steps above returned nothing. Write `N/A — no Storybook coverage` in the PR Screenshots section. Do not invent a story URL.

   **Build the iframe URL** from the chosen `*.stories.tsx`:
   - CSF3 `title` → story ID: lowercase, `/` → `-` (e.g. `Components/Dashboard/Widget` → `components-dashboard-widget`)
   - Variant → first named export, kebab-cased (often `--default`)
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
- Visual change but no Storybook coverage → `N/A — no Storybook coverage`

### Coding standards

- PascalCase for file names and React components. camelCase for functions/variables.
- Functional components only. Export prop interfaces alongside the component.
- `onValueChange` over `useEffect` for reacting to form value changes (react-form-wizard pattern).
- No `console.log` in component code (`no-console: error`). Relaxed in `*.stories.tsx` only.
- Prefer Playwright CT (`*.spec.tsx`) over Jest for component tests. Co-locate test files next to the component.
