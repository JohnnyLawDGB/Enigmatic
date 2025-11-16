"""Session context helpers for optional secure flows.

These helpers wrap the negotiated state derived from X25519 + HKDF handshakes
so that downstream components can reason about active sessions without dealing
with raw secrets.  They are intentionally simple, reflecting that Enigmatic's
numeric transport is *not* a replacement for standard cryptography.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SessionContext:
    """Representation of an active session binding a dialect/channel pair."""

    session_id: str
    channel: str
    dialect: str
    created_at: datetime
    session_key: bytes
    expires_at: Optional[datetime] = None


def session_key_to_passphrase(session_key: bytes) -> str:
    """Convert raw session key bytes into a stable textual passphrase."""

    return base64.urlsafe_b64encode(session_key).decode("ascii")
