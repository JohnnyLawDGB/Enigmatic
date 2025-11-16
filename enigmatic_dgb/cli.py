"""Command line interface for the Enigmatic DigiByte tooling."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Sequence
from uuid import uuid4

from .encoder import EnigmaticEncoder, SpendInstruction
from .model import EncodingConfig, EnigmaticMessage
from .rpc_client import ConfigurationError, DigiByteRPC, RPCError
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

    return parser


def _parse_payload_json(payload_json: str) -> Dict[str, Any]:
    try:
        data = json.loads(payload_json) if payload_json else {}
    except json.JSONDecodeError as exc:  # pragma: no cover - input validation
        raise CLIError(f"Invalid payload JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CLIError("Payload JSON must be an object")
    return data


def _chunk_instructions(
    instructions: Sequence[SpendInstruction], max_per_tx: int
) -> List[List[SpendInstruction]]:
    if max_per_tx <= 0 or len(instructions) <= max_per_tx:
        return [list(instructions)] if instructions else []
    chunks: List[List[SpendInstruction]] = []
    current: List[SpendInstruction] = []
    for instruction in instructions:
        current.append(instruction)
        if len(current) >= max_per_tx:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _aggregate_outputs(instructions: Iterable[SpendInstruction]) -> Dict[str, float]:
    outputs: Dict[str, float] = defaultdict(float)
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
    instructions, fee = encoder.encode_message(message)

    if not instructions:
        raise CLIError("Encoder returned no spend instructions")

    builder = TransactionBuilder(rpc)
    txids: List[str] = []
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
        }
        print(json.dumps(data, separators=COMPACT_JSON_SEPARATORS))

    watcher.run_forever(emit)


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "send-message":
            cmd_send_message(args)
        elif args.command == "watch":
            cmd_watch(args)
        else:  # pragma: no cover - argparse enforces choices
            raise CLIError(f"Unknown command: {args.command}")
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        logger.info("Interrupted by user")
    except (CLIError, ConfigurationError, RPCError, RuntimeError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
