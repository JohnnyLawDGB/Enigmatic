"""Command line interface for the Enigmatic DigiByte tooling."""

from __future__ import annotations

"""Command-line interface for Enigmatic's experimental tooling.

The CLI exposes a thin, well-documented façade over the encoder, dialect, and
optional session helpers so that legitimate operators can experiment with
presence and identity signaling without writing custom Python.
"""

import argparse
import base64
import binascii
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Sequence
from uuid import uuid4

from .dialect import DialectError, load_dialect
from .encoder import EnigmaticEncoder, SpendInstruction
from .model import EncodingConfig, EnigmaticMessage
from .rpc_client import ConfigurationError, DigiByteRPC, RPCError
from .session import SessionContext
from .symbol_sender import SessionRequiredError, send_symbol
from .tx_builder import TransactionBuilder
from .watcher import Watcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMPACT_JSON_SEPARATORS = (",", ":")
MAX_OUTPUTS_PER_TX = 50


class CLIError(RuntimeError):
    """Raised when CLI arguments are invalid."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enigmatic DigiByte CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    send_parser = subparsers.add_parser(
        "send-message", help="encode a message and broadcast the spend pattern"
    )
    send_parser.add_argument("--to-address", required=True, help="Destination DGB address")
    send_parser.add_argument(
        "--intent",
        required=True,
        help="Semantic intent (identity, sync, presence, etc.)",
    )
    send_parser.add_argument(
        "--channel",
        default="default",
        help="Channel identifier used to group packets",
    )
    send_parser.add_argument(
        "--payload-json",
        default="{}",
        help="JSON object describing optional payload flags",
    )
    send_parser.add_argument(
        "--encrypt-with-passphrase",
        default=None,
        help="Optional shared secret used to encrypt the message payload",
    )

    watch_parser = subparsers.add_parser(
        "watch", help="watch an address for Enigmatic packets"
    )
    watch_parser.add_argument("--address", required=True, help="Address to observe")
    watch_parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Polling cadence in seconds (default: 30)",
    )

    symbol_parser = subparsers.add_parser(
        "send-symbol", help="send a symbolic dialect pattern"
    )
    symbol_parser.add_argument(
        "--dialect-path",
        required=True,
        help="Path to the dialect YAML file",
    )
    symbol_parser.add_argument("--symbol", required=True, help="Symbol name")
    symbol_parser.add_argument("--to-address", required=True, help="Destination address")
    symbol_parser.add_argument("--channel", default="default", help="Channel name")
    symbol_parser.add_argument(
        "--extra-payload-json",
        default="{}",
        help="Optional JSON payload merged into the symbol metadata",
    )
    symbol_parser.add_argument(
        "--encrypt-with-passphrase",
        default=None,
        help="Optional shared secret used to encrypt the symbol payload",
    )
    symbol_parser.add_argument(
        "--session-key-b64",
        default=None,
        help="Base64 session key negotiated via handshake",
    )
    symbol_parser.add_argument("--session-id", default=None, help="Session identifier")
    symbol_parser.add_argument(
        "--session-channel",
        default=None,
        help="Channel name tied to the provided session",
    )
    symbol_parser.add_argument(
        "--session-dialect",
        default=None,
        help="Dialect name tied to the provided session",
    )

    return parser


def _parse_payload_json(payload_json: str) -> dict[str, Any]:
    try:
        data = json.loads(payload_json) if payload_json else {}
    except json.JSONDecodeError as exc:  # pragma: no cover - input validation
        raise CLIError(f"Invalid payload JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CLIError("Payload JSON must be an object")
    return data


def _chunk_instructions(
    instructions: Sequence[SpendInstruction], max_per_tx: int
) -> list[list[SpendInstruction]]:
    if max_per_tx <= 0 or len(instructions) <= max_per_tx:
        return [list(instructions)] if instructions else []
    chunks: list[list[SpendInstruction]] = []
    current: list[SpendInstruction] = []
    for instruction in instructions:
        current.append(instruction)
        if len(current) >= max_per_tx:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _aggregate_outputs(instructions: Iterable[SpendInstruction]) -> dict[str, float]:
    outputs: dict[str, float] = defaultdict(float)
    for instruction in instructions:
        outputs[instruction.to_address] += instruction.amount
    return dict(outputs)


def cmd_send_message(args: argparse.Namespace) -> None:
    payload = _parse_payload_json(args.payload_json)
    message = EnigmaticMessage(
        id=str(uuid4()),
        timestamp=datetime.utcnow(),
        channel=args.channel,
        intent=args.intent,
        payload=payload,
    )

    rpc = DigiByteRPC.from_env()
    config = EncodingConfig.enigmatic_default()
    encoder = EnigmaticEncoder(config, target_address=args.to_address)
    instructions, fee = encoder.encode_message(
        message, encrypt_with_passphrase=args.encrypt_with_passphrase
    )

    if not instructions:
        raise CLIError("Encoder returned no spend instructions")

    builder = TransactionBuilder(rpc)
    txids: list[str] = []
    for chunk in _chunk_instructions(instructions, MAX_OUTPUTS_PER_TX):
        outputs = _aggregate_outputs(chunk)
        txid = builder.send_payment_tx(outputs, fee)
        txids.append(txid)

    result = {"message_id": message.id, "txids": txids}
    print(json.dumps(result, separators=COMPACT_JSON_SEPARATORS))


def cmd_watch(args: argparse.Namespace) -> None:
    rpc = DigiByteRPC.from_env()
    config = EncodingConfig.enigmatic_default()
    watcher = Watcher(
        rpc,
        address=args.address,
        config=config,
        poll_interval_seconds=args.poll_interval,
    )

    def emit(message: EnigmaticMessage) -> None:
        data = {
            "id": message.id,
            "timestamp": message.timestamp.isoformat(),
            "channel": message.channel,
            "intent": message.intent,
            "payload": message.payload,
            "encrypted": message.encrypted,
        }
        print(json.dumps(data, separators=COMPACT_JSON_SEPARATORS))

    watcher.run_forever(emit)


def cmd_send_symbol(args: argparse.Namespace) -> None:
    extra_payload = _parse_payload_json(args.extra_payload_json)
    dialect = load_dialect(args.dialect_path)
    rpc = DigiByteRPC.from_env()
    session: SessionContext | None = None
    if args.session_key_b64:
        if not args.session_id:
            raise CLIError("--session-id is required when --session-key-b64 is provided")
        try:
            session_key = base64.urlsafe_b64decode(args.session_key_b64.encode("ascii"))
        except (binascii.Error, ValueError) as exc:
            raise CLIError("Session key must be valid base64") from exc
        session_channel = args.session_channel or args.channel
        session_dialect = args.session_dialect or dialect.name
        session = SessionContext(
            session_id=args.session_id,
            channel=session_channel,
            dialect=session_dialect,
            created_at=datetime.utcnow(),
            session_key=session_key,
        )

    try:
        txids = send_symbol(
            rpc,
            dialect=dialect,
            symbol_name=args.symbol,
            to_address=args.to_address,
            channel=args.channel,
            extra_payload=extra_payload,
            encrypt_with_passphrase=args.encrypt_with_passphrase,
            session=session,
        )
    except SessionRequiredError as exc:
        raise CLIError(str(exc)) from exc
    print(json.dumps({"txids": txids}, separators=COMPACT_JSON_SEPARATORS))


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "send-message":
            cmd_send_message(args)
        elif args.command == "watch":
            cmd_watch(args)
        elif args.command == "send-symbol":
            cmd_send_symbol(args)
        else:  # pragma: no cover - argparse enforces choices
            raise CLIError(f"Unknown command: {args.command}")
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        logger.info("Interrupted by user")
    except (CLIError, ConfigurationError, RPCError, RuntimeError, DialectError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
