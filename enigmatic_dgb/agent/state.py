"""State management for hybrid agent workflows."""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List

from .actions import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    action_request_from_dict,
    action_request_to_dict,
    action_result_from_dict,
    action_result_to_dict,
)
from .audit import AuditLogger
from .events import AgentEvent, event_from_dict, event_to_dict


class AgentStateStore:
    def __init__(
        self,
        *,
        max_events: int = 1000,
        max_action_history: int = 1000,
        persist_path: Path | None = None,
        auto_persist: bool = False,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._events: Deque[AgentEvent] = deque(maxlen=max_events)
        self._processed_event_ids: set[str] = set()
        self._pending_actions: Dict[str, ActionRequest] = {}
        self._action_history: Deque[ActionResult] = deque(maxlen=max_action_history)
        self._preferences: Dict[str, Any] = {}
        self._persist_path = persist_path
        self._auto_persist = auto_persist
        self._audit_logger = audit_logger

        if self._persist_path and self._persist_path.exists():
            self.load()

    def record_event(self, event: AgentEvent) -> None:
        self._events.append(event)
        if self._audit_logger:
            self._audit_logger.log_event(event)
        self._persist_if_enabled()

    def get_recent_events(self, limit: int = 20) -> List[AgentEvent]:
        if limit <= 0:
            return []
        return list(self._events)[-limit:]

    def mark_event_processed(self, event_id: str) -> None:
        self._processed_event_ids.add(event_id)
        self._persist_if_enabled()

    def is_event_processed(self, event_id: str) -> bool:
        return event_id in self._processed_event_ids

    def add_pending_action(self, action: ActionRequest) -> None:
        self._pending_actions[action.action_id] = action
        if self._audit_logger:
            self._audit_logger.log_action_request(action)
        self._persist_if_enabled()

    def update_pending_action_status(
        self, action_id: str, status: ActionStatus
    ) -> ActionRequest:
        action = self._pending_actions.get(action_id)
        if action is None:
            raise KeyError(f"Unknown action id: {action_id}")
        action.status = status
        if self._audit_logger:
            self._audit_logger.log_action_request(action)
        self._persist_if_enabled()
        return action

    def list_pending_actions(self) -> List[ActionRequest]:
        return list(self._pending_actions.values())

    def resolve_action(
        self,
        action_id: str,
        status: ActionStatus,
        *,
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ActionResult:
        action = self._pending_actions.get(action_id)
        if action is None:
            raise KeyError(f"Unknown action id: {action_id}")
        action.status = status
        result = ActionResult(
            action_id=action.action_id,
            action_type=action.action_type,
            completed_at=datetime.now(timezone.utc),
            status=status,
            details=details or {},
            error=error,
        )
        self._action_history.append(result)
        if status in {
            ActionStatus.SUCCEEDED,
            ActionStatus.FAILED,
            ActionStatus.REJECTED,
            ActionStatus.CANCELLED,
        }:
            self._pending_actions.pop(action_id, None)
        if self._audit_logger:
            self._audit_logger.log_action_result(result)
        self._persist_if_enabled()
        return result

    def get_action_history(self, limit: int = 20) -> List[ActionResult]:
        if limit <= 0:
            return []
        return list(self._action_history)[-limit:]

    def set_preference(self, key: str, value: Any) -> None:
        self._preferences[key] = value
        self._persist_if_enabled()

    def get_preferences(self) -> Dict[str, Any]:
        return dict(self._preferences)

    def save(self) -> None:
        if not self._persist_path:
            return
        snapshot = {
            "events": [event_to_dict(event) for event in self._events],
            "processed_event_ids": sorted(self._processed_event_ids),
            "pending_actions": [
                action_request_to_dict(action)
                for action in self._pending_actions.values()
            ],
            "action_history": [
                action_result_to_dict(result) for result in self._action_history
            ],
            "preferences": self._preferences,
        }
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._persist_path.with_suffix(
            self._persist_path.suffix + ".tmp"
        )
        temp_path.write_text(
            json.dumps(snapshot, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )
        temp_path.replace(self._persist_path)

    def load(self) -> None:
        if not self._persist_path:
            return
        raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
        self._events.clear()
        for event_data in raw.get("events", []):
            self._events.append(event_from_dict(event_data))
        self._processed_event_ids = set(raw.get("processed_event_ids", []))
        self._pending_actions.clear()
        for action_data in raw.get("pending_actions", []):
            action = action_request_from_dict(action_data)
            self._pending_actions[action.action_id] = action
        self._action_history.clear()
        for result_data in raw.get("action_history", []):
            self._action_history.append(action_result_from_dict(result_data))
        self._preferences = dict(raw.get("preferences", {}))

    def _persist_if_enabled(self) -> None:
        if self._persist_path and self._auto_persist:
            self.save()

    def to_debug_dict(self) -> Dict[str, Any]:
        return {
            "events": [event_to_dict(event) for event in self._events],
            "processed_event_ids": sorted(self._processed_event_ids),
            "pending_actions": [
                action_request_to_dict(action)
                for action in self._pending_actions.values()
            ],
            "action_history": [
                action_result_to_dict(result) for result in self._action_history
            ],
            "preferences": self._preferences,
        }
