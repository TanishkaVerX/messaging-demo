"""Portable (protocol-neutral) tenant config model."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Protocol = Literal["pulsar", "kafka"]
Stamp = Literal["us", "eu"]

_DURATION = re.compile(r"^\d+(s|m|h|d)$")
_SIZE = re.compile(r"^\d+(B|KiB|MiB|GiB|TiB)$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _check(pattern: re.Pattern[str], value: Optional[str], what: str) -> Optional[str]:
    if value is not None and not pattern.match(value):
        raise ValueError(f"invalid {what}: {value!r}")
    return value


class Retention(Strict):
    time: Optional[str] = None  # None = inherit from defaults/backend
    size: Optional[str] = None

    @field_validator("time")
    @classmethod
    def _time(cls, v: Optional[str]) -> Optional[str]:
        return _check(_DURATION, v, "duration")

    @field_validator("size")
    @classmethod
    def _size(cls, v: Optional[str]) -> Optional[str]:
        return _check(_SIZE, v, "size")


class MessageSchema(Strict):
    type: Literal["avro", "json", "protobuf", "none"] = "none"
    compatibility: Optional[Literal["backward", "forward", "full", "none"]] = None
    ref: Optional[str] = None


class Subscription(Strict):
    """Pulsar subscription / Kafka consumer group."""
    name: str
    consumers: list[str]


class Permissions(Strict):
    produce: list[str] = []
    consume: list[str] = []


class Topic(Strict):
    partitions: int = Field(ge=1)  # required: cannot be decreased after creation
    retention: Optional[Retention] = None
    max_message_size: Optional[str] = None
    ttl: Optional[str] = None  # optional capability
    message_schema: Optional[MessageSchema] = Field(default=None, alias="schema")
    subscriptions: list[Subscription] = []
    native: dict[Protocol, dict[str, Any]] = {}

    @field_validator("max_message_size")
    @classmethod
    def _max_size(cls, v: Optional[str]) -> Optional[str]:
        return _check(_SIZE, v, "size")

    @field_validator("ttl")
    @classmethod
    def _ttl(cls, v: Optional[str]) -> Optional[str]:
        return _check(_DURATION, v, "duration")


class Namespace(Strict):
    retention: Optional[Retention] = None
    permissions: Permissions = Permissions()
    topics: dict[str, Topic] = {}
    native: dict[Protocol, dict[str, Any]] = {}


class Contacts(Strict):
    teams: str
    oncall: str


class TenantConfig(Strict):
    tenant: str
    owner: str
    contacts: Contacts
    protocol: Protocol
    stamps: list[Stamp] = Field(min_length=1)
    client_ids: dict[Stamp, dict[str, str]]
    namespaces: dict[str, Namespace] = {}
