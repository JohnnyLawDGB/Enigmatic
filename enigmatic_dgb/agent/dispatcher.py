"""Action dispatching utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict

from .actions import ActionRequest, ActionResult, ActionStatus

ActionHandler = Callable[[ActionRequest], ActionResult]


@dataclass
class ActionDispatcher:
    handlers: Dict[str, ActionHandler]

    def dispatch(self, action: ActionRequest) -> ActionResult:
        handler = self.handlers.get(action.action_type)
        if not handler:
            return ActionResult(
                action_id=action.action_id,
                action_type=action.action_type,
                completed_at=datetime.now(timezone.utc),
                status=ActionStatus.FAILED,
                error=f"No handler registered for action '{action.action_type}'.",
            )
        try:
            return handler(action)
        except Exception as exc:  # pragma: no cover - defensive logging
            return ActionResult(
                action_id=action.action_id,
                action_type=action.action_type,
                completed_at=datetime.now(timezone.utc),
                status=ActionStatus.FAILED,
                error=str(exc),
            )


def build_notify_handler(
    notifier: Callable[[str, dict], None]
) -> Callable[[ActionRequest], ActionResult]:
    def _handler(action: ActionRequest) -> ActionResult:
        payload = dict(action.payload)
        message = str(payload.get("message") or "Notification")
        notifier(message, payload)
        return ActionResult(
            action_id=action.action_id,
            action_type=action.action_type,
            completed_at=datetime.now(timezone.utc),
            status=ActionStatus.SUCCEEDED,
            details={"notified": True},
        )

    return _handler
