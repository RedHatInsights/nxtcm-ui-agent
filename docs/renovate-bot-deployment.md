# Renovate Bot Deployment

Second bot deployment for the nxtcm-ui-agent runner image. Monitors failing Renovate PRs on `nxtcm-components` and auto-fixes minor/patch CI failures. Major version bumps receive a review-request comment only.

## Instance Config

| Path | Purpose |
|------|---------|
| `instance/renovate-config/agent/instance.yaml` | Workflow `./workflows/renovate-fix`, `source: scheduled` |
| `instance/renovate-config/agent/workflows/renovate-fix/` | Custom workflow (CLAUDE.md, preflight, manifest) |
| `instance/ui-config/agent/` | Existing Jira sprint bot (unchanged) |

Both deployments use the **same container image** built from this repo.

## OpenShift Parameters

Instantiate [`deploy/template.yaml`](../deploy/template.yaml) a second time in app-interface with these values:

| Parameter | UI bot (existing) | Renovate bot (new) |
|-----------|-------------------|---------------------|
| `BOT_NAME` | `devbot-console-next` | `Řehoř Renovate Assist` |
| `BOT_INSTANCE_ID` | `Řehoř řečený Stormbreaker` | `nxtcm-renovate` |
| `BOT_CONFIG_PATH` | `instance/ui-config` | `instance/renovate-config` |
| `BOT_CONFIG_REPO` | `https://github.com/RedHatInsights/nxtcm-ui-agent` | same |
| `BOT_LABEL` | `hcc-ai-nxtcm` | unused (same default) |
| `BOT_IMAGE` / `IMAGE_TAG` | same image | same image |
| KEDA cron | 9–6 ET weekdays | same (or increase frequency if desired) |

Configured in app-interface: [`data/services/insights/platform-frontend-ai-dev/deploy.yml`](https://gitlab.cee.redhat.com/service/app-interface/-/blob/master/data/services/insights/platform-frontend-ai-dev/deploy.yml) under resource template `nxtcm-renovate-agent`.

### Required env vars (Renovate bot)

- `BOT_INSTANCE_ID=nxtcm-renovate` — isolates task queue from UI bot
- `BOT_CONFIG_PATH=instance/renovate-config` — loads renovate workflow
- `BOT_CONFIG_REPO` — git URL for this repo (config pulled at startup)

No Jira board env vars required (`BOT_BOARD_NAME`, `BOT_SPRINT_PREFIX` are unused by the renovate workflow).

## Shared Infrastructure

Both bots share (deployed by `platform-frontend-ai-dev` in the same namespace):

- `devbot-proxy` — credentials, gh CLI, Squid
- `devbot-memory-server` — task tracking + dashboard
- `devbot-secrets` — git identity, tokens

## Local Testing

### Unit tests

```bash
cd nxtcm-ui-agent
PYTHONPATH=dev-bot/presets/shared/preflight \
  python3 -m pytest instance/renovate-config/agent/workflows/renovate-fix/tests/ -v
```

### Preflight (requires gh auth + memory server)

```bash
export BOT_INSTANCE_ID=nxtcm-renovate
# Symlink or copy project-repos.json to dev-bot root for local preflight CWD
cp instance/renovate-config/agent/project-repos.json dev-bot/project-repos.json

cd dev-bot
PYTHONPATH=presets/shared/preflight:../instance/renovate-config/agent/workflows/renovate-fix/preflight \
  python3 ../instance/renovate-config/agent/workflows/renovate-fix/preflight/01-renovate-discover.py | python3 -m json.tool
```

### CLAUDE.md assembly

```bash
cd dev-bot
BOT_CONFIG_PATH=../instance/renovate-config BOT_INSTANCE_ID=nxtcm-renovate \
  python3 bot/run.py --help  # or run assembly via entrypoint in container
```

## Workflow Behavior Summary

1. **Preflight** discovers open Renovate PRs with failing CI or merge conflicts on upstream repos from `project-repos.json`
2. **Major bumps** → PR comment asking reviewers to confirm; task set to `paused`
3. **Minor/patch bumps** → bot checks out PR branch, fixes CI, runs lint/type-check/test:all/build, pushes to Renovate head branch
4. **Merged PRs** → task archived, learnings stored in memory

Task keys: `renovate-fix:nxtcm-components#<pr-number>` with `source_type=github`.
