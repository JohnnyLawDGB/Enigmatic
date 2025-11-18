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
from collections import defaultdict, OrderedDict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Sequence
from uuid import uuid4

from .dialect import DialectError, load_dialect
from .encoder import EnigmaticEncoder, SpendInstruction, aggregate_spend_instructions
from .model import EncodingConfig, EnigmaticMessage
from .planner import (
    AutomationDialect,
    PatternPlan,
    PatternPlanSequence,
    PlanningError,
    PlannedChain,
    SymbolPlanner,
    broadcast_pattern_plan,
    plan_explicit_pattern,
    PREVIOUS_CHANGE_SENTINEL,
)
from .rpc_client import ConfigurationError, DigiByteRPC, RPCConfig, RPCError
from .script_plane import ScriptPlane
from .session import SessionContext
from .symbol_sender import SessionRequiredError, prepare_symbol_send
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
    symbol_parser.add_argument(
        "--fee",
        default=None,
        help="Override the per-transaction fee punctuation defined by the dialect",
    )
    symbol_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Encode and summarize the symbol without broadcasting",
    )

    planner_parser = subparsers.add_parser(
        "plan-symbol",
        help="Plan or broadcast a symbol defined in an automation dialect",
    )
    planner_parser.add_argument(
        "--dialect-path",
        default="examples/dialect-heartbeat.yaml",
        help="Path to the automation dialect YAML file",
    )
    planner_parser.add_argument(
        "--symbol",
        help="Symbol name (defaults to the first entry in the dialect)",
    )
    planner_parser.add_argument(
        "--receiver-address",
        help="Optional receiver override for the value-plane output",
    )
    planner_parser.add_argument(
        "--broadcast",
        action="store_true",
        help="Broadcast the plan after inspection",
    )
    planner_parser.add_argument(
        "--as-chain",
        action="store_true",
        help="Plan the symbol as a chained message using the dialect frames",
    )
    planner_parser.add_argument(
        "--max-frames",
        type=int,
        help="Limit the number of frames when planning a chained symbol",
    )
    planner_parser.add_argument("--rpc-url", help="Override RPC endpoint URL")
    planner_parser.add_argument("--rpc-host", help="Override RPC host")
    planner_parser.add_argument(
        "--rpc-port", type=int, help="Override RPC port (default from dialect)"
    )
    planner_parser.add_argument("--rpc-user", help="Override RPC username")
    planner_parser.add_argument("--rpc-password", help="Override RPC password")
    planner_parser.add_argument("--rpc-wallet", help="Override RPC wallet name")
    https_group = planner_parser.add_mutually_exclusive_group()
    https_group.add_argument(
        "--rpc-use-https",
        dest="rpc_use_https",
        action="store_const",
        const=True,
        help="Force HTTPS when contacting the node",
    )
    https_group.add_argument(
        "--rpc-use-http",
        dest="rpc_use_https",
        action="store_const",
        const=False,
        help="Force HTTP when contacting the node",
    )
    planner_parser.set_defaults(rpc_use_https=None)

    pattern_parser = subparsers.add_parser(
        "plan-pattern",
        help="Plan or broadcast an explicit payment pattern",
    )
    pattern_parser.add_argument("--to-address", required=True, help="Destination DGB address")
    pattern_parser.add_argument(
        "--amounts",
        required=True,
        help="Comma-separated list of output amounts in DGB",
    )
    pattern_parser.add_argument(
        "--fee",
        default="0.21",
        help="Transaction fee in DGB (default: 0.21)",
    )
    pattern_parser.add_argument(
        "--broadcast",
        action="store_true",
        help="Broadcast the plan after inspection",
    )
    pattern_parser.add_argument(
        "--wallet-name",
        "--rpc-wallet",
        dest="rpc_wallet",
        help="Override RPC wallet name",
    )
    pattern_parser.add_argument("--rpc-url", help="Override RPC endpoint URL")
    pattern_parser.add_argument("--rpc-host", help="Override RPC host")
    pattern_parser.add_argument("--rpc-port", type=int, help="Override RPC port")
    pattern_parser.add_argument("--rpc-user", help="Override RPC username")
    pattern_parser.add_argument("--rpc-password", help="Override RPC password")
    pattern_parser.add_argument(
        "--min-confirmations",
        type=int,
        default=1,
        help="Minimum confirmations required for funding UTXOs (default: 1)",
    )
    pattern_parser.add_argument(
        "--wait-between-txs",
        type=float,
        default=0.0,
        help="Seconds to wait between chained broadcasts or confirmation polls",
    )
    pattern_parser.add_argument(
        "--min-confirmations-between-steps",
        type=int,
        default=0,
        help="Confirmations required between chained steps (default: 0)",
    )
    pattern_parser.add_argument(
        "--max-wait-seconds",
        type=float,
        default=600.0,
        help="Maximum time to wait for confirmations before aborting (default: 600)",
    )
    pattern_https_group = pattern_parser.add_mutually_exclusive_group()
    pattern_https_group.add_argument(
        "--rpc-use-https",
        dest="rpc_use_https",
        action="store_const",
        const=True,
        help="Force HTTPS when contacting the node",
    )
    pattern_https_group.add_argument(
        "--rpc-use-http",
        dest="rpc_use_https",
        action="store_const",
        const=False,
        help="Force HTTP when contacting the node",
    )
    pattern_parser.set_defaults(rpc_use_https=None)

    chain_parser = subparsers.add_parser(
        "plan-chain",
        help="Plan or broadcast a chained symbol using dialect frames",
    )
    chain_parser.add_argument(
        "--dialect-path",
        default="examples/dialect-heartbeat.yaml",
        help="Path to the automation dialect YAML file",
    )
    chain_parser.add_argument(
        "--symbol",
        help="Symbol name (defaults to the first entry in the dialect)",
    )
    chain_parser.add_argument(
        "--to-address",
        required=True,
        help="Destination address for the chained message",
    )
    chain_parser.add_argument(
        "--min-confirmations",
        type=int,
        help="Override the dialect min_confirmations when selecting funding UTXOs",
    )
    chain_parser.add_argument(
        "--max-frames",
        type=int,
        help="Limit the number of frames included in the chain",
    )
    chain_mode = chain_parser.add_mutually_exclusive_group()
    chain_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect the plan without broadcasting (default)",
    )
    chain_mode.add_argument(
        "--broadcast",
        action="store_true",
        help="Broadcast the chained plan after inspection",
    )
    chain_parser.add_argument("--rpc-url", help="Override RPC endpoint URL")
    chain_parser.add_argument("--rpc-host", help="Override RPC host")
    chain_parser.add_argument(
        "--rpc-port", type=int, help="Override RPC port (default from dialect)"
    )
    chain_parser.add_argument("--rpc-user", help="Override RPC username")
    chain_parser.add_argument("--rpc-password", help="Override RPC password")
    chain_parser.add_argument("--rpc-wallet", help="Override RPC wallet name")
    chain_parser.add_argument(
        "--wait-between-txs",
        type=float,
        default=0.0,
        help="Seconds to wait between chained broadcasts or confirmation polls",
    )
    chain_parser.add_argument(
        "--min-confirmations-between-steps",
        type=int,
        default=0,
        help="Confirmations required between chained frames (default: 0)",
    )
    chain_parser.add_argument(
        "--max-wait-seconds",
        type=float,
        default=600.0,
        help="Maximum time to wait for confirmations before aborting (default: 600)",
    )
    chain_https_group = chain_parser.add_mutually_exclusive_group()
    chain_https_group.add_argument(
        "--rpc-use-https",
        dest="rpc_use_https",
        action="store_const",
        const=True,
        help="Force HTTPS when contacting the node",
    )
    chain_https_group.add_argument(
        "--rpc-use-http",
        dest="rpc_use_https",
        action="store_const",
        const=False,
        help="Force HTTP when contacting the node",
    )
    chain_parser.set_defaults(rpc_use_https=None)

    send_sequence_parser = subparsers.add_parser(
        "send-sequence",
        help="Send an explicit chained payment sequence",
    )
    _configure_sequence_parser(send_sequence_parser, include_mode_flags=True)

    plan_sequence_parser = subparsers.add_parser(
        "plan-sequence",
        help="Inspect a chained payment sequence without broadcasting",
    )
    _configure_sequence_parser(plan_sequence_parser, include_mode_flags=False)

    return parser


def _configure_sequence_parser(parser: argparse.ArgumentParser, *, include_mode_flags: bool) -> None:
    parser.add_argument("--to-address", required=True, help="Destination DGB address")
    parser.add_argument(
        "--amounts",
        required=True,
        help="Comma-separated list of output amounts in DGB (e.g. 73,61,47)",
    )
    parser.add_argument(
        "--fee",
        default="0.21",
        help="Per-transaction fee in DGB (default: 0.21)",
    )
    parser.add_argument(
        "--min-confirmations",
        type=int,
        default=1,
        help="Minimum confirmations required for funding UTXOs (default: 1)",
    )
    parser.add_argument(
        "--wait-between-txs",
        type=float,
        default=0.0,
        help="Seconds to wait between chained broadcasts or confirmation polls",
    )
    parser.add_argument(
        "--min-confirmations-between-steps",
        type=int,
        default=0,
        help="Confirmations required between chained steps (default: 0)",
    )
    parser.add_argument(
        "--max-wait-seconds",
        type=float,
        default=600.0,
        help="Maximum time to wait for confirmations before aborting (default: 600)",
    )
    parser.add_argument(
        "--op-return-hex",
        help="Comma-separated list of OP_RETURN payloads encoded as hex",
    )
    parser.add_argument(
        "--op-return-ascii",
        help="Comma-separated list of OP_RETURN payloads encoded as ASCII",
    )
    if include_mode_flags:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Plan the sequence without broadcasting",
        )
    else:
        parser.set_defaults(dry_run=True)


def _parse_payload_json(payload_json: str) -> dict[str, Any]:
    try:
        data = json.loads(payload_json) if payload_json else {}
    except json.JSONDecodeError as exc:  # pragma: no cover - input validation
        raise CLIError(f"Invalid payload JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CLIError("Payload JSON must be an object")
    return data


def _parse_amounts_csv(raw: str) -> list[Decimal]:
    parts = _split_csv(raw)
    if not parts:
        raise CLIError("--amounts must include at least one value")
    amounts: list[Decimal] = []
    for index, part in enumerate(parts):
        try:
            amount = Decimal(part)
        except InvalidOperation as exc:  # pragma: no cover - input validation
            raise CLIError(f"Amount #{index + 1} is not a valid decimal value: {part}") from exc
        amounts.append(amount)
    return amounts


def _split_csv(raw: str) -> list[str]:
    return [segment.strip() for segment in raw.split(",") if segment.strip()]


def _parse_decimal(value: str, flag: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - input validation
        raise CLIError(f"{flag} must be a valid decimal value") from exc


def _parse_max_frames(value: int | None) -> int | None:
    """Validate the --max-frames flag shared by the planning commands."""

    if value is None:
        return None
    if value <= 0:
        raise CLIError("--max-frames must be positive")
    return value


def _format_decimal(value: Decimal) -> str:
    """Format Decimal values with fixed precision for human summaries."""

    return f"{value:.8f}"


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


def _aggregate_outputs(
    instructions: Iterable[SpendInstruction],
) -> tuple[dict[str, float], list[str]]:
    outputs, op_returns = aggregate_spend_instructions(instructions)
    return outputs, [data.hex() for data in op_returns]


def _parse_op_return_args(
    op_return_hex: str | None, op_return_ascii: str | None, expected: int
) -> list[str | None]:
    if expected <= 0:
        return []
    if op_return_hex and op_return_ascii:
        raise CLIError("Specify either --op-return-hex or --op-return-ascii, not both")
    if not op_return_hex and not op_return_ascii:
        return [None] * expected
    values = _split_csv(op_return_hex or op_return_ascii or "")
    if len(values) != expected:
        raise CLIError("Number of OP_RETURN entries must match the number of --amounts")
    if op_return_hex:
        normalized: list[str | None] = []
        for entry in values:
            normalized.append(_normalize_hex(entry))
        return normalized
    ascii_payloads: list[str] = []
    for entry in values:
        if not entry:
            raise CLIError("OP_RETURN ASCII entries must be non-empty")
        ascii_payloads.append(entry.encode("utf-8").hex())
    return ascii_payloads


def _normalize_hex(value: str) -> str:
    candidate = value.strip().lower()
    if candidate.startswith("0x"):
        candidate = candidate[2:]
    if not candidate:
        raise CLIError("Hex payloads must be non-empty")
    try:
        bytes.fromhex(candidate)
    except ValueError as exc:  # pragma: no cover - input validation
        raise CLIError(f"Invalid hex payload: {value}") from exc
    return candidate


def _print_symbol_summary(
    message: EnigmaticMessage, outputs: dict[str, float], op_returns: list[str], fee: float
) -> None:
    print(f"Symbol summary for {message.payload.get('symbol', message.intent)} on {message.channel}")
    for address, amount in outputs.items():
        print(f"  → {_format_decimal(Decimal(str(amount)))} DGB to {address}")
    if op_returns:
        for idx, payload in enumerate(op_returns, start=1):
            hint = payload
            try:
                decoded = bytes.fromhex(payload).decode("utf-8")
                if decoded:
                    hint = f"{decoded} ({payload})"
            except (UnicodeDecodeError, ValueError):  # pragma: no cover - display only
                hint = payload
            print(f"  OP_RETURN #{idx}: {hint}")
    print(f"  Fee punctuation: {_format_decimal(Decimal(str(fee)))} DGB")


def _print_sequence_summary(plan: PatternPlanSequence, op_returns: Sequence[str | None]) -> None:
    print("Sequence plan:")
    for index, step in enumerate(plan.steps, start=1):
        input_total = sum(entry.amount for entry in step.inputs)
        outputs_desc = ", ".join(
            f"{_format_decimal(output.amount)} → {output.address}" for output in step.outputs
        )
        if not outputs_desc:
            outputs_desc = "(no value outputs)"
        change_desc = (
            f"change {_format_decimal(step.change_output.amount)} → {step.change_output.address}"
            if step.change_output is not None
            else "no change"
        )
        op_payload = op_returns[index - 1] if index - 1 < len(op_returns) else None
        op_hint = "-"
        if op_payload:
            op_hint = op_payload
            try:
                decoded = bytes.fromhex(op_payload).decode("utf-8")
                if decoded:
                    op_hint = f"{decoded} ({op_payload})"
            except (UnicodeDecodeError, ValueError):  # pragma: no cover - display only
                op_hint = op_payload
        script_desc = _format_script_plane(step.script_plane)
        print(
            f"  Tx {index}: {len(step.inputs)} input(s) totaling {_format_decimal(input_total)} DGB "
            f"→ {outputs_desc} | fee {_format_decimal(step.fee)} DGB | {change_desc} | "
            f"OP_RETURN {op_hint} | script {script_desc}"
        )


def _execute_sequence_plan(
    builder: TransactionBuilder,
    plan: PatternPlanSequence,
    op_returns: Sequence[str | None],
) -> list[str]:
    """Legacy helper retained for tests that exercise the previous interface."""

    if len(op_returns) != len(plan.steps):
        raise CLIError("OP_RETURN payload count must match the number of transactions")
    previous_change_ref: tuple[str, int] | None = None
    txids: list[str] = []
    for index, step in enumerate(plan.steps):
        inputs: list[dict[str, Any]] = []
        for entry in step.inputs:
            if entry.txid == PREVIOUS_CHANGE_SENTINEL:
                if previous_change_ref is None:
                    raise CLIError(
                        "Chained plan referenced a change output before it was created"
                    )
                inputs.append({"txid": previous_change_ref[0], "vout": previous_change_ref[1]})
            else:
                inputs.append({"txid": entry.txid, "vout": entry.vout})
        ordered_outputs: OrderedDict[str, float] = OrderedDict()
        for output in step.outputs:
            ordered_outputs[output.address] = float(output.amount)
        change_index: int | None = None
        if step.change_output is not None:
            change_index = len(step.outputs)
            ordered_outputs[step.change_output.address] = float(step.change_output.amount)
        payload = op_returns[index]
        op_return_list = [payload] if payload else None
        txid = builder.send_payment_tx(
            ordered_outputs,
            float(step.fee),
            op_return_data=op_return_list,
            inputs=inputs,
            script_plane=step.script_plane,
        )
        txids.append(txid)
        if change_index is not None:
            previous_change_ref = (txid, change_index)
        else:
            previous_change_ref = None
    return txids


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
        outputs, op_returns = _aggregate_outputs(chunk)
        txid = builder.send_payment_tx(outputs, fee, op_return_data=op_returns)
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

    fee_override = None
    if args.fee is not None:
        fee_override = float(_parse_decimal(args.fee, "--fee"))

    try:
        message, instructions, fee = prepare_symbol_send(
            dialect,
            args.symbol,
            args.to_address,
            channel=args.channel,
            extra_payload=extra_payload,
            encrypt_with_passphrase=args.encrypt_with_passphrase,
            session=session,
            fee_override=fee_override,
        )
    except SessionRequiredError as exc:
        raise CLIError(str(exc)) from exc

    outputs, op_returns_hex = _aggregate_outputs(instructions)
    if args.dry_run:
        _print_symbol_summary(message, outputs, op_returns_hex, fee)
        summary = {
            "symbol": args.symbol,
            "channel": args.channel,
            "fee": f"{fee:.8f}",
            "outputs": outputs,
            "op_returns": op_returns_hex,
        }
        print(json.dumps(summary, indent=2))
        return

    builder = TransactionBuilder(rpc)
    txid = builder.send_payment_tx(outputs, fee, op_return_data=op_returns_hex)
    print(json.dumps({"txids": [txid]}, separators=COMPACT_JSON_SEPARATORS))


def _rpc_from_automation_args(args: argparse.Namespace, automation_endpoint: str, automation_wallet: str | None) -> DigiByteRPC:
    config = RPCConfig.from_sources(
        user=args.rpc_user,
        password=args.rpc_password,
        host=args.rpc_host,
        port=args.rpc_port,
        use_https=args.rpc_use_https,
        wallet=args.rpc_wallet or automation_wallet,
        endpoint=args.rpc_url or automation_endpoint,
    )
    return DigiByteRPC(config)


def _rpc_from_pattern_args(args: argparse.Namespace) -> DigiByteRPC:
    config = RPCConfig.from_sources(
        user=args.rpc_user,
        password=args.rpc_password,
        host=args.rpc_host,
        port=args.rpc_port,
        use_https=args.rpc_use_https,
        wallet=args.rpc_wallet,
        endpoint=args.rpc_url,
    )
    return DigiByteRPC(config)


def cmd_plan_symbol(args: argparse.Namespace) -> None:
    dialect = AutomationDialect.load(args.dialect_path)
    rpc = _rpc_from_automation_args(args, dialect.automation.endpoint, dialect.automation.wallet)
    planner = SymbolPlanner(rpc, dialect.automation)
    symbol = dialect.get_symbol(args.symbol)
    max_frames = _parse_max_frames(args.max_frames)
    if args.as_chain:
        chain = planner.plan_chain(symbol, receiver=args.receiver_address, max_frames=max_frames)
        print(json.dumps(chain.to_jsonable(), indent=2))
        if args.broadcast:
            txids = planner.broadcast_chain(chain)
            print(json.dumps({"txids": txids}, separators=COMPACT_JSON_SEPARATORS))
    else:
        plan = planner.plan(symbol, receiver=args.receiver_address)
        print(json.dumps(plan.to_jsonable(), indent=2))
        if args.broadcast:
            txid = planner.broadcast(plan)
            print(json.dumps({"txid": txid}, separators=COMPACT_JSON_SEPARATORS))


def cmd_plan_pattern(args: argparse.Namespace) -> None:
    amounts = _parse_amounts_csv(args.amounts)
    fee = _parse_decimal(args.fee, "--fee")
    rpc = _rpc_from_pattern_args(args)
    plan = plan_explicit_pattern(
        rpc,
        to_address=args.to_address,
        amounts=amounts,
        fee=fee,
        min_confirmations=args.min_confirmations,
    )
    print(json.dumps(plan.to_jsonable(), indent=2))
    if args.broadcast:
        txids = broadcast_pattern_plan(
            rpc,
            plan,
            wait_between_txs=args.wait_between_txs,
            min_confirmations_between_steps=args.min_confirmations_between_steps,
            max_wait_seconds=args.max_wait_seconds,
            progress_callback=_stdout_progress,
        )
        print(json.dumps({"txids": txids}, separators=COMPACT_JSON_SEPARATORS))


def cmd_plan_chain(args: argparse.Namespace) -> None:
    """Plan or broadcast a chained symbol defined in an automation dialect."""

    dialect = AutomationDialect.load(args.dialect_path)
    rpc = _rpc_from_automation_args(args, dialect.automation.endpoint, dialect.automation.wallet)
    planner = SymbolPlanner(rpc, dialect.automation)
    symbol = dialect.get_symbol(args.symbol)
    max_frames = _parse_max_frames(args.max_frames)
    chain = planner.plan_chain(
        symbol,
        receiver=args.to_address,
        max_frames=max_frames,
        min_confirmations=args.min_confirmations,
    )
    _print_chain_summary(chain)
    print(json.dumps(chain.to_jsonable(), indent=2))
    if args.broadcast:
        txids = planner.broadcast_chain(
            chain,
            wait_between_txs=args.wait_between_txs,
            min_confirmations_between_steps=args.min_confirmations_between_steps,
            max_wait_seconds=args.max_wait_seconds,
            progress_callback=_stdout_progress,
        )
        print(json.dumps({"txids": txids}, separators=COMPACT_JSON_SEPARATORS))


def cmd_send_sequence(args: argparse.Namespace) -> None:
    amounts = _parse_amounts_csv(args.amounts)
    fee = _parse_decimal(args.fee, "--fee")
    op_returns = _parse_op_return_args(args.op_return_hex, args.op_return_ascii, len(amounts))
    rpc = DigiByteRPC.from_env()
    plan = plan_explicit_pattern(
        rpc,
        to_address=args.to_address,
        amounts=amounts,
        fee=fee,
        min_confirmations=args.min_confirmations,
    )
    is_dry_run = getattr(args, "dry_run", False) or args.command == "plan-sequence"
    if is_dry_run:
        _print_sequence_summary(plan, op_returns)
        print(json.dumps(plan.to_jsonable(), indent=2))
        return
    builder = TransactionBuilder(rpc)
    txids = broadcast_pattern_plan(
        rpc,
        plan,
        op_returns=op_returns,
        wait_between_txs=args.wait_between_txs,
        min_confirmations_between_steps=args.min_confirmations_between_steps,
        max_wait_seconds=args.max_wait_seconds,
        progress_callback=_stdout_progress,
        builder=builder,
    )
    print(json.dumps({"txids": txids}, separators=COMPACT_JSON_SEPARATORS))


def _print_chain_summary(plan: PlannedChain) -> None:
    """Emit a human-readable list of the transactions in a chained plan."""

    if plan.initial_utxos:
        print("Funding UTXOs:")
        for utxo in plan.initial_utxos:
            print(
                f"  - {utxo.txid}:{utxo.vout} → {_format_decimal(utxo.amount)} DGB"
            )
    for index, tx in enumerate(plan.transactions, start=1):
        change_desc = (
            f"change {_format_decimal(tx.change_output.amount)} → {tx.change_output.address}"
            if tx.change_output is not None
            else "no change output"
        )
        script_desc = _format_script_plane(tx.script_plane)
        print(
            f"Frame {index}: send {_format_decimal(tx.to_output.amount)} DGB to {plan.to_address} "
            f"(fee {_format_decimal(tx.fee)} DGB); {change_desc} | script {script_desc}"
        )


def _format_script_plane(script_plane: ScriptPlane | None) -> str:
    if script_plane is None:
        return "legacy"
    parts = [script_plane.script_type]
    if script_plane.taproot_mode:
        parts.append(script_plane.taproot_mode)
    descriptor = "/".join(parts)
    if script_plane.branch_id is not None:
        descriptor += f" branch {script_plane.branch_id}"
    return descriptor


def _stdout_progress(message: str) -> None:
    print(message)


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
        elif args.command == "plan-symbol":
            cmd_plan_symbol(args)
        elif args.command == "plan-pattern":
            cmd_plan_pattern(args)
        elif args.command == "plan-chain":
            cmd_plan_chain(args)
        elif args.command in {"send-sequence", "plan-sequence"}:
            cmd_send_sequence(args)
        else:  # pragma: no cover - argparse enforces choices
            raise CLIError(f"Unknown command: {args.command}")
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        logger.info("Interrupted by user")
    except (
        CLIError,
        ConfigurationError,
        RPCError,
        RuntimeError,
        DialectError,
        PlanningError,
    ) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
