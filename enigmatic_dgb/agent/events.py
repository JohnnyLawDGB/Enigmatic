"""Event schema for hybrid agent processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable
from uuid import uuid4


class EventSeverity(Enum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AgentEvent:
    event_id: str
    event_type: str
    source: str
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    severity: EventSeverity = EventSeverity.INFO
    tags: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        event_type: str,
        source: str,
        *,
        payload: dict[str, Any] | None = None,
        severity: EventSeverity = EventSeverity.INFO,
        tags: Iterable[str] | None = None,
        occurred_at: datetime | None = None,
        event_id: str | None = None,
    ) -> "AgentEvent":
        return cls(
            event_id=event_id or uuid4().hex,
            event_type=event_type,
            source=source,
            occurred_at=occurred_at or utc_now(),
            payload=payload or {},
            severity=severity,
            tags=tuple(tags or ()),
        )


def event_to_dict(event: AgentEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "source": event.source,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": event.payload,
        "severity": event.severity.value,
        "tags": list(event.tags),
    }


def _normalize_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def event_from_dict(data: dict[str, Any]) -> AgentEvent:
    return AgentEvent(
        event_id=str(data["event_id"]),
        event_type=str(data["event_type"]),
        source=str(data["source"]),
        occurred_at=_normalize_timestamp(str(data["occurred_at"])),
        payload=dict(data.get("payload") or {}),
        severity=EventSeverity(str(data.get("severity", EventSeverity.INFO.value))),
        tags=tuple(data.get("tags") or ()),
    )
