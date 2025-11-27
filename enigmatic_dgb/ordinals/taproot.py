"""Taproot-adjacent inspection utilities for ordinal discovery.

These helpers perform lightweight checks against transaction outputs to flag
Taproot-like patterns. They intentionally avoid full BIP341 validation and are
expected to evolve as inscription heuristics mature. The goal is to surface
enough raw information to support inscription detection and decoding without
attempting consensus-level validation.
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
    script_pubkey_type: str | None
    script_pubkey_hex: str | None
    internal_key_hex: str | None
    witness_stack: List[str]
    control_block_hex: str | None
    leaf_script_hex: str | None
    notes: str | None


def inspect_output_for_taproot(rpc_client, txid: str, vout: int) -> TaprootScriptView:
    """Best-effort inspection of a transaction output for Taproot patterns.

    This helper intentionally stops short of full BIP341/BIP342 validation. It
    detects Taproot-like outputs by examining the ``scriptPubKey`` for version
    1 witness programs and by collecting raw witness data from every input.
    The goal is to expose enough low-level material (witness stack, control
    blocks, possible leaf scripts) for downstream inscription detection.
    """

    verbose_tx: Dict[str, Any] = rpc_client.get_raw_transaction(txid, verbose=True)
    outputs = verbose_tx.get("vout", [])
    target_output = next((o for o in outputs if o.get("n") == vout), None)
    script_pubkey = target_output.get("scriptPubKey", {}) if target_output else {}
    script_pubkey_type = script_pubkey.get("type")
    script_pubkey_hex = script_pubkey.get("hex")
    asm = script_pubkey.get("asm", "") or ""

    asm_tokens = asm.strip().split()
    op_1_prefix = len(asm_tokens) >= 2 and asm_tokens[0].upper() == "OP_1"
    pushed_key = asm_tokens[1] if op_1_prefix else ""
    has_32_byte_push = op_1_prefix and len(pushed_key) == 64

    # DigiByte Core mirrors Bitcoin's naming for Taproot outputs, but we allow a
    # loose match on the type to account for dialect differences.
    script_type_lower = script_pubkey_type.lower() if script_pubkey_type else ""
    is_declared_taproot = script_type_lower == "witness_v1_taproot" or "taproot" in script_type_lower
    is_taproot_like = bool(is_declared_taproot or (op_1_prefix and has_32_byte_push))

    witness_stack: List[str] = []
    for vin in verbose_tx.get("vin", []):
        witness = vin.get("txinwitness") or []
        witness_stack.extend(str(item) for item in witness)

    internal_key_hex: Optional[str] = None
    notes: List[str] = []
    if is_taproot_like and script_pubkey_hex:
        try:
            script_bytes = bytes.fromhex(script_pubkey_hex)
            # Best-effort parse: OP_1 (0x51), push 32 (0x20), followed by the
            # x-only internal key. Anything outside this shape is recorded as a
            # TODO for stricter script parsing.
            if len(script_bytes) >= 34 and script_bytes[0] == 0x51 and script_bytes[1] == 0x20:
                internal_key_hex = script_bytes[2:34].hex()
            else:
                notes.append("scriptPubKey not in standard OP_1 <32-byte> form; taproot parse skipped")
        except ValueError:
            notes.append("scriptPubKey hex could not be decoded; taproot parse skipped")

    control_block_hex: Optional[str] = None
    leaf_script_hex: Optional[str] = None
    for item in witness_stack:
        try:
            raw = bytes.fromhex(item)
        except ValueError:
            notes.append("witness item was not valid hex; skipping control-block/script heuristics")
            continue

        length = len(raw)
        first_byte = raw[0] if raw else None

        # BIP341 control blocks begin with version byte in [0xC0, 0xFF] and are
        # 33 bytes for key-path spends or longer when parity bits and merkle
        # paths are present. This heuristic is intentionally permissive; TODO:
        # tighten validation once full control block parsing is available.
        if control_block_hex is None and first_byte is not None and 0xC0 <= first_byte <= 0xFF:
            if length in (33,) or length >= 65:
                control_block_hex = item
                continue

        # Skip probable DER signatures when looking for a redeem script. Taproot
        # leaf scripts can be arbitrary; we only capture the first witness item
        # that is neither a control block nor an obvious signature.
        if leaf_script_hex is None:
            is_likely_signature = first_byte == 0x30 and 8 < length < 80
            if not is_likely_signature:
                leaf_script_hex = item

    # If nothing in the script or witness hinted at Taproot, bail early with a
    # minimal view to avoid leaking unrelated witness data.
    if not is_taproot_like:
        return TaprootScriptView(
            txid=txid,
            vout=vout,
            is_taproot_like=False,
            script_pubkey_type=script_pubkey_type,
            script_pubkey_hex=script_pubkey_hex,
            internal_key_hex=None,
            witness_stack=witness_stack,
            control_block_hex=None,
            leaf_script_hex=None,
            notes="; ".join(notes) or None,
        )

    return TaprootScriptView(
        txid=txid,
        vout=vout,
        is_taproot_like=is_taproot_like,
        script_pubkey_type=script_pubkey_type,
        script_pubkey_hex=script_pubkey_hex,
        internal_key_hex=internal_key_hex,
        witness_stack=witness_stack,
        control_block_hex=control_block_hex,
        leaf_script_hex=leaf_script_hex,
        notes="; ".join(notes) or None,
    )
