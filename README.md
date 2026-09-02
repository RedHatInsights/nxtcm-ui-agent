# nxtcm-ui-agent

Custom bot runner instance built on [dev-bot](https://github.com/RedHatInsights/platform-frontend-ai-dev).

## Architecture

Uses dev-bot as a git submodule. The submodule ships `Dockerfile.runner` which builds the full bot image and runs instance-specific customization hooks from this repo.

```
nxtcm-ui-agent/
├── dev-bot/        # Git submodule (don't modify)
├── setup.sh        # Custom build steps (dnf install, pip install, etc.)
├── instance/       # Extra files COPYed into the image
└── README.md
```

No Dockerfile in this repo — Konflux points at `dev-bot/Dockerfile.runner`.

## Build

```bash
git submodule update --init --recursive
docker build -f dev-bot/Dockerfile.runner -t nxtcm-ui-agent:local .
```

## Bot Instances

This runner ships two instance configs:

| Config path | Deployment | Workflow | Purpose |
|-------------|------------|----------|---------|
| `instance/ui-config/` | `devbot-console-next` | `jira-sprint` | Jira tickets with label `hcc-ai-nxtcm` |
| `instance/renovate-config/` | `devbot-rehor-renovate-patch` | `renovate-fix` | Failing Renovate PRs on `nxtcm-components` |

See [docs/renovate-bot-deployment.md](docs/renovate-bot-deployment.md) for OpenShift parameters for the Renovate bot.

## Customization

- **setup.sh** — runs as root during build. Install packages, write config, etc.
- **instance/** — files COPYed to `/home/botuser/app/instance/` in the image.

## Updating dev-bot

```bash
cd dev-bot && git pull origin master && cd ..
git add dev-bot
git commit -m "chore: update dev-bot submodule"
```

## Konflux

```yaml
dockerfile: dev-bot/Dockerfile.runner
path-context: .
```
