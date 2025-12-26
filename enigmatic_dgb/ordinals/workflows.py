"""Interactive and programmatic workflows for ordinal inscriptions.

This module centralizes the shared logic between the CLI ``ord-inscribe``
command and the interactive Taproot wizard. It intentionally reuses existing
builders and planners so downstream integrations avoid subprocess shims while
benefiting from the same fee selection, size checks, and broadcast steps.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .inscriptions import (
    ENIG_TAPROOT_MAGIC,
    ENIG_TAPROOT_VERSION_V1,
    OrdinalInscriptionPlanner,
    encode_enig_taproot_payload,
)
from .taproot import TaprootScriptBuilder
from ..fees import (
    DEFAULT_CONF_TARGET,
    DEFAULT_ESTIMATE_MODE,
    FeeSelectionResult,
    calculate_fee_sats,
    sat_vb_to_dgb_per_kvb,
    select_fee_rate,
)
from ..rpc_client import RPCError, format_rpc_hint
from ..tx_builder import TransactionBuilder


class InscriptionFlowError(RuntimeError):
    """Raised when inscription preparation or broadcast fails."""


@dataclass
class PreparedInscription:
    """Container describing a signed inscription transaction."""

    scheme: str
    content_type: str
    payload: bytes
    plan: dict
    fee_selection: FeeSelectionResult
    raw_tx: str
    vsize: int
    computed_fee_sats: int
    broadcast: bool
    rbf: bool
    txid: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "content_type": self.content_type,
            "payload_length": len(self.payload),
            "vsize": self.vsize,
            "fee_rate_sat_vb": self.fee_selection.fee_rate_sat_vb,
            "fee_sats": self.computed_fee_sats,
            "broadcast": self.broadcast,
            "rbf": self.rbf,
            "txid": self.txid,
        }


def compute_taproot_envelope_stats(payload: bytes, content_type: str) -> dict[str, int]:
    """Return envelope sizing details for Taproot inscriptions.

    The stats include the base payload length, the encoded Taproot envelope
    length (including magic/version/content-type bytes), the script push bytes
    for a single-element leaf, and the resulting leaf script length. The
    single-element push must not exceed 520 bytes under standard policy.
    """

    envelope = encode_enig_taproot_payload(content_type, payload)
    envelope_length = len(envelope)
    push_bytes = TaprootScriptBuilder.push_single_element(envelope)
    leaf_script = TaprootScriptBuilder.build_enig_leaf(envelope)
    return {
        "payload_bytes": len(payload),
        "envelope_bytes": envelope_length,
        "push_bytes": len(push_bytes),
        "leaf_script_bytes": len(leaf_script),
    }


def suggest_max_fee_sats(fee_sats: int) -> int:
    """Return a padded fee cap for user confirmation dialogs.

    The heuristic rounds 20% above the computed fee to the nearest 100k sats
    boundary. This keeps prompts simple while ensuring ample headroom for
    high-fee environments without silently doubling the spend.
    """

    if fee_sats <= 0:
        return 0
    padded = fee_sats * 1.20
    return int(math.ceil(padded / 100_000) * 100_000)


def prepare_inscription_transaction(
    rpc,
    payload: bytes,
    content_type: str,
    *,
    scheme: str = "taproot",
    conf_target: int | None = None,
    estimate_mode: str | None = None,
    user_fee_rate_satvb: float | None = None,
    min_fee_rate_satvb_floor: float | None = None,
    max_fee_sats: int | None = None,
    rbf: bool = True,
    broadcast: bool = False,
) -> PreparedInscription:
    """Plan, build, and optionally broadcast an inscription transaction."""

    builder = TransactionBuilder(rpc)
    planner = OrdinalInscriptionPlanner(rpc, tx_builder=builder)
    metadata = {"content_type": content_type}

    if scheme not in {"taproot", "op-return"}:
        raise InscriptionFlowError(f"Unsupported inscription scheme: {scheme}")

    if scheme == "op-return":
        plan = planner.plan_op_return_inscription(payload, metadata=metadata)
        inscription_hex = payload.hex()
    else:
        try:
            plan = planner.plan_taproot_inscription(payload, metadata=metadata)
        except ValueError as exc:
            raise InscriptionFlowError(str(exc)) from exc

        inscription_hex = plan.get("metadata", {}).get("taproot_script_hex")
        if not inscription_hex:
            raise InscriptionFlowError("Planner did not emit a Taproot inscription script; aborting")

    estimated_fee = _extract_estimated_fee(plan)
    if estimated_fee is None:
        raise InscriptionFlowError("Planner did not provide an estimated fee; refusing to proceed")

    fee_selection = select_fee_rate(
        rpc,
        conf_target=conf_target or DEFAULT_CONF_TARGET,
        estimate_mode=estimate_mode or DEFAULT_ESTIMATE_MODE,
        user_fee_rate_satvb=user_fee_rate_satvb,
        min_fee_rate_satvb_floor=min_fee_rate_satvb_floor,
    )
    fee_rate_override = sat_vb_to_dgb_per_kvb(fee_selection.fee_rate_sat_vb)
    guess_fee_sats = calculate_fee_sats(fee_selection.fee_rate_sat_vb, 250)
    guess_fee_dgb = guess_fee_sats / 1e8

    try:
        if scheme == "op-return":
            raw_tx = builder.build_payment_tx(
                {},
                float(guess_fee_dgb),
                op_return_data=[inscription_hex],
                fee_rate_override=fee_rate_override,
                replaceable=rbf,
            )
        else:
            try:
                inscription_address = rpc.getnewaddress(address_type="bech32m")
            except TypeError:  # pragma: no cover - older node compatibility
                inscription_address = rpc.getnewaddress()

            outputs_payload = [{inscription_address: 0.0001}]
            raw_tx = builder.build_custom_tx(
                outputs_payload,
                float(guess_fee_dgb),
                fee_rate_override=fee_rate_override,
                replaceable=rbf,
            )
    except RuntimeError as exc:
        raise InscriptionFlowError(f"Failed to build or sign the inscription transaction: {exc}") from exc

    decoded = rpc.decoderawtransaction(raw_tx)
    vsize = decoded.get("vsize") or decoded.get("size")
    if vsize is None:
        raise InscriptionFlowError("Could not decode vsize for inscription transaction; aborting")
    vsize_int = int(vsize)

    fee_selection = fee_selection.with_vsize(vsize_int)
    computed_fee_sats = fee_selection.fee_sats or 0
    computed_fee_dgb = computed_fee_sats / 1e8

    if max_fee_sats is not None and computed_fee_sats > max_fee_sats:
        raise InscriptionFlowError(
            f"Computed fee {computed_fee_sats} sats exceeds max-fee-sats {max_fee_sats}; "
            "increase the cap or lower the target feerate"
        )

    result = PreparedInscription(
        scheme=scheme,
        content_type=content_type,
        payload=payload,
        plan=plan,
        fee_selection=fee_selection,
        raw_tx=raw_tx,
        vsize=vsize_int,
        computed_fee_sats=computed_fee_sats,
        broadcast=broadcast,
        rbf=rbf,
    )

    if not broadcast:
        return result

    try:
        txid = rpc.sendrawtransaction(raw_tx)
    except RPCError as exc:
        hint = format_rpc_hint(exc)
        hint_suffix = f"\nHint: {hint}" if hint else ""
        raise InscriptionFlowError(f"Broadcast failed: {exc}{hint_suffix}") from exc

    result.txid = txid
    return result


def _extract_estimated_fee(plan: dict | None) -> float | None:
    metadata = (plan or {}).get("metadata", {}) if isinstance(plan, dict) else {}
    fee = metadata.get("estimated_fee") or (plan or {}).get("funding_amount")
    return float(fee) if fee is not None else None


def write_receipt(path: Path, payload: bytes, content_type: str, details: dict[str, Any]) -> Path:
    """Persist a JSON receipt for the inscription flow."""

    path.parent.mkdir(parents=True, exist_ok=True)
    receipt: dict[str, Any] = {
        "content_type": content_type,
        "payload_hex": payload.hex(),
    }
    receipt.update(details)
    path.write_text(json.dumps(receipt, indent=2))
    return path
