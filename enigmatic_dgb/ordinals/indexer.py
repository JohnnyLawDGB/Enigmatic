"""Ordinal-style index scaffolding for DigiByte.

This module defines foundational types and scanning stubs for locating
ordinal-style inscriptions on the DigiByte blockchain. The logic here is
non-consensus, experimental, and focused on discoverability rather than
formal ordinal numbering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set


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

    def __init__(self, rpc_client) -> None:
        """Initialize the indexer with an RPC client.

        Args:
            rpc_client: An instance of :class:`~enigmatic_dgb.rpc_client.DigiByteRPCClient`
                or a compatible interface capable of fetching raw blocks and
                transactions.
        """

        self.rpc_client = rpc_client

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
