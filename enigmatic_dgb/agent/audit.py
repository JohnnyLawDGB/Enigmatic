"""Audit logging utilities for hybrid agent activity."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .actions import ActionRequest, ActionResult, action_request_to_dict, action_result_to_dict
from .events import AgentEvent, event_to_dict


logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(
        self,
        path: Path,
        *,
        strict: bool = False,
        max_bytes: int | None = None,
        rotate_keep: int = 3,
    ) -> None:
        self.path = path
        self.strict = strict
        self.max_bytes = max_bytes
        self.rotate_keep = max(0, rotate_keep)

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
        serialized = json.dumps(
            record, sort_keys=True, ensure_ascii=True, default=str
        )
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_if_needed(len(serialized) + 1)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.write("\n")
        except OSError as exc:
            logger.warning("Audit log write failed: %s", exc)
            if self.strict:
                raise

    def _rotate_if_needed(self, incoming_size: int) -> None:
        if not self.max_bytes:
            return
        try:
            current_size = self.path.stat().st_size
        except FileNotFoundError:
            current_size = 0
        if current_size + incoming_size <= self.max_bytes:
            return
        self._rotate_files()

    def _rotate_files(self) -> None:
        if self.rotate_keep <= 0:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Failed to truncate audit log.")
            return
        for idx in range(self.rotate_keep - 1, 0, -1):
            src = self.path.with_name(f"{self.path.name}.{idx}")
            dst = self.path.with_name(f"{self.path.name}.{idx + 1}")
            if src.exists():
                try:
                    src.replace(dst)
                except OSError:
                    logger.debug("Failed to rotate audit log %s", src.as_posix())
        if self.path.exists():
            rotated = self.path.with_name(f"{self.path.name}.1")
            try:
                self.path.replace(rotated)
            except OSError:
                logger.debug("Failed to rotate audit log %s", self.path.as_posix())


def serialize_for_audit(data: Any) -> dict[str, Any]:
    if hasattr(data, "__dataclass_fields__"):
        return asdict(data)
    if isinstance(data, dict):
        return dict(data)
    return {"value": data}
