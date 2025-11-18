"""Message encoder mapping semantics to DigiByte spend patterns."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Iterable, Tuple
from uuid import uuid4

from .dialect import DialectSymbol
from .encryption import encrypt_payload
from .model import (
    EncodingConfig,
    EnigmaticMessage,
    message_with_encrypted_payload,
)

logger = logging.getLogger(__name__)


@dataclass
class SpendInstruction:
    """Represents a single payment pattern element."""

    to_address: str | None
    amount: float
    is_anchor: bool
    is_micro: bool
    role: str
    op_return_data: bytes | None = None

    @property
    def is_op_return(self) -> bool:
        return self.op_return_data is not None


def aggregate_spend_instructions(
    instructions: Iterable["SpendInstruction"],
) -> Tuple[dict[str, float], list[bytes]]:
    """Group spend instructions by address and collect OP_RETURN payloads."""

    outputs: dict[str, float] = defaultdict(float)
    op_returns: list[bytes] = []
    for instruction in instructions:
        if instruction.op_return_data:
            op_returns.append(instruction.op_return_data)
            continue
        if not instruction.to_address:
            raise ValueError("Spend instruction is missing a destination address")
        outputs[instruction.to_address] += instruction.amount
    return dict(outputs), op_returns


class EnigmaticEncoder:
    """Translate :class:`EnigmaticMessage` objects into spend patterns."""

    def __init__(self, config: EncodingConfig, target_address: str) -> None:
        self.config = config
        self.target_address = target_address

    def encode_message(
        self,
        message: EnigmaticMessage,
        *,
        encrypt_with_passphrase: str | None = None,
    ) -> tuple[list[SpendInstruction], float]:
        """Convert a high-level message into spend instructions.

        The encoder does not interact with the blockchain. It simply derives
        a deterministic pattern which may later be realized by wallet code.
        This project exists for legitimate experimental signaling over DigiByte.
        When ``encrypt_with_passphrase`` is provided the semantic payload is
        encrypted using the optional helper layer before being stored with the
        message, but the numeric spend pattern remains unchanged.
        """

        payload_for_encoding = dict(message.payload)
        if encrypt_with_passphrase:
            encrypted_payload = encrypt_payload(
                payload_for_encoding,
                passphrase=encrypt_with_passphrase,
            )
            updated = message_with_encrypted_payload(message, encrypted_payload)
            message.payload = updated.payload
            message.encrypted = updated.encrypted

        anchors = self._anchors_for_intent(message.intent)
        micros = self._micros_for_payload(payload_for_encoding)

        instructions: list[SpendInstruction] = []
        for amount in anchors:
            instructions.append(
                SpendInstruction(
                    to_address=self.target_address,
                    amount=amount,
                    is_anchor=True,
                    is_micro=False,
                    role=message.intent,
                )
            )
        for idx, amount in enumerate(micros):
            instructions.append(
                SpendInstruction(
                    to_address=self.target_address,
                    amount=amount,
                    is_anchor=False,
                    is_micro=True,
                    role=f"payload_{idx}",
                )
            )

        op_return_hint = self._build_op_return_hint(message, payload_for_encoding)
        if op_return_hint:
            instructions.append(
                SpendInstruction(
                    to_address=None,
                    amount=0.0,
                    is_anchor=False,
                    is_micro=False,
                    role="op_return",
                    op_return_data=op_return_hint,
                )
            )

        logger.debug(
            "Encoded message %s into %d instructions", message.id or str(uuid4()), len(instructions)
        )
        return instructions, self.config.fee_punctuation

    def encode_symbol(
        self,
        symbol: DialectSymbol,
        channel: str,
        extra_payload: dict[str, Any] | None = None,
        encrypt_with_passphrase: str | None = None,
    ) -> tuple[EnigmaticMessage, list[SpendInstruction], float]:
        """Encode a :class:`DialectSymbol` into spend instructions.

        This helper lets trusted systems load dialect definitions from YAML and
        request Enigmatic patterns using symbolic names (e.g. ``INTEL_HELLO``).
        It keeps REAL/other integrations isolated from the blockchain concerns
        while ensuring the on-chain usage remains legitimate experimentation.
        Callers may optionally encrypt the semantic payload using the
        ``encrypt_with_passphrase`` parameter to protect contextual metadata.
        """

        payload: dict[str, Any] = {
            "symbol": symbol.name,
            "dialect": symbol.dialect_name or "unknown",
        }
        payload.update(symbol.metadata)
        if extra_payload:
            payload.update(extra_payload)

        payload_for_hint = dict(payload)

        message = EnigmaticMessage(
            id=str(uuid4()),
            timestamp=datetime.utcnow(),
            channel=channel,
            intent=symbol.intent or "symbol",
            payload=payload,
        )

        if encrypt_with_passphrase:
            encrypted_payload = encrypt_payload(
                payload,
                passphrase=encrypt_with_passphrase,
            )
            message = message_with_encrypted_payload(message, encrypted_payload)

        instructions: list[SpendInstruction] = []
        for amount in symbol.anchors:
            instructions.append(
                SpendInstruction(
                    to_address=self.target_address,
                    amount=amount,
                    is_anchor=True,
                    is_micro=False,
                    role=message.intent,
                )
            )
        for idx, amount in enumerate(symbol.micros):
            instructions.append(
                SpendInstruction(
                    to_address=self.target_address,
                    amount=amount,
                    is_anchor=False,
                    is_micro=True,
                    role=f"symbol_micro_{idx}",
                )
            )

        op_return_hint = self._build_op_return_hint(message, payload_for_hint)
        if op_return_hint:
            instructions.append(
                SpendInstruction(
                    to_address=None,
                    amount=0.0,
                    is_anchor=False,
                    is_micro=False,
                    role="op_return",
                    op_return_data=op_return_hint,
                )
            )
        logger.debug(
            "Encoded symbol %s (%s) into %d instructions",
            symbol.name,
            symbol.dialect_name,
            len(instructions),
        )
        return message, instructions, self.config.fee_punctuation

    def _anchors_for_intent(self, intent: str) -> list[float]:
        anchors = self.config.anchor_amounts
        if intent == "identity":
            return [anchors[0]]
        if intent == "sync":
            return anchors[1:3]
        if intent == "presence":
            return [anchors[3]]
        if intent == "high_presence":
            return [anchors[4]]
        return [anchors[0]]

    def _micros_for_payload(self, payload: dict) -> list[float]:
        micros: list[float] = []
        if not payload:
            return micros
        keys = sorted(payload.keys())
        micro_values = self.config.micro_amounts
        for idx, key in enumerate(keys):
            if idx >= len(micro_values):
                break
            value = payload[key]
            if isinstance(value, bool) and value:
                micros.append(micro_values[idx])
            elif isinstance(value, (int, float)):
                micros.append(micro_values[idx])
            elif value:
                micros.append(micro_values[idx])
        return micros

    def _build_op_return_hint(
        self, message: EnigmaticMessage, payload: dict[str, Any]
    ) -> bytes | None:
        """Serialize a compact hint for the optional OP_RETURN plane."""

        hint: dict[str, Any] = {
            "id": message.id,
            "intent": message.intent,
            "channel": message.channel,
        }
        if payload:
            try:
                serialized_payload = json.dumps(
                    payload, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            except (TypeError, ValueError):  # pragma: no cover - defensive
                serialized_payload = b""
            if serialized_payload:
                digest = hashlib.sha256(serialized_payload).hexdigest()[:16]
                hint["payload_hash"] = digest

        for keys_to_drop in (set(), {"channel"}, {"payload_hash"}, {"channel", "payload_hash"}):
            candidate = {k: v for k, v in hint.items() if k not in keys_to_drop}
            encoded = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
            if len(encoded) <= 80:
                return encoded
        return None
