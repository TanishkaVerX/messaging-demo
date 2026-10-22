# messaging-demo

Sandbox for trying out the repository structure proposed in
[`roadmap-new-repo-eu-priority.md`](https://github.com/vertexinc/gala-pulsar-env-deployment/blob/develop/docs/roadmap-new-repo-eu-priority.md)
for `vcp-messaging-resources` — a backend-agnostic, single-branch repo for provisioning
messaging resources (tenants, namespaces, topics, subscriptions, permissions) across stamps,
on **any** messaging platform (Pulsar today; Kafka, Event Hubs, etc. as teams adopt them).

## Structure

```
messaging-demo/
├── platform/                  # Platform-team owned (CODEOWNERS-protected)
│   ├── stamps.yml             # stamp (us, eu) → protocol → backends (pulsar-4x, msk-3x, ...) → clusters
│   ├── backend-routing.yml    # per-tenant backend overrides during backend migrations
│   ├── defaults.yml           # org-wide defaults, generated from live cluster state then reviewed
│   ├── defaults.eu.yml        # EU-specific overrides
│   └── geo-replication-exceptions.yml
├── tenants/
│   └── <tenant>/config.yml    # one file per tenant: owner, contacts, protocol, stamps, client IDs,
│                              # namespaces, topics, permissions (only deviations from defaults)
├── schema/
│   ├── models.py              # portable Pydantic models — source of truth for validation
│   └── tenant-config.schema.json  # generated from models.py
├── messaging_deploy/          # CLI: validate, plan, apply, audit, monitors, scaffold-tenant, migrate
│   ├── config/                # load configs, merge defaults, resolve names → client IDs
│   ├── backends/              # one adapter per protocol, all implementing backends/base.py
│   │   ├── base.py            # Backend interface + capability model
│   │   ├── pulsar.py          # portable model → Pulsar tenants/namespaces/topics/policies
│   │   └── kafka.py           # portable model → Kafka topics/configs/ACLs/consumer groups
│   ├── engine/                # generic diff (desired vs live), plan, apply — backend-independent
│   ├── stamps/                # stamp → backend → cluster resolution
│   ├── monitors/              # Datadog monitor generation
│   └── migrate/               # convert legacy gala-pulsar-env-deployment configs
├── datadog/                   # monitor templates per protocol (pulsar/, kafka/) + per-env thresholds
├── .github/
│   ├── workflows/             # validate.yml (PR), plan.yml (PR comment), deploy.yml (gated promotion)
│   └── CODEOWNERS             # generated from tenant configs + platform/ ownership
└── docs/
```

## Key concepts

- **Stamp** — data-residency zone (`us`, `eu`); the only location concept tenants declare.
  **Region** means a cloud region (`us-east-2`, `eu-central-1`) and is resolved by the platform.
- **Protocol** — the client wire protocol a tenant codes against (`pulsar`, `kafka`). Declared by the
  tenant, because application SDKs are protocol-specific and cannot be swapped transparently.
- **Backend** — a concrete deployment of a protocol (`pulsar-4x`, `pulsar-5x`, `msk-3x`,
  `eventhubs-kafka`); version, vendor and cloud are hidden from tenants.
- **Single branch (`main`)** — environments (`dev` → `qa` → `stage` → `prod`) are promoted via
  gated GitHub Environments, dispatched with independent `stamp` and `target_env` inputs.
- **Plan/apply** — every change is diffed against live cluster state before it is applied.
- **Monitors** — created per environment right after each deploy; `contacts.oncall` is required.

## Backend abstraction

The repo must serve teams on Pulsar, Kafka, or any future messaging platform without changing
the tenant config format or the engine. The design has four layers:

```
tenants/<t>/config.yml        portable model (protocol-neutral names and units)
        │  validate: schema + capability check against the tenant's protocol
        ▼
backends/<protocol>.py        translate desired config → native resources
        │  read live state → same native resource shape
        ▼
engine/                       generic diff by (kind, key, spec) → plan.json
        ▼
backends/<protocol>.py        apply each change via the native admin API
```

### 1. Portable config model

Tenant configs use neutral concepts, names and units:

| Portable concept | Pulsar | Kafka |
|---|---|---|
| `tenant` | tenant | topic-name prefix + ACL principal scope |
| `namespace` | namespace | topic-name prefix `<tenant>.<namespace>.`; namespace settings become per-topic defaults |
| `topic` | `persistent://<tenant>/<namespace>/<topic>` | topic `<tenant>.<namespace>.<topic>` |
| `partitions` | partitioned topic | partitions |
| `retention: {time, size}` | retention policy (minutes / MB) | `retention.ms` / `retention.bytes` |
| `max_message_size` | `maxMessageSize` | `max.message.bytes` |
| `subscriptions` | subscription | consumer group (+ READ ACL on group) |
| `permissions.produce/consume` | namespace `grant-permission` | PREFIXED ACLs (WRITE / READ) |
| `schema: {type, compatibility}` | schema registry on topic | Schema Registry subject `<topic>-value` |

Units are human-readable (`7d`, `2GiB`) and converted by each adapter.

### 2. Capabilities, not lowest common denominator

Each backend declares the optional features it supports (e.g. `ttl`, `delayed_delivery`,
`dispatch_rate` for Pulsar; `compaction` for Kafka). `validate` rejects a tenant config that uses a
feature its protocol does not support — so portable configs never silently lose settings.

### 3. Native escape hatch

Settings with no portable equivalent go under `native.<protocol>` on a namespace or topic. They are
passed through untouched by the engine, validated by that protocol's adapter, and ignored by others:

```yaml
topics:
  orders:
    partitions: 3
    retention: { time: 7d }
    native:
      pulsar: { isGlobal: true }
```

If the same `native` setting appears in many tenants, promote it to the portable model.

### 4. Routing by protocol

Tenants declare `protocol` and `stamps`; `platform/stamps.yml` resolves them to backends and clusters.
A new platform (e.g. Event Hubs via its Kafka endpoint, or Pulsar 5.x) is added by registering a
backend under the right protocol — no tenant config changes. A new *protocol* (e.g. RabbitMQ/AMQP) is
added by writing one adapter in `backends/` and one monitor template set in `datadog/`.

### Monitors

Monitor kinds are portable (`backlog`/`lag`, `no_consumers`, `publish_absent`, `error_rate`);
`datadog/<protocol>/` maps each kind to that protocol's metrics (e.g. `pulsar.msg_backlog` vs.
`kafka.consumer_lag`).

## Out of scope

Connectors, Pulsar Functions, and Gala (Pulsar 3.x).

## Proposed changes vs. the original roadmap

This demo keeps the roadmap's direction (new repo, single branch, live-state-derived defaults,
zero-diff migration gate, stamps) but proposes the following adjustments:

### Tooling
- **Evaluate buy vs. build before writing a custom plan/apply engine.** Compare
  `streamnative/terraform-provider-pulsar` and the StreamNative `pulsar-resources-operator`
  (GitOps via ArgoCD) against a bespoke CLI. Custom code may only be needed for orphan
  detection and cross-backend equivalence checks. Terraform has providers for both Pulsar and
  Kafka, so adapters could emit Terraform instead of calling admin APIs directly.
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
- **Make the abstraction real, not just naming.** The roadmap's sample config uses Pulsar-only
  fields (`maxProducersPerTopic`, `subscription_auth_mode`, `encryption_required`), so it is not
  actually backend-agnostic. Adopt the portable model + capability check + `native.<protocol>`
  escape hatch + per-protocol adapters described in [Backend abstraction](#backend-abstraction).
- **Tenants declare `protocol`** (`pulsar` / `kafka`). Client SDKs are protocol-specific, so the
  protocol can't be hidden; version, vendor and cloud still are.
- **Diff in native terms, generically.** Adapters translate both desired and live state into the
  same `(kind, key, spec)` resources, so `engine/` has no protocol-specific code.
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
