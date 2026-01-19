"""Minimal HTTP JSON API for Enigmatic encode/decode helpers."""

from __future__ import annotations

import argparse
import json
import logging
import os
from decimal import Decimal, InvalidOperation
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
from .ordinals import OrdinalInscriptionDecoder
from .rpc_client import DigiByteRPC, RPCError

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
        }
        handler = routes.get(path)
        if handler is None:
            self._send_json(404, {"error": "not_found"})
            return

        try:
            payload = self._read_json_body()
            response = handler(payload)
        except (ValueError, BinaryEncodingError, RPCError) as exc:
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


def _make_rpc(wallet_override: str | None = None) -> DigiByteRPC:
    overrides = {}
    if wallet_override is not None:
        overrides["wallet"] = wallet_override
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
    rpc = _make_rpc()
    decoder = OrdinalInscriptionDecoder(rpc)
    try:
        results = decoder.decode_from_tx(txid)
    except RPCError as exc:
        if exc.code == -5 and rpc.config.wallet:
            base_rpc = _make_rpc(wallet_override="")
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
