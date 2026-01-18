"""Action schema for hybrid agent execution and approvals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class ActionStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ActionRequest:
    action_id: str
    action_type: str
    created_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    status: ActionStatus = ActionStatus.PENDING

    @classmethod
    def create(
        cls,
        action_type: str,
        *,
        payload: dict[str, Any] | None = None,
        requires_confirmation: bool = False,
        created_at: datetime | None = None,
        action_id: str | None = None,
    ) -> "ActionRequest":
        return cls(
            action_id=action_id or uuid4().hex,
            action_type=action_type,
            created_at=created_at or utc_now(),
            payload=payload or {},
            requires_confirmation=requires_confirmation,
            status=ActionStatus.PENDING,
        )


@dataclass(frozen=True)
class ActionResult:
    action_id: str
    action_type: str
    completed_at: datetime
    status: ActionStatus
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def action_request_to_dict(action: ActionRequest) -> dict[str, Any]:
    return {
        "action_id": action.action_id,
        "action_type": action.action_type,
        "created_at": action.created_at.isoformat(),
        "payload": action.payload,
        "requires_confirmation": action.requires_confirmation,
        "status": action.status.value,
    }


def action_request_from_dict(data: dict[str, Any]) -> ActionRequest:
    created_at = datetime.fromisoformat(str(data["created_at"]))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    status = ActionStatus(str(data.get("status", ActionStatus.PENDING.value)))
    return ActionRequest(
        action_id=str(data["action_id"]),
        action_type=str(data["action_type"]),
        created_at=created_at,
        payload=dict(data.get("payload") or {}),
        requires_confirmation=bool(data.get("requires_confirmation", False)),
        status=status,
    )


def action_result_to_dict(result: ActionResult) -> dict[str, Any]:
    return {
        "action_id": result.action_id,
        "action_type": result.action_type,
        "completed_at": result.completed_at.isoformat(),
        "status": result.status.value,
        "details": result.details,
        "error": result.error,
    }


def action_result_from_dict(data: dict[str, Any]) -> ActionResult:
    completed_at = datetime.fromisoformat(str(data["completed_at"]))
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    status = ActionStatus(str(data.get("status", ActionStatus.SUCCEEDED.value)))
    return ActionResult(
        action_id=str(data["action_id"]),
        action_type=str(data["action_type"]),
        completed_at=completed_at,
        status=status,
        details=dict(data.get("details") or {}),
        error=data.get("error"),
    )
