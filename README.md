**AI-Generated Content** — This document was drafted by an AI agent (GitHub Copilot) using the `gala-pulsar-env-deployment` repository and its roadmap (`docs/roadmap-new-repo-eu-priority.md`). It may contain inaccuracies or reasoning gaps.

**Human review is required before acting on any recommendation.** Report errors by opening an issue in this repository.

# messaging-demo

Prototype of **`vcp-messaging-resources`** — the GitOps repository that will replace `vertexinc/gala-pulsar-env-deployment` for provisioning Apache Pulsar 4.x (Vespa) resources: tenants, namespaces, topics, subscriptions, permissions, and their Datadog monitors.

This repository is the proving ground. The real `vcp-messaging-resources` repository is created **only after** this design and its implementation steps are reviewed and approved.

> **Demo only.** Tenants, client IDs, cluster URLs, audiences and principals here are synthetic. No credentials or internal endpoints are stored in this repository. Workflows run on GitHub-hosted runners against local Pulsar containers.

- **Jira:** project `CPEARES`, label `ares-vcp-messaging-repository-refactor`
- **Owning team:** `@vertexinc/cfs-ares` (Ares platform team)

## Status

**Phase 1 — design spikes and demo build.** Nothing is implemented yet; see [Roadmap](#roadmap).

## Why

`gala-pulsar-env-deployment` today:

- One branch per environment (`develop → qa → stage → main`); changes move by merging branches.
- Ansible roles call the Pulsar Admin API directly; there is no plan before apply.
- Per-tenant `host_vars/<tenant>/create/pulsar-env-changelist.yml` plus per-resource config JSONs.
- No defaults layer: omitted properties fall through to undocumented broker defaults.
- Hardcoded behaviours (`isGlobal=true` on topic policies, `0` / `{}` / `[]` as delete sentinels) and two latent bugs:
  - namespace schema policies can never move off the broker default;
  - `schemaValidationEnforced` cannot be set back to `false`.
- Adding a data-residency zone (EU) means more branches, inventory groups and shell matrices.

## Goals

- One config file per tenant, listing only deviations from platform defaults.
- `plan` before `apply`; the plan shows exactly what changes on each cluster.
- Single `main` branch; promotion per tenant, per environment, behind approvals. **Nothing is auto-promoted.**
- EU as a first-class stamp from day one; no replication between US and EU.
- Datadog monitors generated for every tenant and environment, routed to the tenant's on-call.
- An AI onboarding agent that takes a user from "I need a topic" to an open PR.
- Migration from `gala-pulsar-env-deployment` one tenant at a time, gated by a zero-diff `plan`.

## Non-goals

- Other messaging systems (Kafka, Event Hubs, …). **Pulsar only.** The only indirection is stamp → Pulsar backend version (4.x / 5.x) → cluster.
- Pulsar 3.x (Gala) — fully shut down, not considered.
- Pulsar IO connectors and Pulsar Functions.
- StreamNative `terraform-provider-pulsar` / `pulsar-resources-operator` — evaluated, not chosen (ADR-0001).

## Concepts

| Term | Meaning | Examples |
|---|---|---|
| Stamp | Data-residency zone; the only location level tenants declare | `us`, `eu` |
| Region | Cloud region hosting a cluster | `us-east-2`, `us-west-2`, `eu-central-1` |
| Environment | Promotion stage | `dev`, `qa`, `stage`, `prod` |
| Cluster | One Pulsar cluster for a stamp × environment × region | `us / prod / us-west-2` |
| Tenant | A team's Pulsar tenant and its config file | `tenants/demo-orders/config.yml` |

US clusters today: dev and qa in `us-east-2` only; stage and prod in `us-east-2` and `us-west-2`. EU clusters are coming.

## How it works

### Tenant config

`tenants/<tenant>/config.yml` declares:

- `owner` (GitHub team) and `contacts.oncall` (Datadog on-call handle) — both required;
- `contacts.teams` for non-paging notifications;
- `stamps` the tenant deploys to;
- `client_ids` keyed by stamp, then environment;
- namespaces, topics (`partitions` **required**), subscriptions and permissions;
- optional `regions` restriction (replaces `westRegionDisabled`; not the same as disabling geo-replication).

Consumers that are not tenants in this repo are named in `platform/principals.yml`. "Unset" and "explicitly `0`" are distinct — there are no magic sentinels.

### Defaults: enforce vs. inherit

`platform/defaults.yml` has two kinds of entries:

- **enforce** — written explicitly to every resource unless the tenant overrides it;
- **inherit** — recorded as the expected broker default and never written. `audit` warns when a cluster's effective value differs.

Broker defaults come from `pulsar-admin brokers get-runtime-config` and the Helm values in `cfs-pulsar-infra/charts/pulsar-cluster/values-*.yaml`, cross-checked against a live-state dump.

### CLI: `messaging-deploy`

| Command | Purpose |
|---|---|
| `validate` | Schema, owner, on-call handle, principal references, stamps/regions, geo-replication rule |
| `plan` | Desired vs. live state per cluster; human-readable and JSON output |
| `plan --offline` | Resolved desired state without credentials (used by the onboarding agent) |
| `apply` | Executes an approved plan; re-plans first and aborts if the result differs |
| `audit` | Drift, orphaned resources, inherited-default mismatches |
| `monitors` | Generates Terraform variables for Datadog monitors |
| `codeowners` | Generates `.github/CODEOWNERS` from tenant owners |
| `migrate` | Converts a tenant from the `gala-pulsar-env-deployment` format |

### Plan semantics

- `plan` compares **local** policies (what is set on the resource), not applied/effective values.
- A property that is neither declared nor enforced must be unset.
- Partition counts never decrease; deletions are flagged and need explicit confirmation.
- Global vs. local topic policies (legacy `isGlobal=true`) are handled per the outcome of spike SP-5.

### Promotion

1. Merge to `main` deploys to **dev** only.
2. A manual `promote` dispatch (`tenant`, `stamp`, `to_env`) deploys the commit tagged `<stamp>/<previous-env>/<tenant>`.
3. Stage and prod require approval through GitHub Environments.
4. After a successful apply, the tag `<stamp>/<to_env>/<tenant>` moves to that commit.

A change parked in qa never rides along with another tenant's prod release, because prod only ever receives the commit that passed stage for that tenant.

### Access control

- `CODEOWNERS` is generated from tenant owners; a ruleset on `main` requires code-owner review.
- `platform/` (`stamps.yml`, `defaults.yml`, `principals.yml`, `geo-replication-exceptions.yml`) is owned by `@vertexinc/cfs-ares`.
- **`override defaults`:** when a PR introduces a new deviation from enforced defaults, `validate` applies the `override defaults` label. A required `override-approval` check recomputes the deviation itself and passes only with an approving review from `@vertexinc/cfs-ares`. Removing the label does not unblock the PR.
- `@vertexinc/cfs-ares` is on the ruleset bypass list.
- No "PR author must be in the owning team" check — CODEOWNERS review covers it without blocking platform help or bots.

### Credentials (production repository)

- Two OAuth2 client-credentials clients per cluster: **read** (`plan`, `audit`) and **admin** (`apply`).
- Secrets come from 1Password (OP Connect) and GitHub Environment secrets. Admin credentials exist only in protected environments.
- PR plans cover dev and qa only and always run the tooling from the base branch; stage/prod plans run inside the `promote` job before approval.
- Workflows run on `[self-hosted, Standard]` runners. The demo uses GitHub-hosted runners and local Pulsar without auth.

### Monitors

- Terraform, reusing the `team-topic-monitors` module from `gala-pulsar-env-deployment`; inputs generated from tenant configs.
- One grouped multi-alert monitor per tenant × environment × stamp, grouped by topic and subscription — not one monitor per topic.
- Terraform state in S3 (`us-east-2`), one state per stamp × environment.
- A Datadog failure is a warning; it does not block promotion.
- The demo runs `terraform validate` / `plan` only.

### Migration from `gala-pulsar-env-deployment`

1. `messaging-deploy migrate` converts the tenant and writes every policy the old tool set explicitly.
2. `plan` must show zero changes in every environment.
3. The tenant is added to `deployment/playbook/exclude-hosts/vespa/<env>` in the old repo — the cut-over marker.
4. `apply` in the new repo refuses any tenant/environment the old repo still manages.

Before archiving the old repo, a home is decided for `pulsar-admin-stats-service`, `pulsar-data-offload-service`, `pulsar-topic-purge-tool`, the smoke/HA/geo-replication tests, and any live connectors/functions.

## Onboarding agent

A VS Code / Copilot custom agent (`messaging-onboarding`) that:

1. Asks about the use case: produce or consume, other consumers, message size and rate, ordering/partitions, retention, schema, US/EU, on-call handle.
2. Maps it to tenants, namespaces, topics, subscriptions and permissions, and explains which defaults apply.
3. Edits `tenants/<tenant>/config.yml` (from the template for new tenants).
4. Runs `validate` and `plan --offline` and explains the result.
5. Creates a branch and commit and opens a PR with the template filled in — asking before pushing.
6. Explains PR checks, the plan comment, approvals and how to request promotion.

Guardrails: never edits `platform/`, never runs `apply`, never handles secrets, blocks partition decreases, flags deletions for a human. v1 covers new resources and modifications.

## Repository layout (planned)

```text
platform/                 stamps.yml, defaults.yml, principals.yml, geo-replication-exceptions.yml
tenants/                  _template/, demo-orders/, demo-payments/
src/messaging_deploy/     CLI, models, Pulsar client, diff/apply/audit, monitors, migrate
tests/                    unit, end-to-end round trip, latent-bug regressions, legacy fixtures
datadog/                  team-topic-monitors module and root Terraform
.github/
  workflows/              validate, plan, override-approval, deploy-dev, promote, audit
  agents/ skills/         onboarding agent and skills
  CODEOWNERS              generated
  PULL_REQUEST_TEMPLATE.md, ISSUE_TEMPLATE/
docs/                     adr/, walkthrough.md
docker-compose.yml        three local Pulsar 4.x clusters (us-east-2, us-west-2, eu-central-1)
```

## Local development (planned)

Prerequisites: Docker, Python 3.12.

1. `docker compose up -d` — starts the local clusters.
2. `pip install -e .` — installs the CLI.
3. `messaging-deploy validate`, then `messaging-deploy plan --env dev --stamp us`.

## Architecture decisions

All **Proposed**; written in `docs/adr/` by SP-10.

| ADR | Topic |
|---|---|
| 0001 | Provisioning engine: custom Python CLI |
| 0002 | Diff semantics and enforce/inherit defaults |
| 0003 | Promotion through per-tenant environment tags |
| 0004 | Credentials: separate read and admin clients |
| 0005 | Access control and `override defaults` approval |
| 0006 | Monitors: grouped multi-alert in Terraform |
| 0007 | Migration cut-over marker (`exclude-hosts/vespa/<env>`) |
| 0008 | Tenant config shape and ownership |
| 0009 | Geo-replication, regions and global policies |

## Roadmap

Single engineer; timeline is flexible. Sizes: S ≈ 1 day, M ≈ 2 days, L ≈ 3 days.

### Phase 1 — design spikes and demo (~12 weeks)

Spikes that need real clusters run outside this repository; only sanitised findings are recorded here.

| ID | Item | Size | Blocked by | Week |
|---|---|---|---|---|
| SP-1 | Authenticate to Pulsar Admin in every Vespa environment | L | — | 1 |
| SP-2 | Read-only Pulsar admin role feasibility | M | — | 1 |
| SP-3 | Live-state dump prototype (local, global, applied policies) | L | SP-1 | 1–2 |
| SP-4 | Broker defaults from `get-runtime-config` and Helm values | M | SP-1 | 2 |
| SP-5 | `isGlobal` and local vs. global topic policies | M | SP-3 | 2 |
| SP-6 | Reproduce latent bugs from the old Ansible roles | S | SP-1 | 3 |
| SP-10 | Write ADR-0001 … ADR-0009 | M | SP-2…SP-5 | 3 |
| D-1 | Scaffold repository | S | SP-10 | 4 |
| D-2 | Local Pulsar 4.x clusters via docker-compose | M | D-1 | 4 |
| D-3 | Pydantic config models, loader, platform files | L | D-1 | 4–5 |
| D-4 | `validate` | M | D-3 | 5 |
| D-5 | Pulsar admin client (read side) | M | D-2 | 6 |
| D-6 | `plan` (diff engine) | L | D-3, D-5 | 6 |
| D-7 | `apply` | L | D-6 | 7 |
| D-8 | End-to-end round-trip and latent-bug tests | M | D-7, SP-6 | 7 |
| D-9 | `audit` | M | D-6 | 8 |
| D-10 | `plan --offline` | S | D-6 | 8 |
| D-11 | CODEOWNERS generation and check | S | D-3 | 8 |
| SP-7 | Prove GitHub mechanics (approval decline, tag promote, bypass, review-triggered check) | M | D-1 | 8 |
| D-12 | `override defaults` auto-label and approval check | M | D-11, SP-7 | 9 |
| D-13 | PR `validate` and `plan` workflows | M | D-6 | 9 |
| D-14 | Deploy to dev on merge and `promote` workflow | L | D-7, SP-7 | 9–10 |
| SP-8 | Grouped Datadog monitor design | M | — | 10 |
| D-15 | Monitors via Terraform | M | SP-8, D-3 | 10 |
| D-16 | `migrate` from legacy format | L | D-6 | 11 |
| SP-9 | Onboarding agent surface and tool permissions | S | — | 11 |
| D-17 | Onboarding agent | L | D-10, SP-9 | 11–12 |
| D-18 | PR template, issue form, walkthrough, sign-off | S | D-1 … D-17 | 12 |

Critical path: SP-1 → SP-3 → SP-5 → SP-10 → D-3 → D-6 → D-7 → D-14 → D-18.

### Phase 2 onward — `vcp-messaging-resources` (after sign-off, ~4–5 months)

| Epic | Scope |
|---|---|
| Repo & Access Foundation | Create the internal repo, port the demo, rulesets, GitHub Environments, OP Connect secrets |
| Live State & Defaults | Full dump of all clusters, cross-cluster comparison, generate and review `defaults.yml`, zero-diff on sample tenants |
| Provisioning Tooling | OAuth2, real `stamps.yml`, global/local policy handling, parity with Ansible roles, sandbox round trip |
| CI/CD & Promotion | Self-hosted runners, PR plans, end-to-end promote through prod, weekly audit |
| Observability | Datadog Terraform backends, monitors for pilot tenant, routing, retire duplicate old monitors |
| Tenant Migration | Runbook, pilot tenant, batches of ~5 tenants, onboarding agent rollout |
| EU Enablement | EU stamp, auth, environments, defaults check, first EU tenant (when EU infra is ready) |
| Old Repo Decommission | Relocate Java services and tests, hand off connectors/functions, archive `gala-pulsar-env-deployment` |

Critical path: demo sign-off → repo and environments → OAuth2 → live dump → `defaults.yml` review → zero-diff → pilot tenant → migration batches → archive.

## Contributing

Branch from `main`, change your tenant config, open a PR. CI runs `validate` and `plan`. Code owners approve; changes that override defaults also need `@vertexinc/cfs-ares` approval. After merge, the change deploys to dev; promote further with the `promote` workflow.
