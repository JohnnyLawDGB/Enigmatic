"""Message encoder mapping semantics to DigiByte spend patterns."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple
from uuid import uuid4

from .model import EncodingConfig, EnigmaticMessage

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

    def encode_message(self, message: EnigmaticMessage) -> Tuple[List[SpendInstruction], float]:
        """Convert a high-level message into spend instructions.

        The encoder does not interact with the blockchain. It simply derives
        a deterministic pattern which may later be realized by wallet code.
        This project exists for legitimate experimental signaling over DigiByte.
        """

        anchors = self._anchors_for_intent(message.intent)
        micros = self._micros_for_payload(message.payload)

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
