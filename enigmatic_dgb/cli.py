"""Command line entry points for Enigmatic DigiByte tooling."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

from .encoder import EnigmaticEncoder
from .model import EncodingConfig, EnigmaticMessage
from .rpc_client import DigiByteRPC
from .tx_builder import TransactionBuilder
from .watcher import Watcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enigmatic DigiByte CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    send_parser = subparsers.add_parser("send-message", help="encode and send a message")
    send_parser.add_argument("--to-address", required=True)
    send_parser.add_argument("--intent", required=True)
    send_parser.add_argument("--channel", default="default")
    send_parser.add_argument("--payload-json", default="{}")

    watch_parser = subparsers.add_parser("watch", help="watch an address for packets")
    watch_parser.add_argument("--address", required=True)
    watch_parser.add_argument("--poll-interval", type=int, default=30)

    return parser


def cmd_send_message(args: argparse.Namespace) -> None:
    rpc = DigiByteRPC.from_env()
    config = EncodingConfig.enigmatic_default()
    builder = TransactionBuilder(rpc)

    payload: Dict[str, Any]
    try:
        payload = json.loads(args.payload_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid payload JSON: {exc}")

    message = EnigmaticMessage(
        id=str(uuid4()),
        timestamp=datetime.utcnow(),
        channel=args.channel,
        intent=args.intent,
        payload=payload,
    )

    encoder = EnigmaticEncoder(config, target_address=args.to_address)
    instructions, fee = encoder.encode_message(message)

    outputs: Dict[str, float] = {}
    for instruction in instructions:
        outputs.setdefault(instruction.to_address, 0.0)
        outputs[instruction.to_address] += instruction.amount

    txid = builder.send_payment_tx(outputs, fee)
    print(json.dumps({"txid": txid}))


def cmd_watch(args: argparse.Namespace) -> None:
    rpc = DigiByteRPC.from_env()
    config = EncodingConfig.enigmatic_default()
    watcher = Watcher(rpc, args.address, config, poll_interval_seconds=args.poll_interval)

    def emit(message: EnigmaticMessage) -> None:
        data = {
            "timestamp": message.timestamp.isoformat(),
            "channel": message.channel,
            "intent": message.intent,
            "payload": message.payload,
        }
        print(json.dumps(data))

    watcher.run_forever(emit)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "send-message":
        cmd_send_message(args)
    elif args.command == "watch":
        cmd_watch(args)
    else:  # pragma: no cover - argparse enforces commands
        parser.error("Unknown command")


if __name__ == "__main__":
    main()
