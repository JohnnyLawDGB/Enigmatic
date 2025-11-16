"""Domain models for the Enigmatic DigiByte protocol."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List

from .encryption import EncryptedPayload, decrypt_payload


@dataclass
class EnigmaticMessage:
    """High-level semantic message passed between Enigmatic peers."""

    id: str
    timestamp: datetime
    channel: str
    intent: str
    payload: Dict[str, Any] = field(default_factory=dict)
    encrypted: bool = False


def message_with_encrypted_payload(
    base_message: EnigmaticMessage, encrypted_payload: EncryptedPayload
) -> EnigmaticMessage:
    """Return a copy of *base_message* containing only the encrypted payload."""

    payload_wrapper = {"encrypted": asdict(encrypted_payload)}
    return replace(base_message, payload=payload_wrapper, encrypted=True)


def message_decrypt_payload(message: EnigmaticMessage, passphrase: str) -> Dict[str, Any]:
    """Return the plaintext payload for *message* using *passphrase* when needed."""

    if not message.encrypted:
        return message.payload
    encrypted_data = message.payload.get("encrypted")
    if not isinstance(encrypted_data, dict):  # pragma: no cover - defensive
        raise ValueError("Encrypted message payload is malformed")
    encrypted_payload = EncryptedPayload(**encrypted_data)
    return decrypt_payload(encrypted_payload, passphrase)


@dataclass
class AnchorPattern:
    amount: float
    label: str


@dataclass
class MicroPattern:
    amount: float
    label: str


@dataclass
class EncodingConfig:
    """Configuration describing anchors, micros, and timing for encoding."""

    anchor_amounts: List[float]
    micro_amounts: List[float]
    fee_punctuation: float
    packet_max_interval_seconds: int

    @classmethod
    def enigmatic_default(cls) -> "EncodingConfig":
        """Return the reference configuration used in documentation examples."""

        anchors = [217, 234, 265, 352, 866]
        micros = [0.076, 0.152, 0.303, 0.331, 0.5178, 0.771, 0.889, 1.0]
        return cls(
            anchor_amounts=anchors,
            micro_amounts=micros,
            fee_punctuation=0.21,
            packet_max_interval_seconds=120,
        )
