"""Taproot-adjacent inspection utilities for ordinal discovery.

These helpers perform lightweight checks against transaction outputs to flag
Taproot-like patterns. They intentionally avoid full BIP341 validation and are
expected to evolve as inscription heuristics mature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class TaprootScriptView:
    """Summarizes witness and script data for a transaction output."""

    txid: str
    vout: int
    is_taproot_like: bool
    witness_fields: List[str]
    script_hex: Optional[str]


def inspect_output_for_taproot(rpc_client, txid: str, vout: int) -> TaprootScriptView:
    """Inspect a transaction output for taproot-like witness data.

    The current heuristic only checks for the presence of witness fields and
    simple script patterns. Future work should expand this into full BIP341
    parsing and validation.
    """

    verbose_tx: Dict[str, Any] = rpc_client.get_raw_transaction(txid, verbose=True)
    outputs = verbose_tx.get("vout", [])
    target_output = next((o for o in outputs if o.get("n") == vout), None)
    script_hex: Optional[str] = None

    if target_output:
        script_hex = target_output.get("scriptPubKey", {}).get("hex")

    witness_fields: List[str] = []
    for vin in verbose_tx.get("vin", []):
        witness = vin.get("txinwitness") or []
        witness_fields.extend(str(item) for item in witness)

    # TODO: Introduce stronger taproot detection heuristics once signing and
    # script parsing utilities are available.
    is_taproot_like = bool(witness_fields) or (script_hex is not None and script_hex.startswith("5120"))

    return TaprootScriptView(
        txid=txid,
        vout=vout,
        is_taproot_like=is_taproot_like,
        witness_fields=witness_fields,
        script_hex=script_hex,
    )
