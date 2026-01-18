"""Audit logging utilities for hybrid agent activity."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .actions import ActionRequest, ActionResult, action_request_to_dict, action_result_to_dict
from .events import AgentEvent, event_to_dict


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def log_event(self, event: AgentEvent) -> None:
        self._append_entry("event", event_to_dict(event))

    def log_action_request(self, action: ActionRequest) -> None:
        self._append_entry("action_request", action_request_to_dict(action))

    def log_action_result(self, result: ActionResult) -> None:
        self._append_entry("action_result", action_result_to_dict(result))

    def _append_entry(self, entry_type: str, payload: dict[str, Any]) -> None:
        record = {
            "entry_id": uuid4().hex,
            "entry_type": entry_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True))
            handle.write("\n")


def serialize_for_audit(data: Any) -> dict[str, Any]:
    if hasattr(data, "__dataclass_fields__"):
        return asdict(data)
    if isinstance(data, dict):
        return dict(data)
    return {"value": data}
