"""Taproot inscription reveal transaction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Iterable

from ..rpc_client import DigiByteRPC
from .inscriptions import encode_enig_taproot_payload
from .taproot import TaprootScriptBuilder
from .taproot_builder import DEFAULT_UNSPENDABLE_KEY, compute_taproot_output_from_script


class TaprootRevealError(RuntimeError):
    """Raised when building or validating a Taproot reveal transaction fails."""


@dataclass
class RevealInput:
    txid_le: bytes
    vout: int
    script_sig: bytes
    sequence: bytes


@dataclass
class RevealOutput:
    value_sats: int
    script_pubkey: bytes


def build_taproot_reveal_tx(
    rpc: DigiByteRPC,
    commit_txid: str,
    destination: str,
    payload: bytes,
    content_type: str,
    *,
    commit_vout: int | None = None,
    fee_dgb: str | Decimal = "0.00001",
    internal_key_hex: str | None = None,
) -> dict[str, Any]:
    """Return a signed reveal transaction hex plus metadata.

    The reveal spends the Taproot commitment output via script-path and embeds
    the inscription witness (leaf script + control block). It assumes the
    commitment output is unspendable via key-path and thus does not use wallet
    signatures for that input.
    """

    commit_tx = rpc.getrawtransaction(commit_txid, verbose=True)
    vout = _select_commit_vout(commit_tx, commit_vout)
    commit_amount = Decimal(str(vout["value"]))
    fee_amount = _parse_decimal(fee_dgb)
    output_amount = commit_amount - fee_amount

    if output_amount <= Decimal("0"):
        raise TaprootRevealError(
            f"Commit output {commit_amount} DGB is not enough to cover fee {fee_amount} DGB"
        )

    script_pubkey_hex = vout.get("scriptPubKey", {}).get("hex")
    if not script_pubkey_hex:
        raise TaprootRevealError("Commit output is missing scriptPubKey hex")

    output_key = _extract_taproot_output_key(script_pubkey_hex)

    envelope = encode_enig_taproot_payload(content_type, payload)
    leaf_script = TaprootScriptBuilder.build_enig_leaf(envelope)
    internal_key = (
        bytes.fromhex(internal_key_hex)
        if internal_key_hex is not None
        else DEFAULT_UNSPENDABLE_KEY
    )
    taproot_output = compute_taproot_output_from_script(leaf_script, internal_key)

    if taproot_output["output_key"] != output_key:
        raise TaprootRevealError(
            "Commitment output key does not match the provided payload "
            "(check payload/content-type/internal key)"
        )

    output_value = _quantize_dgb(output_amount)
    raw_tx = rpc.createrawtransaction(
        [{"txid": commit_txid, "vout": int(vout["n"])}],
        {destination: float(output_value)},
    )

    witness_stack = [
        b"\x01",
        leaf_script,
        bytes.fromhex(taproot_output["control_block"]),
    ]
    raw_tx_with_witness = _append_witness_to_raw_tx(raw_tx, [witness_stack])

    return {
        "raw_tx": raw_tx_with_witness,
        "commit_vout": int(vout["n"]),
        "output_amount": float(output_value),
        "fee_dgb": float(fee_amount),
        "control_block": taproot_output["control_block"],
        "leaf_script_hex": leaf_script.hex(),
        "output_key": taproot_output["output_key"],
    }


def _select_commit_vout(commit_tx: dict, commit_vout: int | None) -> dict:
    outputs = commit_tx.get("vout", []) or []
    if commit_vout is not None:
        for entry in outputs:
            if entry.get("n") == commit_vout:
                return entry
        raise TaprootRevealError(f"Commit vout {commit_vout} not found in tx")

    for entry in outputs:
        script_pubkey = entry.get("scriptPubKey", {}) or {}
        output_type = (script_pubkey.get("type") or "").lower()
        if output_type == "witness_v1_taproot":
            return entry

    raise TaprootRevealError("No Taproot output found in commit transaction")


def _extract_taproot_output_key(script_pubkey_hex: str) -> str:
    try:
        script = bytes.fromhex(script_pubkey_hex)
    except ValueError as exc:
        raise TaprootRevealError("Commit scriptPubKey hex is invalid") from exc
    if len(script) < 34 or script[0] != 0x51 or script[1] != 0x20:
        raise TaprootRevealError("Commit output is not a standard P2TR scriptPubKey")
    return script[2:34].hex()


def _parse_decimal(value: str | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise TaprootRevealError(f"Invalid decimal value: {value}") from exc


def _quantize_dgb(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)


def _encode_varint(value: int) -> bytes:
    if value < 0xFD:
        return bytes([value])
    if value <= 0xFFFF:
        return b"\xfd" + value.to_bytes(2, "little")
    if value <= 0xFFFFFFFF:
        return b"\xfe" + value.to_bytes(4, "little")
    return b"\xff" + value.to_bytes(8, "little")


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise TaprootRevealError("Unexpected end of raw transaction")
    prefix = data[offset]
    if prefix < 0xFD:
        return prefix, offset + 1
    if prefix == 0xFD:
        return int.from_bytes(data[offset + 1 : offset + 3], "little"), offset + 3
    if prefix == 0xFE:
        return int.from_bytes(data[offset + 1 : offset + 5], "little"), offset + 5
    return int.from_bytes(data[offset + 1 : offset + 9], "little"), offset + 9


def _append_witness_to_raw_tx(raw_hex: str, witnesses: list[list[bytes]]) -> str:
    raw = bytes.fromhex(raw_hex)
    if len(raw) < 6:
        raise TaprootRevealError("Raw transaction too short to decode")

    version = raw[0:4]
    marker = raw[4]
    flag = raw[5]
    if marker == 0x00 and flag == 0x01:
        raise TaprootRevealError("Raw transaction already includes witness data")

    offset = 4
    input_count, offset = _read_varint(raw, offset)
    inputs: list[RevealInput] = []
    for _ in range(input_count):
        txid_le = raw[offset : offset + 32]
        offset += 32
        vout = int.from_bytes(raw[offset : offset + 4], "little")
        offset += 4
        script_len, offset = _read_varint(raw, offset)
        script_sig = raw[offset : offset + script_len]
        offset += script_len
        sequence = raw[offset : offset + 4]
        offset += 4
        inputs.append(
            RevealInput(
                txid_le=txid_le,
                vout=vout,
                script_sig=script_sig,
                sequence=sequence,
            )
        )

    output_count, offset = _read_varint(raw, offset)
    outputs: list[RevealOutput] = []
    for _ in range(output_count):
        value_sats = int.from_bytes(raw[offset : offset + 8], "little")
        offset += 8
        script_len, offset = _read_varint(raw, offset)
        script_pubkey = raw[offset : offset + script_len]
        offset += script_len
        outputs.append(
            RevealOutput(value_sats=value_sats, script_pubkey=script_pubkey)
        )

    if offset + 4 > len(raw):
        raise TaprootRevealError("Raw transaction missing locktime")
    locktime = raw[offset : offset + 4]

    if len(witnesses) != len(inputs):
        raise TaprootRevealError("Witness count must match input count")

    serialized = bytearray()
    serialized.extend(version)
    serialized.extend(b"\x00\x01")
    serialized.extend(_encode_varint(len(inputs)))
    for entry in inputs:
        serialized.extend(entry.txid_le)
        serialized.extend(entry.vout.to_bytes(4, "little"))
        serialized.extend(_encode_varint(len(entry.script_sig)))
        serialized.extend(entry.script_sig)
        serialized.extend(entry.sequence)

    serialized.extend(_encode_varint(len(outputs)))
    for entry in outputs:
        serialized.extend(entry.value_sats.to_bytes(8, "little"))
        serialized.extend(_encode_varint(len(entry.script_pubkey)))
        serialized.extend(entry.script_pubkey)

    for witness in witnesses:
        serialized.extend(_encode_varint(len(witness)))
        for item in witness:
            serialized.extend(_encode_varint(len(item)))
            serialized.extend(item)

    serialized.extend(locktime)
    return serialized.hex()

