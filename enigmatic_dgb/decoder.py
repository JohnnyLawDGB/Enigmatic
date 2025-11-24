"""Decoder mapping observed DigiByte traffic back to Enigmatic messages."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, List

from .model import EncodingConfig, EnigmaticMessage
from .script_plane import ScriptPlane

logger = logging.getLogger(__name__)


@dataclass
class ObservedTx:
    txid: str
    timestamp: datetime
    amount: float
    fee: float | None = None
    op_return_data: bytes | None = None
    script_plane: ScriptPlane | None = None
    block_height: int | None = None


def group_into_packets(txs: List[ObservedTx], config: EncodingConfig) -> List[List[ObservedTx]]:
    """Group sorted transactions into packets based on time gaps."""

    if not txs:
        return []
    txs_sorted = sorted(txs, key=lambda tx: tx.timestamp)
    packets: List[List[ObservedTx]] = []
    current: List[ObservedTx] = [txs_sorted[0]]
    max_gap = timedelta(seconds=config.packet_max_interval_seconds)
    last = txs_sorted[0]

    for tx in txs_sorted[1:]:
        if tx.timestamp - last.timestamp >= max_gap:
            packets.append(current)
            current = [tx]
        else:
            current.append(tx)
        last = tx
    packets.append(current)
    return packets


class EnigmaticDecoder:
    """Translate packets of payments back into Enigmatic messages."""

    def __init__(self, config: EncodingConfig) -> None:
        self.config = config

    def decode_packet(self, packet: List[ObservedTx], channel: str) -> EnigmaticMessage:
        if not packet:
            raise ValueError("Packet must contain at least one transaction")

        anchors = [tx for tx in packet if self._matches_anchor(tx.amount)]
        micros = [tx for tx in packet if self._matches_micro(tx.amount)]
        fee_punct = any(
            tx.fee is not None and abs(tx.fee - self.config.fee_punctuation) < 1e-8
            for tx in packet
        )

        intent = self._intent_from_anchors(anchors)
        payload = self._payload_from_micros(micros)
        if fee_punct:
            payload["punctuation"] = True
        script_planes = [tx.script_plane.to_dict() for tx in packet if tx.script_plane]
        if script_planes:
            payload["script_plane"] = script_planes[0] if len(script_planes) == 1 else script_planes

        op_return_hints = self._op_return_metadata(packet)
        if op_return_hints:
            payload["op_return"] = op_return_hints[0] if len(op_return_hints) == 1 else op_return_hints

        message = EnigmaticMessage(
            id=str(uuid.uuid4()),
            timestamp=min(tx.timestamp for tx in packet),
            channel=channel,
            intent=intent,
            payload=payload,
        )
        logger.debug("Decoded packet of %d txs into %s", len(packet), message.intent)
        return message

    def _intent_from_anchors(self, anchors: List[ObservedTx]) -> str:
        amounts = {round(tx.amount, 8) for tx in anchors}
        config_anchors = self.config.anchor_amounts
        if config_anchors[0] in amounts:
            if len(amounts) > 1:
                return "channel"
            return "identity"
        if config_anchors[1] in amounts and config_anchors[0] in amounts:
            return "sync"
        if config_anchors[3] in amounts:
            return "presence"
        if config_anchors[4] in amounts:
            return "high_presence"
        return "content"

    def _payload_from_micros(self, micros: List[ObservedTx]) -> dict:
        payload: dict = {}
        micro_values = self.config.micro_amounts
        for idx, tx in enumerate(micros):
            if idx >= len(micro_values):
                break
            if abs(tx.amount - micro_values[idx]) < 1e-8:
                payload[f"flag_{idx}"] = True
            else:
                payload[f"micro_{idx}"] = tx.amount
        return payload

    def _matches_anchor(self, amount: float) -> bool:
        return any(abs(amount - anchor) < 1e-8 for anchor in self.config.anchor_amounts)

    def _matches_micro(self, amount: float) -> bool:
        return any(abs(amount - micro) < 1e-8 for micro in self.config.micro_amounts)

    def _op_return_metadata(self, packet: List[ObservedTx]) -> list[dict[str, Any]]:
        hints: list[dict[str, Any]] = []
        for tx in packet:
            if not tx.op_return_data:
                continue
            try:
                text = tx.op_return_data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                hints.append(decoded)
        return hints
