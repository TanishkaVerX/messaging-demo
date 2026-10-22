"""Pulsar adapter: portable model → Pulsar tenants, namespaces, topics, subscriptions, grants."""
from __future__ import annotations

from typing import Any

from schema.models import TenantConfig

from .base import Backend, Change, Resource, nbytes, seconds


class PulsarBackend(Backend):
    protocol = "pulsar"
    capabilities = frozenset({"ttl", "delayed_delivery", "dispatch_rate"})

    def desired(self, cfg: TenantConfig) -> list[Resource]:
        t = cfg.tenant
        out = [Resource("tenant", t)]
        for ns_name, ns in cfg.namespaces.items():
            ns_key = f"{t}/{ns_name}"
            out.append(Resource("namespace", ns_key, {**_retention(ns.retention), **ns.native.get("pulsar", {})}))

            actions: dict[str, set[str]] = {}
            for p in ns.permissions.produce:
                actions.setdefault(p, set()).add("produce")
            for p in ns.permissions.consume:
                actions.setdefault(p, set()).add("consume")
            out += [Resource("grant", f"{ns_key}:{p}", {"actions": sorted(a)}) for p, a in actions.items()]

            for topic_name, topic in ns.topics.items():
                key = f"persistent://{ns_key}/{topic_name}"
                spec: dict[str, Any] = {"partitions": topic.partitions, **_retention(topic.retention)}
                if topic.max_message_size:
                    spec["maxMessageSize"] = nbytes(topic.max_message_size)
                if topic.ttl:
                    spec["messageTTL"] = seconds(topic.ttl)
                out.append(Resource("topic", key, {**spec, **topic.native.get("pulsar", {})}))
                out += [Resource("subscription", f"{key}:{s.name}") for s in topic.subscriptions]
                if topic.message_schema:
                    out.append(Resource("schema", key, topic.message_schema.model_dump(exclude_none=True)))
        return out

    def live(self, cluster: dict[str, Any], tenant: str) -> list[Resource]:
        raise NotImplementedError("demo: read via Pulsar Admin REST API")

    def apply(self, cluster: dict[str, Any], change: Change) -> None:
        raise NotImplementedError("demo: mutate via Pulsar Admin REST API")


def _retention(r) -> dict[str, int]:
    if r is None:
        return {}
    spec = {}
    if r.time:
        spec["retentionTimeInMinutes"] = seconds(r.time) // 60
    if r.size:
        spec["retentionSizeInMB"] = nbytes(r.size) // 1024**2
    return spec
