"""Backend interface. Every messaging protocol implements this; the engine only sees Resource/Change."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from schema.models import TenantConfig

Kind = Literal["tenant", "namespace", "topic", "subscription", "grant", "schema"]


@dataclass(frozen=True)
class Resource:
    kind: Kind
    key: str  # native identifier, e.g. persistent://t/ns/topic or t.ns.topic
    spec: dict[str, Any] = field(default_factory=dict, hash=False)


@dataclass(frozen=True)
class Change:
    action: Literal["create", "update", "delete"]
    resource: Resource
    before: dict[str, Any] | None = None


class Backend(ABC):
    protocol: str
    capabilities: frozenset[str] = frozenset()  # optional portable features this protocol supports

    def validate(self, cfg: TenantConfig) -> list[str]:
        """Reject portable features this protocol can't honour, so nothing is silently dropped."""
        errors = []
        for ns_name, ns in cfg.namespaces.items():
            for t_name, t in ns.topics.items():
                if t.ttl is not None and "ttl" not in self.capabilities:
                    errors.append(f"{ns_name}/{t_name}: 'ttl' not supported by {self.protocol}")
        return errors

    @abstractmethod
    def desired(self, cfg: TenantConfig) -> list[Resource]:
        """Translate the portable config into native resources."""

    @abstractmethod
    def live(self, cluster: dict[str, Any], tenant: str) -> list[Resource]:
        """Read live state into the same native resource shape as desired()."""

    @abstractmethod
    def apply(self, cluster: dict[str, Any], change: Change) -> None:
        """Execute one change via the native admin API."""


_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_BYTES = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}


def seconds(value: str) -> int:
    n, unit = re.match(r"(\d+)(\w+)", value).groups()
    return int(n) * _UNITS[unit]


def nbytes(value: str) -> int:
    n, unit = re.match(r"(\d+)(\w+)", value).groups()
    return int(n) * _BYTES[unit]
