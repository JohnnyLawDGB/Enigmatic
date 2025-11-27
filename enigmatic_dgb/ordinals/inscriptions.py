"""Decoding helpers for ordinal-style inscriptions.

This module focuses on retrieving inscription payloads and translating them into
structured metadata. It does not implement a canonical ordinal numbering scheme;
all behavior is experimental and subject to iteration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from enigmatic_dgb.ordinals.indexer import OrdinalLocation


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
        return self._extract_candidate_payloads_from_tx(tx)

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

    def _extract_candidate_payloads_from_tx(self, tx: Dict[str, Any]) -> List[InscriptionPayload]:
        """Placeholder for inscription payload extraction.

        TODO: Parse OP_RETURN outputs, inspect Taproot-like witness data, and
        construct :class:`InscriptionPayload` entries. For now, this returns an
        empty list to keep the plumbing lightweight.
        """

        return []
