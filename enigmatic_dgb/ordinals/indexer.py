"""Ordinal-style index scaffolding for DigiByte.

This module defines foundational types and scanning stubs for locating
ordinal-style inscriptions on the DigiByte blockchain. The logic here is
non-consensus, experimental, and focused on discoverability rather than
formal ordinal numbering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set

from enigmatic_dgb.rpc_client import DigiByteRPCClient


@dataclass
class OrdinalLocation:
    """Represents a candidate inscription location within a transaction output."""

    txid: str
    vout: int
    height: Optional[int]
    ordinal_hint: Optional[str]
    tags: Set[str] = field(default_factory=set)


@dataclass
class OrdinalScanConfig:
    """Configuration for scanning a range of blocks for ordinal-style data."""

    start_height: Optional[int]
    end_height: Optional[int]
    limit: Optional[int]
    include_op_return: bool = True
    include_taproot_like: bool = True


class OrdinalIndexer:
    """Scanner for ordinal-style inscriptions.

    This class wires the existing RPC client into ordinal discovery routines.
    Heavy parsing logic is intentionally deferred; this skeleton focuses on
    API design and iteration boundaries for future scanning heuristics.
    """

    def __init__(self, rpc_client: DigiByteRPCClient) -> None:
        """Initialize the indexer with an RPC client.

        Args:
            rpc_client: An instance of :class:`~enigmatic_dgb.rpc_client.DigiByteRPCClient`
                or a compatible interface capable of fetching raw blocks and
                transactions.
        """

        self.rpc_client = rpc_client

    def _iter_block_range(self, config: OrdinalScanConfig) -> Iterable[dict]:
        """Yield decoded block JSONs for the configured range.

        The defaults iterate from ``start_height`` through ``end_height`` (or the
        current best height) respecting an optional ``limit`` on the number of
        blocks. This scaffolding is intentionally light and is expected to be
        replaced with pagination and cache-aware behavior.

        TODO: Expand to support reverse iteration and streaming from an
        external index when available.
        """

        best_height = self.rpc_client.get_best_height()
        start_height = config.start_height if config.start_height is not None else 0
        end_height = config.end_height if config.end_height is not None else best_height
        yielded = 0

        for height in range(start_height, end_height + 1):
            if config.limit is not None and yielded >= config.limit:
                break
            yield self.rpc_client.getblock_by_height(height)
            yielded += 1

    def _scan_block(self, block_json: dict) -> List[OrdinalLocation]:
        """Inspect a decoded block for inscription-style outputs.

        This placeholder walks transaction shells but intentionally performs no
        deep parsing yet. Future implementations will check for OP_RETURN
        outputs and Taproot-like witness payloads before constructing
        :class:`OrdinalLocation` results.

        TODO: Implement OP_RETURN scraping and Taproot-style witness scanning.
        """

        candidate_locations: List[OrdinalLocation] = []
        for _tx in block_json.get("tx", []):
            # TODO: Inspect outputs and witness data for inscription markers.
            continue

        return candidate_locations

    def scan_range(self, config: OrdinalScanConfig) -> List[OrdinalLocation]:
        """Scan a block range for candidate ordinal inscription outputs.

        This method should walk the blockchain according to ``config`` and
        collect outputs that look like inscription carriers (e.g., OP_RETURN
        messages or Taproot-like witness patterns). The exact heuristics will
        evolve; for now, this function is a stub ready for later expansion.

        Args:
            config: Range bounds and feature toggles for the scan.

        Returns:
            A list of candidate :class:`OrdinalLocation` instances.
        """

        raise NotImplementedError("Range scanning is not implemented yet")

    def scan_tx(self, txid: str) -> List[OrdinalLocation]:
        """Inspect a single transaction for ordinal-style outputs.

        The implementation is expected to fetch the transaction via the RPC
        client and apply light heuristics to identify inscription-like data
        carriers. Future revisions will consider OP_RETURN parsing and
        Taproot-style witness introspection.

        Args:
            txid: Hex-encoded transaction identifier.

        Returns:
            A list of candidate :class:`OrdinalLocation` records, possibly
            empty if no inscription-style data is detected.
        """

        raise NotImplementedError("Transaction scanning is not implemented yet")
