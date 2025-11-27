"""Decoding helpers for ordinal-style inscriptions.

This module focuses on retrieving inscription payloads and translating them into
structured metadata. It does not implement a canonical ordinal numbering scheme;
all behavior is experimental and subject to iteration.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from enigmatic_dgb.ordinals.indexer import OrdinalIndexer, OrdinalLocation


@dataclass
class InscriptionMetadata:
    """Describes the decoded metadata for an inscription payload."""

    location: OrdinalLocation
    protocol: str
    content_type: Optional[str]
    length: Optional[int]
    codec: Optional[str]
    notes: Optional[str]


@dataclass
class InscriptionPayload:
    """Container for inscription metadata and raw/decoded content."""

    metadata: InscriptionMetadata
    raw_payload: bytes
    decoded_text: Optional[str]
    decoded_json: Optional[Dict[str, Any]]


class OrdinalInscriptionDecoder:
    """Decode ordinal-style inscriptions from DigiByte transactions.

    This decoder is intentionally lightweight; it wires RPC retrieval into
    placeholder payload extraction routines. Future implementations can layer in
    stricter protocol detection and content decoding.
    """

    def __init__(self, rpc_client) -> None:
        self.rpc_client = rpc_client

    def decode_from_tx(self, txid: str) -> List[InscriptionPayload]:
        """Decode inscription-style data from a transaction.

        The current implementation fetches the transaction and delegates to a
        helper for candidate payload extraction. No decoding heuristics are
        applied yet.
        """

        tx = self.rpc_client.get_raw_transaction(txid, verbose=True)
        indexer = OrdinalIndexer(self.rpc_client)
        locations = indexer.scan_tx(txid)
        return _extract_candidate_payloads_from_tx(tx, locations)

    def decode_from_location(self, location: OrdinalLocation) -> Optional[InscriptionPayload]:
        """Decode a specific output location for inscription-style data.

        The default behavior fetches the transaction and scans it for candidate
        payloads. Future revisions may short-circuit when the location is
        already known to contain data.
        """

        payloads = self.decode_from_tx(location.txid)
        for payload in payloads:
            if payload.metadata.location.vout == location.vout:
                return payload
        return None


def _extract_candidate_payloads_from_tx(tx_json: Dict[str, Any], locations: List[OrdinalLocation]) -> List[InscriptionPayload]:
    """Extract candidate inscription payloads from a transaction.

    This helper performs lightweight decoding for OP_RETURN-based inscriptions
    and captures raw witness data for taproot-like locations. It is intentionally
    forgiving and will return as many payloads as it can recover without raising
    exceptions.
    """

    logger = logging.getLogger(__name__)
    payloads: List[InscriptionPayload] = []

    vout_by_index = {vout.get("n", 0): vout for vout in tx_json.get("vout", [])}
    witness_fields: List[str] = []
    for vin in tx_json.get("vin", []):
        witness_fields.extend(vin.get("txinwitness") or [])

    for location in locations:
        vout = vout_by_index.get(location.vout)
        if not vout:
            logger.debug("No matching vout %s for location %s", location.vout, location)
            continue

        script_pub_key = vout.get("scriptPubKey", {})

        if location.ordinal_hint == "op_return":
            data_hex = _extract_op_return_hex(script_pub_key)
            if data_hex is None:
                logger.debug("Failed to extract OP_RETURN hex for %s", location)
                continue

            try:
                raw_bytes = bytes.fromhex(data_hex)
            except ValueError:
                logger.debug("Non-hex data in OP_RETURN payload for %s", location)
                continue

            decoded_text = raw_bytes.decode("utf-8", errors="replace") if raw_bytes else ""
            decoded_json: Optional[Dict[str, Any]] = None
            if decoded_text:
                try:
                    decoded_json = json.loads(decoded_text)
                except (json.JSONDecodeError, TypeError):
                    decoded_json = None

            metadata = InscriptionMetadata(
                location=location,
                protocol="enigmatic/experimental",
                content_type=None,
                length=len(raw_bytes),
                codec="raw-hex",
                notes="OP_RETURN inscription candidate",
            )

            payloads.append(
                InscriptionPayload(
                    metadata=metadata,
                    raw_payload=raw_bytes,
                    decoded_text=decoded_text,
                    decoded_json=decoded_json,
                )
            )

        elif location.ordinal_hint == "taproot_like":
            witness_bytes = b"".join(_hex_to_bytes_safe(w) for w in witness_fields)

            metadata = InscriptionMetadata(
                location=location,
                protocol="enigmatic/experimental",
                content_type=None,
                length=len(witness_bytes),
                codec="raw-witness",
                notes="Taproot-like placeholder; TODO: BIP341-style parsing",
            )

            payloads.append(
                InscriptionPayload(
                    metadata=metadata,
                    raw_payload=witness_bytes,
                    decoded_text=witness_bytes.decode("utf-8", errors="replace") if witness_bytes else "",
                    decoded_json=None,
                )
            )

    return payloads


def _extract_op_return_hex(script_pub_key: Dict[str, Any]) -> Optional[str]:
    """Attempt to extract the data hex component from an OP_RETURN script."""

    asm = script_pub_key.get("asm") or ""
    asm_parts = [part for part in asm.split(" ") if part]
    # Prefer the last hex-looking token in the asm representation.
    for part in reversed(asm_parts):
        if _is_hex(part):
            return part

    hex_field = script_pub_key.get("hex")
    if isinstance(hex_field, str) and _is_hex(hex_field):
        # Strip the OP_RETURN opcode (0x6a) when present; keep remaining payload.
        if hex_field.lower().startswith("6a"):
            return hex_field[2:]
        return hex_field

    return None


def _is_hex(value: str) -> bool:
    """Return True if the string looks like hex data."""

    try:
        bytes.fromhex(value)
        return True
    except (TypeError, ValueError):
        return False


def _hex_to_bytes_safe(value: Any) -> bytes:
    """Safely convert a hex-like string to bytes, ignoring failures."""

    if not isinstance(value, str):
        return b""
    try:
        return bytes.fromhex(value)
    except ValueError:
        return b""
