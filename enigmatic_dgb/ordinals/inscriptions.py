"""Decoding helpers for ordinal-style inscriptions.

This module focuses on retrieving inscription payloads and translating them into
structured metadata. It does not implement a canonical ordinal numbering scheme;
all behavior is experimental and subject to iteration.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


ENIG_TAPROOT_MAGIC = b"ENIG"
ENIG_TAPROOT_VERSION_V1 = 1
ENIG_TAPROOT_PROTOCOL = "enigmatic/taproot-v1"


def encode_enig_taproot_payload(content_type: str, payload: bytes) -> bytes:
    """Encode a taproot inscription envelope per ``docs/taproot-dialect-v1.md``.

    The payload layout is ``ENIG`` magic + 1-byte version + 1-byte content-type
    length + UTF-8 content-type string + raw payload bytes. The version emitted
    by this helper is ``ENIG_TAPROOT_VERSION_V1``.
    """

    if not isinstance(content_type, str):
        raise ValueError("content_type must be a string")
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError("payload must be bytes")

    content_type_bytes = content_type.encode("utf-8")
    if len(content_type_bytes) > 255:
        raise ValueError("content_type is too long; must fit in one byte of length")

    return (
        ENIG_TAPROOT_MAGIC
        + bytes([ENIG_TAPROOT_VERSION_V1])
        + bytes([len(content_type_bytes)])
        + content_type_bytes
        + bytes(payload)
    )


def decode_enig_taproot_payload(data: bytes) -> Tuple[int, str, bytes]:
    """Decode an inscription envelope per ``docs/taproot-dialect-v1.md``.

    Validates the ``ENIG`` magic, parses the version byte and content-type
    header, and returns a tuple of ``(version, content_type, payload_bytes)``.
    Raises :class:`ValueError` with clear messages when parsing fails.
    """

    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("data must be bytes")
    if len(data) < len(ENIG_TAPROOT_MAGIC) + 2:
        raise ValueError("data too short to contain Enigmatic taproot envelope")
    if not data.startswith(ENIG_TAPROOT_MAGIC):
        raise ValueError("missing ENIG taproot magic")

    cursor = len(ENIG_TAPROOT_MAGIC)
    version = data[cursor]
    cursor += 1

    if cursor >= len(data):
        raise ValueError("missing content_type length byte")

    content_length = data[cursor]
    cursor += 1

    if len(data) < cursor + content_length:
        raise ValueError("data too short for declared content_type length")

    content_type_bytes = data[cursor : cursor + content_length]
    try:
        content_type = content_type_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("content_type is not valid UTF-8") from exc

    payload_bytes = data[cursor + content_length :]

    return version, content_type, payload_bytes

from enigmatic_dgb.ordinals.indexer import OrdinalIndexer, OrdinalLocation


@dataclass
class InscriptionMetadata:
    """Describes the decoded metadata for an inscription payload."""

    location: OrdinalLocation
    protocol: str
    version: Optional[int]
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

        This routine inspects both OP_RETURN-based inscriptions and Enigmatic
        Taproot dialect inscriptions. It leverages :class:`OrdinalIndexer` to
        surface candidate outputs and then routes each to the appropriate
        decoding path, keeping behavior backward-compatible for existing
        OP_RETURN flows.
        """

        tx = self.rpc_client.get_raw_transaction(txid, verbose=True)
        indexer = OrdinalIndexer(self.rpc_client)
        locations = indexer.scan_tx(txid)
        return _extract_candidate_payloads_from_tx(tx, locations, rpc_client=self.rpc_client)

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


class OrdinalInscriptionPlanner:
    """Skeleton planner for ordinal-style inscription creation.

    The planner intentionally stops short of building or signing transactions.
    It accepts the RPC client and optional helpers via dependency injection so
    that future revisions can integrate tightly with :mod:`planner` and
    :mod:`tx_builder` without changing the call sites. The returned dictionaries
    are intended for CLI inspection and carry enough hints for operators to
    understand what the *eventual* transaction would look like.
    """

    DEFAULT_FEE_ESTIMATE = 0.001  # Placeholder until tx_builder integration

    def __init__(self, rpc_client, tx_builder=None, planner=None) -> None:
        """Create a planner wired to RPC and transaction-building helpers.

        Parameters
        ----------
        rpc_client
            DigiByte RPC client used for fee lookups and wallet probing.
        tx_builder
            Optional transaction-building helper injected by callers so the
            planner can align its dry-run outputs with real construction
            routines.
        planner
            Optional higher-level planner/automation harness for future
            integrations.
        """

        self.rpc_client = rpc_client
        # Keep hooks to existing builders so we can slot them in later without
        # changing the CLI surface area. These are deliberately unused for now,
        # but are stored for parity with the transaction planning layer.
        self.tx_builder = tx_builder
        self.planner = planner

    def plan_op_return_inscription(
        self, message: bytes | str, metadata: dict | None = None
    ) -> dict:
        """Draft a plan for an OP_RETURN inscription.

        The payload is converted to bytes (hex decoding supported for string
        inputs) and captured as an OP_RETURN template. Funding amounts and fees
        are placeholders only—later revisions should request accurate estimates
        from :class:`~enigmatic_dgb.tx_builder.TransactionBuilder` and wallet
        policy.
        """

        payload_bytes = self._coerce_bytes(message)
        payload_hex = payload_bytes.hex()
        estimated_fee = self._estimate_fee_placeholder(len(payload_bytes))

        # TODO: integrate TransactionBuilder.build_payment_tx to derive exact
        # funding requirements, change outputs, and signature scope.
        proposed_outputs = [
            {
                "type": "op_return",
                "data_hex": payload_hex,
                "description": "Non-spendable inscription envelope (draft)",
            }
        ]

        plan_metadata: dict[str, Any] = {
            "payload_length": len(payload_bytes),
            "payload_preview": payload_bytes[:32].hex(),
            "notes": [
                "Fee and change are illustrative; tx_builder integration pending",
                "RPC wallet funding/selection will be delegated in a future patch",
            ],
        }
        if estimated_fee is not None:
            plan_metadata["estimated_fee"] = estimated_fee
        if metadata:
            plan_metadata["user_metadata"] = metadata

        return {
            "inscription_type": "op_return",
            "funding_amount": estimated_fee or 0.0,
            "outputs": proposed_outputs,
            "metadata": plan_metadata,
        }

    def plan_taproot_inscription(
        self, payload: bytes, metadata: dict | None = None
    ) -> dict:
        """Draft a plan for a Taproot inscription using the Enigmatic dialect.

        This remains a dry-run helper: it does not sign or broadcast anything
        and it currently uses a placeholder internal key. Future revisions
        should thread a hardened key derivation strategy and satisfaction
        script into the transaction-building layer.
        """

        if not isinstance(payload, (bytes, bytearray)):
            raise ValueError("payload must be bytes")

        metadata = metadata or {}
        content_type = metadata.get("content_type", "application/octet-stream")
        target_address = metadata.get("target_address")
        funding_wallet = metadata.get("funding_wallet")

        envelope = encode_enig_taproot_payload(content_type, bytes(payload))

        taproot_leaf_script = self._build_taproot_leaf_script(envelope)
        taproot_script_hex = taproot_leaf_script.hex()

        internal_key_hex = metadata.get(
            "internal_key_hex", "00" * 32
        )  # TODO: thread hardened internal key handling

        estimated_fee = self._estimate_taproot_fee(len(envelope))

        proposed_outputs = [
            {
                "type": "taproot_v1",
                "internal_key_hex": internal_key_hex,
                "leaf_script_hex": taproot_script_hex,
                "description": "Taproot inscription leaf (draft, unsatisfied)",
            }
        ]

        # Mirror tx_builder semantics by sketching a change output. Exact
        # amounts are deferred to the real builder once fee and key-handling
        # utilities are wired in.
        change_preview = {
            "type": "change",
            "description": "Change output placeholder; amount assigned by builder",
        }

        plan_metadata: dict[str, Any] = {
            "protocol": ENIG_TAPROOT_PROTOCOL,
            "content_type": content_type,
            "payload_length": len(payload),
            "taproot_script_hex": taproot_script_hex,
            "notes": [
                "Plan-only: no signing or broadcast performed",
                "Leaf uses OP_FALSE OP_IF <envelope> OP_ENDIF; satisfaction script pending",
                "Internal key is a placeholder and should be replaced with a derived key",
            ],
        }
        if estimated_fee is not None:
            plan_metadata["estimated_fee"] = estimated_fee
        if target_address:
            plan_metadata["target_address"] = target_address
        if funding_wallet:
            plan_metadata["funding_wallet"] = funding_wallet
        if metadata:
            plan_metadata["user_metadata"] = metadata

        return {
            "inscription_type": "taproot_inscription",
            "protocol": ENIG_TAPROOT_PROTOCOL,
            "content_type": content_type,
            "funding_amount": estimated_fee or 0.0,
            "inputs": [
                {
                    "source": "wallet",
                    "assumption": "Single funding input; selection delegated to tx_builder",
                }
            ],
            "outputs": proposed_outputs + [change_preview],
            "metadata": plan_metadata,
        }

    @staticmethod
    def _coerce_bytes(message: bytes | str) -> bytes:
        if isinstance(message, bytes):
            return message
        if _is_hex(message):
            try:
                return bytes.fromhex(message)
            except ValueError:
                # Fall back to UTF-8 encoding when the hex parse fails to keep the
                # planner permissive for CLI experimentation.
                return message.encode("utf-8")
        return message.encode("utf-8")

    def _estimate_fee_placeholder(self, payload_length: int) -> float | None:
        """Return a rough fee placeholder for inscription planning.

        This is intentionally naive; the goal is to surface the need for funds
        without constraining the eventual transaction builder. Future revisions
        should query fee rates and size estimates directly from the node and
        tx_builder.
        """

        # Very rough heuristic: start with a baseline and scale slightly with
        # payload size so operators are nudged to keep inscriptions small.
        return round(self.DEFAULT_FEE_ESTIMATE + (payload_length * 0.0000005), 8)

    def _estimate_taproot_fee(self, envelope_length: int) -> float:
        """Estimate fee for a simple Taproot inscription transaction.

        The heuristic assumes one funding input, one Taproot output, and one
        change output. It prioritizes clarity over precision so operators can
        reason about funding needs before invoking the real transaction
        builder.
        """

        # Baseline virtual size approximations (in vbytes):
        # - Taproot input: ~58 vbytes
        # - Taproot output: ~43 vbytes
        # - Change output: ~31 vbytes (varies by address type)
        # - Overhead: ~10 vbytes
        # Add a small premium for the inscription envelope length.
        vbytes = 58 + 43 + 31 + 10 + (envelope_length / 8)
        # Target a conservative 10 sat/vbyte and convert to DGB assuming 1e8
        # satoshis per coin.
        sats = vbytes * 10
        return round(sats / 1e8, 8)

    @staticmethod
    def _build_taproot_leaf_script(envelope: bytes) -> bytes:
        """Construct a single-leaf Taproot script for the inscription envelope."""

        def _push_data(data: bytes) -> bytes:
            length = len(data)
            if length <= 75:
                return bytes([length]) + data
            if length <= 255:
                return b"\x4c" + bytes([length]) + data  # OP_PUSHDATA1
            raise ValueError("envelope too large for simple pushdata encoding")

        # OP_FALSE OP_IF <payload> OP_ENDIF
        return b"".join([b"\x00\x63", _push_data(envelope), b"\x68"])


def _extract_candidate_payloads_from_tx(
    tx_json: Dict[str, Any], locations: List[OrdinalLocation], rpc_client=None
) -> List[InscriptionPayload]:
    """Extract candidate inscription payloads from a transaction.

    This helper performs lightweight decoding for OP_RETURN-based inscriptions
    and Enigmatic Taproot dialect inscriptions. Taproot decoding is
    dialect-aware and looks for the ENIG magic within the leaf script before
    delegating to :func:`decode_enig_taproot_payload`. The helper is
    intentionally forgiving and will return as many payloads as it can recover
    without raising exceptions.
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
                version=None,
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
                version=None,
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

        elif location.ordinal_hint == "enig_taproot":
            if rpc_client is None:
                logger.debug("RPC client unavailable; cannot inspect taproot view for %s", location)
                continue

            try:
                from enigmatic_dgb.ordinals import taproot

                taproot_view = taproot.inspect_output_for_taproot(
                    rpc_client, location.txid, location.vout
                )
            except Exception:  # pragma: no cover - defensive against RPC hiccups
                logger.debug("Taproot inspection failed for %s", location, exc_info=True)
                continue

            leaf_hex = taproot_view.leaf_script_hex if taproot_view else None
            if not leaf_hex:
                logger.debug("No leaf script present for Enigmatic taproot location %s", location)
                continue

            try:
                leaf_bytes = bytes.fromhex(leaf_hex)
            except ValueError:
                logger.debug("Leaf script was not valid hex for %s", location)
                continue

            magic_index = leaf_bytes.find(ENIG_TAPROOT_MAGIC)
            if magic_index == -1:
                logger.debug("ENIG magic not found in leaf script for %s", location)
                continue

            envelope = leaf_bytes[magic_index:]
            try:
                version, content_type, payload_bytes = decode_enig_taproot_payload(envelope)
            except ValueError:
                logger.debug("Failed to decode Enigmatic taproot payload for %s", location, exc_info=True)
                continue

            decoded_text: Optional[str] = None
            if content_type and (
                content_type.startswith("text/")
                or content_type == "application/json"
                or content_type.endswith("+json")
            ):
                decoded_text = payload_bytes.decode("utf-8", errors="replace") if payload_bytes else ""

            decoded_json: Optional[Dict[str, Any]] = None
            if content_type == "application/json" and decoded_text:
                try:
                    decoded_json = json.loads(decoded_text)
                except (json.JSONDecodeError, TypeError):
                    decoded_json = None

            metadata = InscriptionMetadata(
                location=location,
                protocol=ENIG_TAPROOT_PROTOCOL,
                version=version,
                content_type=content_type,
                length=len(payload_bytes),
                codec="enigmatic/taproot-v1",
                notes="Enigmatic Taproot inscription candidate",
            )

            payloads.append(
                InscriptionPayload(
                    metadata=metadata,
                    raw_payload=payload_bytes,
                    decoded_text=decoded_text,
                    decoded_json=decoded_json,
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
