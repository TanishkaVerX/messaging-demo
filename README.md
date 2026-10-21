# messaging-demo

Sandbox for trying out the repository structure proposed in
[`roadmap-new-repo-eu-priority.md`](https://github.com/vertexinc/gala-pulsar-env-deployment/blob/develop/docs/roadmap-new-repo-eu-priority.md)
for `vcp-messaging-resources` — a backend-agnostic, single-branch repo for provisioning
messaging resources (tenants, namespaces, topics, subscriptions, permissions) across stamps.

## Structure

```
messaging-demo/
├── platform/                  # Platform-team owned (CODEOWNERS-protected)
│   ├── stamps.yml             # stamp (us, eu) → backend (pulsar-4x, ...) → clusters per env/cloud region
│   ├── backend-routing.yml    # per-tenant backend overrides during backend migrations
│   ├── defaults.yml           # org-wide defaults, generated from live cluster state then reviewed
│   ├── defaults.eu.yml        # EU-specific overrides
│   └── geo-replication-exceptions.yml
├── tenants/
│   └── <tenant>/config.yml    # one file per tenant: owner, contacts, stamps, client IDs,
│                              # namespaces, topics, permissions (only deviations from defaults)
├── schema/
│   ├── models.py              # Pydantic models — source of truth for validation
│   └── tenant-config.schema.json
├── messaging-deploy/          # CLI: validate, plan, apply, audit, monitors, scaffold-tenant, migrate
│   ├── config/                # load configs, merge defaults, resolve names → client IDs
│   ├── backends/              # backend interface + Pulsar Admin implementation
│   ├── engine/                # diff (desired vs live), plan, apply
│   ├── stamps/                # stamp → backend → cluster resolution
│   ├── monitors/              # Datadog monitor generation
│   └── migrate/               # convert legacy gala-pulsar-env-deployment configs
├── datadog/                   # monitor templates and per-environment thresholds
├── .github/
│   ├── workflows/             # validate.yml (PR), plan.yml (PR comment), deploy.yml (gated promotion)
│   └── CODEOWNERS             # generated from tenant configs + platform/ ownership
└── docs/
```

## Key concepts

- **Stamp** — data-residency zone (`us`, `eu`); the only location concept tenants declare.
  **Region** means a cloud region (`us-east-2`, `eu-central-1`) and is resolved by the platform.
- **Backend** — messaging platform/version (`pulsar-4x`, `pulsar-5x`); hidden from tenants.
- **Single branch (`main`)** — environments (`dev` → `qa` → `stage` → `prod`) are promoted via
  gated GitHub Environments, dispatched with independent `stamp` and `target_env` inputs.
- **Plan/apply** — every change is diffed against live cluster state before it is applied.
- **Monitors** — created per environment right after each deploy; `contacts.oncall` is required.

## Out of scope

Connectors, Pulsar Functions, and Gala (Pulsar 3.x).

## Proposed changes vs. the original roadmap

This demo keeps the roadmap's direction (new repo, single branch, live-state-derived defaults,
zero-diff migration gate, stamps) but proposes the following adjustments:

### Tooling
- **Evaluate buy vs. build before writing a custom plan/apply engine.** Compare
  `streamnative/terraform-provider-pulsar` and the StreamNative `pulsar-resources-operator`
  (GitOps via ArgoCD) against a bespoke CLI. Custom code may only be needed for orphan
  detection and cross-backend equivalence checks.
- **Generate the JSON Schema from the Pydantic models** (`model_json_schema()`) instead of maintaining both.
- **`apply` rejects stale plans** (hash of live state embedded in `plan.json`) rather than defaulting to dry-run.

### Defaults and diffing
- **Define what "zero diff" compares against** — local (explicitly set) vs. applied (effective) policies.
- **Split `defaults.yml` into `enforce` and `inherit`.** `enforce` values are written explicitly;
  `inherit` values are recorded for reference only and left unset, so inheritance and the
  hardcoded `isGlobal=true` behaviour don't turn every broker default into an explicit topic policy.
- **Source broker defaults cheaply** from `pulsar-admin brokers get-runtime-config` and the
  `cfs-pulsar-infra` Helm values, before dumping every topic.

### Backend abstraction
- **Be honest that the tenant config is Pulsar-shaped.** Keep abstraction at the
  stamp → backend → cluster routing layer (needed for 4.x → 5.x); defer Kafka until it is a real requirement.
- **Describe multi-backend apply as "partial failure reported"**, not atomic.

### Config format
- **`client_ids` keyed by stamp, then env** (`{us: {dev, qa, stage, prod}, eu: {...}}`, falling back to `us`),
  instead of fused keys like `eu-prod`.
- **A principals registry** for permission grants to consumers that are not tenants in this repo.
- **Ownership inline** (`owner:` in `config.yml`); no separate `tenant-owners.yml`.
- **Don't map `westRegionDisabled` to `geo_replication: false`** — "no resources on a cluster" and
  "no replication" are different settings.
- **Geo-replication mandate must match the cluster matrix** (e.g. EU stage has a single cluster).

### CI/CD and promotion
- **Promote a recorded SHA per tenant/env**, not `main` HEAD, so a change parked in qa isn't
  unintentionally shipped by a later prod dispatch for the same tenant.
- **Least-privilege credentials:** read-only admin role for `plan`/`audit`; apply credentials only
  in protected environments; PR plans run base-branch tooling code, not PR-modified code.

### Access control
- **Rely on CODEOWNERS + required code-owner review.** Drop the CI authorship check
  (blocks platform help and bots) and avoid duplicating CODEOWNERS with path Rulesets.
- **`CODEOWNERS` itself is platform-owned.**
- **Avoid platform approval on every tenant's prod deploy** to prevent a bottleneck.

### Observability
- **One monitor mechanism** — keep Terraform (already used for team topic monitors) fed from
  tenant config, rather than adding a parallel Python generator.
- **Multi-alert monitors grouped by tenant/namespace** (split by topic) instead of one monitor per
  topic × subscription × env × stamp × backend.
- **Monitor deploy failures warn rather than block** resource promotion.
- **Migrate existing per-tenant `monitors.yml`** along with changelists and configs.

### Migration and decommission
- **Reuse `exclude-hosts/vespa/<env>`** in the old repo as the cut-over marker instead of a
  cross-repo `MIGRATION_STATUS.md` check.
- **Plan a home for the Java services and tests** (`pulsar-admin-stats-service`, offload service,
  purge tool, smoke/HA/geo-rep tests) and for existing connectors/functions before archiving the old repo.
- **Reconcile "Gala stays in old repo" with "archive old repo in Month 4."**
- **Fix the two latent bugs in the old repo too** (schema policy never updating; `schemaValidationEnforced`
  irreversible) since it remains live for months.
- **Revisit the 16–20 week estimate** — Month 1 workstreams alone exceed ~12 engineer-weeks, and the EU
  Month 2 fast-track depends on a production-grade `apply` that is itself Month 2 work.
