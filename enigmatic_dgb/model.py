"""Domain models for the Enigmatic DigiByte protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class EnigmaticMessage:
    """High-level semantic message passed between Enigmatic peers."""

    id: str
    timestamp: datetime
    channel: str
    intent: str
    payload: Dict[str, Any] = field(default_factory=dict)


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
