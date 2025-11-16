"""Handshake utilities for establishing shared session keys.

This module layers a standard X25519 + HKDF key agreement workflow on top of
Enigmatic's messaging model.  It deliberately avoids custom cryptographic math
and instead focuses on building payloads that higher layers can transport using
the existing :class:`enigmatic_dgb.model.EnigmaticMessage` infrastructure.
"""

from __future__ import annotations

import base64
import binascii
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from .model import EnigmaticMessage

logger = logging.getLogger(__name__)


class HandshakeRole(Enum):
    """Enumeration describing whether we initiated or responded."""

    INITIATOR = auto()
    RESPONDER = auto()


class HandshakePhase(Enum):
    """Simple state machine for the handshake lifecycle."""

    INIT = auto()
    RESP = auto()
    COMPLETE = auto()
    FAILED = auto()


@dataclass
class HandshakeParameters:
    """Static parameters for a handshake exchange."""

    session_id: str
    channel: str
    dialect: str
    created_at: datetime


@dataclass
class HandshakeState:
    """Mutable state for an in-progress handshake."""

    role: HandshakeRole
    phase: HandshakePhase
    params: HandshakeParameters
    local_private_key: bytes
    local_public_key: bytes
    remote_public_key: Optional[bytes] = None
    shared_secret: Optional[bytes] = None
    session_key: Optional[bytes] = None


HANDSHAKE_PAYLOAD_VERSION = 1
HKDF_KEY_LEN = 32
HKDF_SALT_PREFIX = b"enigmatic-handshake"


def _generate_session_id() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_private_key(private_key: x25519.X25519PrivateKey) -> bytes:
    return private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())


def _serialize_public_key(public_key: x25519.X25519PublicKey) -> bytes:
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _load_private_key(data: bytes) -> x25519.X25519PrivateKey:
    return x25519.X25519PrivateKey.from_private_bytes(data)


def _load_public_key(data: bytes) -> x25519.X25519PublicKey:
    return x25519.X25519PublicKey.from_public_bytes(data)


def create_initiator_state(channel: str, dialect: str) -> HandshakeState:
    """Create a handshake state for the initiator."""

    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    params = HandshakeParameters(
        session_id=_generate_session_id(),
        channel=channel,
        dialect=dialect,
        created_at=_utcnow(),
    )
    logger.info("Creating initiator handshake state", extra={"channel": channel})
    return HandshakeState(
        role=HandshakeRole.INITIATOR,
        phase=HandshakePhase.INIT,
        params=params,
        local_private_key=_serialize_private_key(private_key),
        local_public_key=_serialize_public_key(public_key),
    )


def create_responder_state(params: HandshakeParameters) -> HandshakeState:
    """Create a handshake state for the responder."""

    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    logger.info(
        "Creating responder handshake state",
        extra={"channel": params.channel, "session_id": params.session_id},
    )
    return HandshakeState(
        role=HandshakeRole.RESPONDER,
        phase=HandshakePhase.RESP,
        params=params,
        local_private_key=_serialize_private_key(private_key),
        local_public_key=_serialize_public_key(public_key),
    )


def derive_session_key(shared_secret: bytes, params: HandshakeParameters) -> bytes:
    """Derive a session key from a raw shared secret using HKDF-SHA256."""

    salt = HKDF_SALT_PREFIX + params.session_id.encode("utf-8")
    info = f"enigmatic|{params.channel}|{params.dialect}".encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=HKDF_KEY_LEN,
        salt=salt,
        info=info,
    )
    return hkdf.derive(shared_secret)


def build_handshake_payload(state: HandshakeState, include_mac: bool = False) -> Dict[str, Any]:
    """Build a serializable payload describing the handshake state."""

    payload: Dict[str, Any] = {
        "type": "handshake",
        "version": HANDSHAKE_PAYLOAD_VERSION,
        "session_id": state.params.session_id,
        "phase": state.phase.name,
        "role_hint": state.role.name.lower(),
        "dialect": state.params.dialect,
        "channel": state.params.channel,
        "created_at": state.params.created_at.isoformat(),
        "public_key": base64.b64encode(state.local_public_key).decode("ascii"),
    }
    if include_mac and state.session_key is not None:
        payload["mac"] = base64.b64encode(state.session_key).decode("ascii")
    return payload


def parse_handshake_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a handshake payload dictionary."""

    required_fields = {"type", "version", "session_id", "phase", "dialect", "channel", "public_key"}
    missing = required_fields - payload.keys()
    if missing:
        raise ValueError(f"Handshake payload missing fields: {sorted(missing)}")

    if payload["type"] != "handshake":
        raise ValueError("Unsupported handshake payload type")

    version = payload["version"]
    if version != HANDSHAKE_PAYLOAD_VERSION:
        raise ValueError(f"Unsupported handshake payload version: {version}")

    phase_name = payload["phase"]
    try:
        phase = HandshakePhase[phase_name]
    except KeyError as exc:
        raise ValueError(f"Unknown handshake phase: {phase_name}") from exc

    try:
        public_key = base64.b64decode(payload["public_key"], validate=True)
    except binascii.Error as exc:
        raise ValueError("Invalid base64 encoding for public_key") from exc

    mac: Optional[bytes] = None
    if "mac" in payload and payload["mac"] is not None:
        try:
            mac = base64.b64decode(payload["mac"], validate=True)
        except binascii.Error as exc:  # pragma: no cover - defensive
            raise ValueError("Invalid base64 encoding for mac") from exc

    normalized = {
        "session_id": str(payload["session_id"]),
        "phase": phase,
        "dialect": str(payload["dialect"]),
        "channel": str(payload["channel"]),
        "public_key": public_key,
    }
    if mac is not None:
        normalized["mac"] = mac
    return normalized


def _compute_shared_secret(state: HandshakeState, remote_public_key: bytes) -> bytes:
    private_key = _load_private_key(state.local_private_key)
    public_key = _load_public_key(remote_public_key)
    return private_key.exchange(public_key)


def initiator_build_init_message(state: HandshakeState) -> Dict[str, Any]:
    """Build the INIT payload for the initiator."""

    if state.role is not HandshakeRole.INITIATOR:
        raise ValueError("State is not configured as initiator")
    state.phase = HandshakePhase.INIT
    return build_handshake_payload(state)


def responder_process_init_and_build_resp(
    responder_state: HandshakeState,
    init_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Process the INIT payload and return the RESP payload."""

    if responder_state.role is not HandshakeRole.RESPONDER:
        raise ValueError("State is not configured as responder")

    parsed = parse_handshake_payload(init_payload)
    if parsed["session_id"] != responder_state.params.session_id:
        raise ValueError("Session mismatch between init payload and responder state")
    if parsed["channel"] != responder_state.params.channel or parsed["dialect"] != responder_state.params.dialect:
        raise ValueError("Channel or dialect mismatch in init payload")

    responder_state.remote_public_key = parsed["public_key"]
    shared_secret = _compute_shared_secret(responder_state, parsed["public_key"])
    responder_state.shared_secret = shared_secret
    responder_state.session_key = derive_session_key(shared_secret, responder_state.params)
    responder_state.phase = HandshakePhase.COMPLETE
    logger.info(
        "Responder completed handshake",
        extra={"channel": responder_state.params.channel, "session_id": responder_state.params.session_id},
    )
    return build_handshake_payload(responder_state)


def initiator_process_resp(initiator_state: HandshakeState, resp_payload: Dict[str, Any]) -> None:
    """Process the RESP payload and finalize the initiator state."""

    if initiator_state.role is not HandshakeRole.INITIATOR:
        raise ValueError("State is not configured as initiator")

    parsed = parse_handshake_payload(resp_payload)
    if parsed["session_id"] != initiator_state.params.session_id:
        raise ValueError("Session mismatch between resp payload and initiator state")
    if parsed["channel"] != initiator_state.params.channel or parsed["dialect"] != initiator_state.params.dialect:
        raise ValueError("Channel or dialect mismatch in resp payload")

    initiator_state.remote_public_key = parsed["public_key"]
    shared_secret = _compute_shared_secret(initiator_state, parsed["public_key"])
    initiator_state.shared_secret = shared_secret
    initiator_state.session_key = derive_session_key(shared_secret, initiator_state.params)
    initiator_state.phase = HandshakePhase.COMPLETE
    logger.info(
        "Initiator completed handshake",
        extra={"channel": initiator_state.params.channel, "session_id": initiator_state.params.session_id},
    )


def create_handshake_init_message(state: HandshakeState) -> EnigmaticMessage:
    """Wrap the initiator payload in an EnigmaticMessage container."""

    payload = initiator_build_init_message(state)
    return EnigmaticMessage(
        id=f"{state.params.session_id}:INIT",
        timestamp=_utcnow(),
        channel=state.params.channel,
        intent="handshake",
        payload=payload,
    )


def create_handshake_resp_message(state: HandshakeState, resp_payload: Dict[str, Any]) -> EnigmaticMessage:
    """Wrap a responder payload in an EnigmaticMessage container."""

    return EnigmaticMessage(
        id=f"{state.params.session_id}:RESP",
        timestamp=_utcnow(),
        channel=state.params.channel,
        intent="handshake",
        payload=resp_payload,
    )

