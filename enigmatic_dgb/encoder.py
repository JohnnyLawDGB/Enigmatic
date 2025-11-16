"""Message encoder mapping semantics to DigiByte spend patterns."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Tuple
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

    to_address: str
    amount: float
    is_anchor: bool
    is_micro: bool
    role: str


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
    ) -> Tuple[List[SpendInstruction], float]:
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

        instructions: List[SpendInstruction] = []
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
    ) -> tuple[EnigmaticMessage, List[SpendInstruction], float]:
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

        instructions: List[SpendInstruction] = []
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
        logger.debug(
            "Encoded symbol %s (%s) into %d instructions",
            symbol.name,
            symbol.dialect_name,
            len(instructions),
        )
        return message, instructions, self.config.fee_punctuation

    def _anchors_for_intent(self, intent: str) -> List[float]:
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

    def _micros_for_payload(self, payload: dict) -> List[float]:
        micros: List[float] = []
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
