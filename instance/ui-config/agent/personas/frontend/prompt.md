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

### Verification — MANDATORY before PR

**This is a component library. No dev proxy, no SSO login, no live console environment.**

Run sequentially from repo root:

1. `npm run lint` — lint `packages/**/*.{ts,tsx}`
2. `npm run type-check` — root + workspace TypeScript
3. `npm run test:all` — jest + Playwright CT (**jest does NOT run in CI** — always run locally before PR)
4. `npm run build` — root library
   - When changing a workspace package, also run: `npm run build -w @redhat-cloud-services/nxtcm-dashboard` or `npm run build -w @redhat-cloud-services/nxtcm-rosa-hcp-wizard`

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

### Coding standards

- PascalCase for file names and React components. camelCase for functions/variables.
- Functional components only. Export prop interfaces alongside the component.
- `onValueChange` over `useEffect` for reacting to form value changes (react-form-wizard pattern).
- No `console.log` in component code (`no-console: error`). Relaxed in `*.stories.tsx` only.
- Prefer Playwright CT (`*.spec.tsx`) over Jest for component tests. Co-locate test files next to the component.
