"""Kafka adapter: portable model → Kafka topics/configs, prefixed ACLs, consumer groups, SR subjects.

Kafka has no tenant/namespace, so both become a topic-name prefix (`<tenant>.<namespace>.`),
namespace settings become per-topic defaults, and namespace permissions become PREFIXED ACLs.
"""
from __future__ import annotations

from typing import Any

from schema.models import Retention, TenantConfig

from .base import Backend, Change, Resource, nbytes, seconds


class KafkaBackend(Backend):
    protocol = "kafka"
    capabilities = frozenset({"compaction"})

    def desired(self, cfg: TenantConfig) -> list[Resource]:
        t = cfg.tenant
        out: list[Resource] = []
        for ns_name, ns in cfg.namespaces.items():
            prefix = f"{t}.{ns_name}."
            ops: dict[str, set[str]] = {}
            for p in ns.permissions.produce:
                ops.setdefault(p, {"DESCRIBE"}).add("WRITE")
            for p in ns.permissions.consume:
                ops.setdefault(p, {"DESCRIBE"}).add("READ")
            out += [Resource("grant", f"topic-prefix:{prefix}:{p}", {"operations": sorted(o)}) for p, o in ops.items()]

            for topic_name, topic in ns.topics.items():
                key = f"{prefix}{topic_name}"
                configs: dict[str, Any] = {
                    **ns.native.get("kafka", {}),
                    **_retention(ns.retention, topic.retention),
                    **topic.native.get("kafka", {}),
                }
                if topic.max_message_size:
                    configs["max.message.bytes"] = nbytes(topic.max_message_size)
                out.append(Resource("topic", key, {"partitions": topic.partitions, "configs": configs}))

                for s in topic.subscriptions:
                    group = f"{t}.{s.name}"
                    out += [Resource("grant", f"group:{group}:{c}", {"operations": ["READ"]}) for c in s.consumers]
                if topic.message_schema:
                    out.append(Resource("schema", f"{key}-value", topic.message_schema.model_dump(exclude_none=True)))
        return out

    def live(self, cluster: dict[str, Any], tenant: str) -> list[Resource]:
        raise NotImplementedError("demo: read via Kafka AdminClient + Schema Registry")

    def apply(self, cluster: dict[str, Any], change: Change) -> None:
        raise NotImplementedError("demo: mutate via Kafka AdminClient + Schema Registry")


def _retention(ns: Retention | None, topic: Retention | None) -> dict[str, int]:
    time = (topic and topic.time) or (ns and ns.time)
    size = (topic and topic.size) or (ns and ns.size)
    spec = {}
    if time:
        spec["retention.ms"] = seconds(time) * 1000
    if size:
        spec["retention.bytes"] = nbytes(size)
    return spec
