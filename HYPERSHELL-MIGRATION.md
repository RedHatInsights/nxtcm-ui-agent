# HyperShell migration prep: Console Next UI agent

**Status: preparation only.** This document records a proposed UI-only migration for REHOR-182. It does not authorize a cutover. No live resources were changed, and no runner or dispatcher image was promoted as part of this preparation.

## Scope and invariants

- Migrate only the Console Next UI agent to dispatcher-managed execution. Leave the legacy [`deploy/template.yaml`](deploy/template.yaml), including its KEDA scaler, and the Renovate workflow unchanged.
- Preserve the UI agent's existing GitOps-provided identity. The source of live overrides is the rendered app-interface entry `nxtcm-ui-agent` in `data/services/insights/platform-frontend-ai-dev/deploy.yml` (verified locally in GitOps): Jira label `hcc-ai-nxtcm`, board `Console Next Sprint Board`, sprint prefix `Console Next Sprint`, backlog `true` (the app-interface override wins; the template's `false` default must not override it), and the GitOps-supplied instance ID, config repo, and config path. The template defaults in [`deploy/template.yaml`](deploy/template.yaml) apply only when app-interface does not override them. Keep any credentials outside this repository and documentation.
- Preserve the legacy schedule: `America/New_York`, weekdays, 09:00–18:00. The legacy template's base replica setting is `0`, but its KEDA cron scaler raises the deployment to one replica during that window. A desired replica count of zero alone does not mean the legacy agent is inactive.
- Dispatcher discovery covers both profiles in this repository. Keep Renovate discoverable but inert: give its profile an explicit compatible image, carry its existing GitOps identity in `env` (the dispatcher validates the instance identity before evaluating the preflight list, including empty lists), and declare `preflights: []`. The empty preflight list must result in no scripts/no actionable start, so the dispatcher cannot launch its sandbox. Do not port, rewrite, or remove the legacy Renovate workflow or its preflight implementation.

The profile locations are [`instance/ui-config/agent/instance.yaml`](instance/ui-config/agent/instance.yaml) and [`instance/renovate-config/agent/instance.yaml`](instance/renovate-config/agent/instance.yaml). The Renovate workflow is under [`instance/renovate-config/agent/workflows/renovate-fix/`](instance/renovate-config/agent/workflows/renovate-fix/). For dispatcher behavior, see the submodule's [instance configuration](dev-bot/docs/presets/instance-config.md), [scheduling](dev-bot/docs/scheduling.md), and [deployment/rollback guide](dev-bot/docs/agent-dispatcher-deployment.md).

## Readiness gates before any cutover

1. **Dispatcher compatibility:** verify the dispatcher supports the required changes from Rehor #668 and #674, using the agreed source pin `a113ed3`. Do not infer compatibility from a floating branch or image tag.
2. **Published runner image:** confirm a published image compatible with the profile and dispatcher exists. Image publication/promotion is a separate gate; this prep does not promote an image.
3. **Profile validation:** verify dispatcher discovery accepts both profiles, preserves the UI settings and schedule, and treats Renovate's explicit empty preflight list as inert (`no-scripts`, with no sandbox launch).
4. **Tooling checks:** test the required MCP integration and npm setup against the candidate runner image — Node 24/Playwright, local Chromium, and the PatternFly and Chrome MCP servers — and record the results.
5. **Cycle checks:** verify a no-work UI cycle does not start a sandbox, then verify one representative UI cycle behaves as expected in an approved test/canary context. Confirm cycle and cleanup results before considering cutover.
6. **Bot-assigned candidate coverage and Jira gateway:** the legacy candidate scan includes bot-assigned sprint and backlog tickets, while the current dispatcher `jira-sprint` preflight scans only unassigned tickets here because the deployment-provided Jira identity is not wired to its optional email input. Preserve the bot-assigned candidate path before cutover and verify it with a representative bot-assigned ticket. The live Jira gateway path must also be validated end to end.
7. **Screenshot upload (pre-cutover blocker):** a runtime audit verified the pinned dispatcher (`a113ed3`) has neither screenshot upload URL injection nor a sandbox route to the existing screenshot gateway. Wire screenshot upload through the authenticated gateway and sandbox policy before cutover, then verify an actual screenshot upload and the returned link in a representative visual UI cycle.
8. **Human review:** review GitOps diffs, identity/routing settings, schedule semantics, image references, and rollback readiness before changing any live deployment. The UI-only scope and the legacy KEDA interaction require explicit review.

Until every gate passes and an owner approves the cutover, leave live deployments untouched. Do not enroll the UI agent in both legacy polling and dispatcher execution at once.

## Rollback

If dispatcher execution must be stopped, remove this configuration repository from the dispatcher's configured repository list so neither profile is discovered. If the legacy UI deployment was changed during an approved cutover, restore its previous GitOps deployment configuration, including its prior schedule and identity. Verify dispatcher discovery is gone and legacy execution is restored before declaring rollback complete. Do not modify the legacy template as part of this prep.
