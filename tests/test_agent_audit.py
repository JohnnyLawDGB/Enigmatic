from pathlib import Path

import pytest

from enigmatic_dgb.agent.audit import AuditLogger
from enigmatic_dgb.agent.events import AgentEvent


def test_audit_logger_handles_unwritable_path(tmp_path) -> None:
    log_dir = tmp_path / "audit"
    log_dir.mkdir()
    logger = AuditLogger(log_dir)
    logger.log_event(AgentEvent.create(event_type="transaction", source="demo"))

    strict_logger = AuditLogger(log_dir, strict=True)
    with pytest.raises(OSError):
        strict_logger.log_event(AgentEvent.create(event_type="transaction", source="demo"))


def test_audit_logger_rotates(tmp_path) -> None:
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path, max_bytes=200, rotate_keep=2)
    for _ in range(10):
        logger.log_event(AgentEvent.create(event_type="transaction", source="demo"))

    rotated = Path(f"{log_path}.1")
    assert rotated.exists()
