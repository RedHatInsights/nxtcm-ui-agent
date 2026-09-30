# nxtcm-ui-agent Instance — Additional Instructions

## Version Management

This instance has **nvm** (Node) version manager installed. Use it to match the version required by each repo.

### Node.js (nvm)

Before working on a repo with `package.json`, check its `.nvmrc` or `engines.node` field and switch if needed:

```bash
nvm use          # reads .nvmrc if present
nvm install 20   # install + switch to Node 20
nvm use default  # back to default (22)
```

Default: Node.js 22 LTS. Available globally via `/usr/local/bin/node`.

**nxtcm-components requires Node >=24.15** (see `package.json` `engines.node`). Always use Node 24 for this repo:

```bash
nvm install 24
nvm use 24
```

### When to switch

- `nxtcm-components` repo → always `nvm use 24`
- `.nvmrc` says `20` → `nvm use 20` (installs automatically if missing)
- No version file → use the defaults (22)

## Dependency Synchronization

- After every branch checkout or switch, activate the repository's required Node version and run `npm ci` from the repository root before doing any other work. This includes returning to an existing task for PR review feedback and temporary branch switches for visual comparisons.
- Before running tests, confirm that `npm ci` completed successfully after the most recent branch checkout. A failed `npm ci` is a hard stop: do not test, build, or modify code; report the failure.

## Verification override (nxtcm-components)

For visual verification, reload and follow `personas/frontend/prompt.md` (overrides jira-sprint visual steps).
