"""Minimal HTTP JSON API for Enigmatic encode/decode helpers."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from .binary_packets import BinaryEncodingError, decode_binary_packets_to_text
from .binary_packets import encode_text_to_binary_packets
from .config import load_rpc_config
from .dtsp import (
    DTSP_CONTROL,
    DTSP_TOLERANCE,
    closest_dtsp_symbol,
    decode_dtsp_sequence_to_message,
    encode_message_to_dtsp_sequence,
)
from .planner import (
    DUST_LIMIT,
    PlanningError,
    broadcast_pattern_plan,
    plan_explicit_pattern,
    plan_independent_pattern,
)
from .ordinals import OrdinalInscriptionDecoder
from .rpc_client import DigiByteRPC, RPCError
from .tx_builder import TransactionBuilder

logger = logging.getLogger(__name__)

EIGHT_DP = Decimal("0.00000001")


class EnigmaticAPIServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class, *, allow_origin: str | None):
        super().__init__(server_address, handler_class)
        self.allow_origin = allow_origin


class EnigmaticAPIHandler(BaseHTTPRequestHandler):
    server: EnigmaticAPIServer

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.client_address[0], format % args)

    def do_OPTIONS(self) -> None:  # noqa: N802 - http.server signature
        self._send_json(204, {})

    def do_GET(self) -> None:  # noqa: N802 - http.server signature
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server signature
        path = urlparse(self.path).path
        routes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "/encode/dtsp": _handle_encode_dtsp,
            "/decode/dtsp": _handle_decode_dtsp,
            "/encode/binary": _handle_encode_binary,
            "/decode/binary": _handle_decode_binary,
            "/decode/ord": _handle_decode_ord,
            "/plan/sequence": _handle_plan_sequence,
            "/send/sequence": _handle_send_sequence,
            "/plan/pattern": _handle_plan_pattern,
            "/send/pattern": _handle_send_pattern,
        }
        handler = routes.get(path)
        if handler is None:
            self._send_json(404, {"error": "not_found"})
            return

        try:
            payload = self._read_json_body()
            response = handler(payload)
        except (ValueError, BinaryEncodingError, RPCError, PlanningError) as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Unhandled API error")
            self._send_json(500, {"error": str(exc)})
            return

        self._send_json(200, response)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if self.server.allow_origin:
            self.send_header("Access-Control-Allow-Origin", self.server.allow_origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON payload: {exc}") from exc
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise ValueError("JSON payload must be an object")
        return payload


def _format_amount(value: Decimal | float) -> str:
    quantized = Decimal(str(value)).quantize(EIGHT_DP)
    return f"{quantized:.8f}"


def _parse_amounts(raw: list[Any]) -> list[Decimal]:
    amounts: list[Decimal] = []
    for entry in raw:
        try:
            amounts.append(Decimal(str(entry)))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid amount: {entry}") from exc
    return amounts


def _handle_encode_dtsp(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message")
    if not isinstance(message, str):
        raise ValueError("message must be a string")
    include_accept = bool(payload.get("include_accept", False))
    include_handshake = bool(payload.get("include_handshake", True) or include_accept)
    sequence = encode_message_to_dtsp_sequence(
        message, include_start_end=include_handshake
    )
    if include_accept and sequence:
        sequence.insert(1, DTSP_CONTROL["ACCEPT"])
    return {
        "amounts": [_format_amount(value) for value in sequence],
        "sequence": ",".join(f"{value:.8f}" for value in sequence),
    }


def _handle_decode_dtsp(payload: dict[str, Any]) -> dict[str, Any]:
    raw_amounts = payload.get("amounts")
    if not isinstance(raw_amounts, list):
        raise ValueError("amounts must be a list")
    tolerance = float(payload.get("tolerance", DTSP_TOLERANCE))
    strip_handshake = bool(payload.get("strip_handshake", False))
    amounts = [float(amount) for amount in _parse_amounts(raw_amounts)]
    message = decode_dtsp_sequence_to_message(
        amounts,
        require_start_end=not strip_handshake,
        tolerance=tolerance,
    )
    if strip_handshake:
        for token in ("start", "accept", "end"):
            message = message.replace(token, "")
    response: dict[str, Any] = {"message": message}
    if payload.get("show_matches"):
        matches = []
        for value in amounts:
            symbol, error = closest_dtsp_symbol(value, tolerance)
            matches.append(
                {
                    "amount": f"{value:.8f}",
                    "symbol": symbol,
                    "error": error,
                }
            )
        response["matches"] = matches
    return response


def _handle_encode_binary(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("text")
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    base_amount = Decimal(str(payload.get("base_amount", "0.0001")))
    bits_per_char = int(payload.get("bits_per_char", 8))
    packets = encode_text_to_binary_packets(
        text, base_amount=base_amount, bits_per_char=bits_per_char
    )
    return {
        "packets": [
            {
                "letter": packet.letter,
                "bits": packet.bits,
                "amount": _format_amount(packet.amount),
            }
            for packet in packets
        ],
        "amounts": [_format_amount(packet.amount) for packet in packets],
    }


def _handle_decode_binary(payload: dict[str, Any]) -> dict[str, Any]:
    raw_amounts = payload.get("amounts")
    if not isinstance(raw_amounts, list):
        raise ValueError("amounts must be a list")
    base_amount = Decimal(str(payload.get("base_amount", "0.0001")))
    bits_per_char = int(payload.get("bits_per_char", 8))
    amounts = _parse_amounts(raw_amounts)
    text = decode_binary_packets_to_text(
        amounts, base_amount=base_amount, bits_per_char=bits_per_char
    )
    return {"text": text}


def _make_rpc(
    wallet_override: str | None = None, payload: dict[str, Any] | None = None
) -> DigiByteRPC:
    overrides: dict[str, Any] = {}
    if wallet_override is not None:
        overrides["wallet"] = wallet_override
    rpc_override = payload.get("rpc") if isinstance(payload, dict) else None
    if isinstance(rpc_override, dict):
        for key in ("user", "password", "host", "port", "use_https", "wallet", "endpoint"):
            if key in rpc_override:
                overrides[key] = rpc_override[key]
    return DigiByteRPC(load_rpc_config(overrides=overrides or None))


def _payload_to_dict(payload_obj: Any) -> dict[str, Any]:
    metadata = payload_obj.metadata
    return {
        "txid": metadata.location.txid,
        "vout": metadata.location.vout,
        "height": metadata.location.height,
        "protocol": metadata.protocol,
        "content_type": metadata.content_type,
        "length": metadata.length,
        "codec": metadata.codec,
        "notes": metadata.notes,
        "decoded_text": payload_obj.decoded_text,
        "decoded_json": payload_obj.decoded_json,
    }


def _handle_decode_ord(payload: dict[str, Any]) -> dict[str, Any]:
    txid = payload.get("txid")
    if not isinstance(txid, str) or not txid:
        raise ValueError("txid must be a non-empty string")
    vout = payload.get("vout")
    rpc = _make_rpc(payload=payload)
    decoder = OrdinalInscriptionDecoder(rpc)
    try:
        results = decoder.decode_from_tx(txid)
    except RPCError as exc:
        if exc.code == -5 and rpc.config.wallet:
            base_rpc = _make_rpc(wallet_override="", payload=payload)
            decoder = OrdinalInscriptionDecoder(base_rpc)
            results = decoder.decode_from_tx(txid)
        else:
            raise

    if vout is not None:
        try:
            vout_idx = int(vout)
        except (TypeError, ValueError) as exc:
            raise ValueError("vout must be an integer") from exc
        results = [
            payload_obj
            for payload_obj in results
            if payload_obj.metadata.location.vout == vout_idx
        ]
    return {"payloads": [_payload_to_dict(item) for item in results]}


def _parse_sequence_amounts(payload: dict[str, Any]) -> list[Decimal]:
    raw_amounts = payload.get("amounts")
    if not isinstance(raw_amounts, list) or not raw_amounts:
        raise ValueError("amounts must be a non-empty list")
    return _parse_amounts(raw_amounts)


def _parse_op_returns(payload: dict[str, Any], expected: int) -> list[str | None]:
    op_hex = payload.get("op_return_hex")
    op_ascii = payload.get("op_return_ascii")
    if op_hex and op_ascii:
        raise ValueError("Provide either op_return_hex or op_return_ascii, not both")
    if not op_hex and not op_ascii:
        return [None] * expected
    values = op_hex or op_ascii
    if not isinstance(values, list) or len(values) != expected:
        raise ValueError("OP_RETURN list must match the number of amounts")
    if op_hex:
        normalized: list[str | None] = []
        for entry in values:
            if not isinstance(entry, str):
                raise ValueError("op_return_hex entries must be strings")
            candidate = entry.strip().lower()
            if candidate.startswith("0x"):
                candidate = candidate[2:]
            if not candidate:
                raise ValueError("op_return_hex entries must be non-empty")
            try:
                bytes.fromhex(candidate)
            except ValueError as exc:
                raise ValueError(f"Invalid hex payload: {entry}") from exc
            normalized.append(candidate)
        return normalized
    ascii_payloads: list[str] = []
    for entry in values:
        if not isinstance(entry, str) or not entry:
            raise ValueError("op_return_ascii entries must be non-empty strings")
        ascii_payloads.append(entry.encode("utf-8").hex())
    return ascii_payloads


def _parse_utxo_refs(raw_refs: list[Any]) -> list[tuple[str, int]]:
    refs: list[tuple[str, int]] = []
    for entry in raw_refs:
        if not isinstance(entry, str) or ":" not in entry:
            raise ValueError("use_utxos entries must look like txid:vout")
        txid, vout_str = entry.split(":", 1)
        try:
            vout = int(vout_str)
        except ValueError as exc:
            raise ValueError(f"Invalid vout index: {entry}") from exc
        refs.append((txid, vout))
    return refs


def _load_selected_utxos(
    rpc: DigiByteRPC, raw_refs: list[Any] | None, min_confirmations: int
) -> list[dict[str, Any]]:
    if not raw_refs:
        return []
    references = _parse_utxo_refs(raw_refs)
    available = rpc.listunspent(min_confirmations)
    indexed = {
        (entry["txid"], int(entry["vout"])): entry
        for entry in available
        if entry.get("spendable", True)
    }
    missing = [ref for ref in references if ref not in indexed]
    if missing:
        missing_desc = ", ".join(f"{txid}:{vout}" for txid, vout in missing)
        raise ValueError("Requested UTXOs not found or not spendable: " + missing_desc)
    return [indexed[ref] for ref in references]


def _wait_for_tx_confirmations(
    rpc: DigiByteRPC, txid: str, min_confirmations: int, max_wait_seconds: float | None
) -> None:
    target = max(1, min_confirmations)
    waited = 0.0
    poll_interval = 5.0
    while True:
        try:
            info = rpc.gettransaction(txid)
        except RPCError:
            info = {}
        confirmations = int(info.get("confirmations", 0) or 0)
        if confirmations >= target:
            return
        if max_wait_seconds is not None and waited >= max_wait_seconds:
            raise ValueError("Preparation transaction did not confirm in time")
        time.sleep(poll_interval)
        waited += poll_interval


def _auto_prepare_utxos(
    rpc: DigiByteRPC,
    builder: TransactionBuilder,
    amounts: list[Decimal],
    fee: Decimal,
    min_confirmations: int,
    prepare_fee: Decimal,
    max_wait_seconds: float | None,
) -> list[dict[str, Any]]:
    buffer_amount = max(DUST_LIMIT, Decimal("0.0002"))
    funding_confirmations = max(1, min_confirmations)
    outputs_payload: list[dict[str, Any]] = []
    addresses: list[str] = []
    for amount in amounts:
        target = (amount + fee + buffer_amount).quantize(EIGHT_DP)
        if target <= 0:
            raise ValueError("Auto-prepared UTXO target amount must be positive")
        address = rpc.getnewaddress()
        outputs_payload.append({address: float(target)})
        addresses.append(address)
    signed_hex = builder.build_custom_tx(
        outputs_payload, float(prepare_fee), min_confirmations=funding_confirmations
    )
    txid = rpc.sendrawtransaction(signed_hex)
    _wait_for_tx_confirmations(
        rpc, txid, funding_confirmations, max_wait_seconds
    )
    prepared = rpc.listunspent(funding_confirmations, 9999999, addresses)
    if len(prepared) < len(addresses):
        raise ValueError("Auto-prepared UTXOs were not detected after confirmation")
    return prepared


def _ensure_independent_funding(
    rpc: DigiByteRPC,
    builder: TransactionBuilder,
    amounts: list[Decimal],
    fee: Decimal,
    min_confirmations: int,
    selected_utxos: list[dict[str, Any]],
    *,
    auto_prepare: bool,
    auto_prepare_fee: Decimal | None,
    allow_unconfirmed: bool,
    max_wait_seconds: float | None,
) -> list[dict[str, Any]]:
    required = len(amounts)
    if required <= 1:
        return selected_utxos
    if selected_utxos:
        if len(selected_utxos) < required:
            raise ValueError(
                "Independent sequences require one UTXO per step; provide more use_utxos or enable chained mode."
            )
        return selected_utxos
    count_minconf = min_confirmations if allow_unconfirmed else max(1, min_confirmations)
    if len(rpc.listunspent(count_minconf)) >= required:
        return selected_utxos
    if not auto_prepare:
        raise ValueError(
            "Independent sequences require enough confirmed UTXOs; enable auto_prepare_utxos or provide use_utxos."
        )
    prepare_fee = auto_prepare_fee if auto_prepare_fee is not None else fee
    return _auto_prepare_utxos(
        rpc,
        builder,
        amounts,
        fee,
        min_confirmations,
        prepare_fee,
        max_wait_seconds,
    )


def _plan_sequence(
    rpc: DigiByteRPC,
    payload: dict[str, Any],
) -> PatternPlanSequence:
    amounts = _parse_sequence_amounts(payload)
    fee = Decimal(str(payload.get("fee", "0.21")))
    min_confirmations = int(payload.get("min_confirmations", 1))
    allow_unconfirmed = bool(payload.get("allow_unconfirmed", False))
    chained = bool(payload.get("chained", False))
    use_utxos = payload.get("use_utxos")
    selected = _load_selected_utxos(
        rpc, use_utxos, min_confirmations
    )
    planner_fn = plan_explicit_pattern if chained else plan_independent_pattern
    return planner_fn(
        rpc,
        to_address=payload.get("to_address"),
        amounts=amounts,
        fee=fee,
        min_confirmations=min_confirmations,
        preferred_utxos=selected or None,
        allow_unconfirmed_chain=allow_unconfirmed,
    )


def _handle_plan_sequence(payload: dict[str, Any]) -> dict[str, Any]:
    to_address = payload.get("to_address")
    if not isinstance(to_address, str) or not to_address:
        raise ValueError("to_address is required")
    amounts = _parse_sequence_amounts(payload)
    op_returns = _parse_op_returns(payload, expected=len(amounts))
    rpc = _make_rpc(payload=payload)
    plan = _plan_sequence(rpc, payload)
    return {
        "plan": plan.to_jsonable(),
        "op_returns": op_returns,
    }


def _handle_send_sequence(payload: dict[str, Any]) -> dict[str, Any]:
    to_address = payload.get("to_address")
    if not isinstance(to_address, str) or not to_address:
        raise ValueError("to_address is required")
    amounts = _parse_sequence_amounts(payload)
    op_returns = _parse_op_returns(payload, expected=len(amounts))
    fee = Decimal(str(payload.get("fee", "0.21")))
    min_confirmations = int(payload.get("min_confirmations", 1))
    allow_unconfirmed = bool(payload.get("allow_unconfirmed", False))
    chained = bool(payload.get("chained", False))
    single_tx = bool(payload.get("single_tx", False))
    auto_prepare = bool(payload.get("auto_prepare_utxos", False))
    auto_prepare_fee = payload.get("auto_prepare_fee")
    auto_prepare_fee_decimal = (
        Decimal(str(auto_prepare_fee)) if auto_prepare_fee is not None else None
    )
    min_conf_between = int(payload.get("min_confirmations_between_steps", 0))
    wait_between = float(payload.get("wait_between_txs", 0.0))
    max_wait_seconds = payload.get("max_wait_seconds")
    max_wait = float(max_wait_seconds) if max_wait_seconds is not None else None

    rpc = _make_rpc(payload=payload)
    use_utxos = payload.get("use_utxos")
    selected = _load_selected_utxos(rpc, use_utxos, min_confirmations)

    # Support pinned change address and RBF from caller
    change_address = payload.get("change_address")
    replaceable = payload.get("replaceable")
    builder = TransactionBuilder(
        rpc,
        change_address=change_address if isinstance(change_address, str) else None,
        default_replaceable=bool(replaceable) if replaceable is not None else None,
    )
    if not chained and not single_tx:
        selected = _ensure_independent_funding(
            rpc,
            builder,
            amounts,
            fee,
            min_confirmations,
            selected,
            auto_prepare=auto_prepare,
            auto_prepare_fee=auto_prepare_fee_decimal,
            allow_unconfirmed=allow_unconfirmed,
            max_wait_seconds=max_wait,
        )
    planner_fn = plan_explicit_pattern if chained else plan_independent_pattern
    plan = planner_fn(
        rpc,
        to_address=payload.get("to_address"),
        amounts=amounts,
        fee=fee,
        min_confirmations=min_confirmations,
        preferred_utxos=selected or None,
        allow_unconfirmed_chain=allow_unconfirmed or single_tx,
    )
    txids = broadcast_pattern_plan(
        rpc,
        plan,
        op_returns=op_returns,
        wait_between_txs=wait_between,
        min_confirmations_between_steps=min_conf_between,
        min_confirmations=min_confirmations,
        max_wait_seconds=max_wait,
        builder=builder,
        single_tx=single_tx,
    )
    return {"txids": txids}


def _handle_plan_pattern(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    to_address = cleaned.get("to_address")
    if not isinstance(to_address, str) or not to_address:
        raise ValueError("to_address is required")
    cleaned.pop("op_return_hex", None)
    cleaned.pop("op_return_ascii", None)
    amounts = _parse_sequence_amounts(cleaned)
    rpc = _make_rpc(payload=cleaned)
    plan = _plan_sequence(rpc, cleaned)
    return {"plan": plan.to_jsonable(), "op_returns": [None] * len(amounts)}


def _handle_send_pattern(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload.pop("op_return_hex", None)
    payload.pop("op_return_ascii", None)
    return _handle_send_sequence(payload)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Minimal HTTP API for Enigmatic encode/decode helpers"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("ENIGMATIC_API_HOST", "127.0.0.1"),
        help="Bind host (default: 127.0.0.1 or ENIGMATIC_API_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ENIGMATIC_API_PORT", "8123")),
        help="Bind port (default: 8123 or ENIGMATIC_API_PORT)",
    )
    parser.add_argument(
        "--allow-origin",
        default=os.getenv("ENIGMATIC_API_ALLOW_ORIGIN", ""),
        help="Optional CORS allow-origin value",
    )
    args = parser.parse_args(argv)

    allow_origin = args.allow_origin or None
    server = EnigmaticAPIServer(
        (args.host, args.port), EnigmaticAPIHandler, allow_origin=allow_origin
    )
    logging.basicConfig(level=logging.INFO)
    logger.info("Enigmatic API listening on %s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
