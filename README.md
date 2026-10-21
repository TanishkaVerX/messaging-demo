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
