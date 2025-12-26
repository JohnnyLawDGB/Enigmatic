"""Interactive ASCII console for Enigmatic DigiByte tooling."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import traceback
from pathlib import Path
from typing import Any, List, Sequence

from . import cli
from . import prime_ladder
from .decoder import ObservedTx
from .dtsp import (
    DTSP_CONTROL,
    DTSPEncodingError,
    DTSP_TOLERANCE,
    closest_dtsp_symbol,
    decode_dtsp_sequence_to_message,
    encode_message_to_dtsp_sequence,
)
from .dialect import DialectError, load_dialect
from .model import EncodingConfig
from .rpc_client import ConfigurationError, DigiByteRPC, RPCError, RPCTransportError
from .ordinals.workflows import (
    compute_taproot_envelope_stats,
    prepare_inscription_transaction,
    suggest_max_fee_sats,
    write_receipt,
)
from .fees import calculate_fee_sats, sat_vb_to_dgb_per_kvb
from .watcher import Watcher

DEFAULT_FEE = 0.21
DEFAULT_DIALECT = "examples/dialect-showcase.yaml"
DTSP_GAP_SECONDS = 600.0
DEFAULT_TAPROOT_WALLET = "taproot-lab"


def prompt_str(prompt: str, default: str | None = None) -> str:
    """Prompt for a string value, honoring an optional default."""

    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if raw:
            return raw
        if default is not None:
            return default
        print("Please enter a value or provide a default.")


def prompt_float(prompt: str, default: float | None = None) -> float | None:
    """Prompt for a floating-point number, returning the default on blank input."""

    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            print("Invalid number, please try again.")


def prompt_int(prompt: str, default: int | None = None) -> int | None:
    """Prompt for an integer, returning the default on blank input."""

    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print("Invalid integer, please try again.")


def _prompt_send_mode() -> tuple[bool, str]:
    """Ask the user whether to send as chained frames or a single fan-out tx."""

    choice = (
        input(
            "Send as: [1] multiple transactions (frames) [2] single transaction (fan-out) [1]: "
        )
        .strip()
        .lower()
    )
    single_tx = choice == "2"
    mode_label = "SINGLE-TX (fan-out)" if single_tx else "MULTI-TX (frames)"
    return single_tx, mode_label


def _should_debug() -> bool:
    return bool(int(os.environ.get("ENIGMATIC_DEBUG", "0")))


def _safe_rpc_call(func, *, friendly_name: str) -> tuple[bool, Any]:
    try:
        return True, func()
    except (ConfigurationError, RPCTransportError, RPCError) as exc:
        print(f"{friendly_name} failed: {exc}")
        return False, None


def run_enigmatic_cli(args: Sequence[str]) -> int:
    """Invoke the Enigmatic CLI via subprocess or internal dispatcher."""

    executable = shutil.which("enigmatic-dgb")
    if executable:
        print(f"Running CLI: {executable} {' '.join(args)}")
        result = subprocess.run([executable, *args], capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode

    print("enigmatic-dgb executable not found; falling back to in-process dispatcher.")
    try:
        cli.main(args)
    except SystemExit as exc:  # argparse.exit surfaces as SystemExit
        return int(exc.code or 0)
    return 0


def _confirm(prompt: str = "Proceed? [y/N]: ") -> bool:
    return input(prompt).strip().lower().startswith("y")


def _pause(message: str = "Press Enter to return to the menu...") -> None:
    input(message)


def _prompt_choice(prompt: str, choices: dict[str, str]) -> str:
    """Prompt for a choice key present in ``choices``.

    Keys are compared in lower-case form and the first character match is
    accepted. Returns the canonical key as stored in the mapping.
    """

    while True:
        raw = input(prompt).strip().lower()
        for key in choices:
            if raw == key.lower() or raw == key.lower()[:1]:
                return key
        print("Invalid selection, please try again.\n")


def _parse_amounts_csv(raw: str) -> List[str]:
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def handle_quickstart() -> None:
    """Guide the user through sending a simple amount pattern."""

    print("\nQuickstart: Send a simple pattern\n" + "-" * 40)
    to_address = prompt_str("Destination address")
    amounts_raw = prompt_str("Comma-separated amounts (e.g. 21.21,7.0,0.978521)")
    fee = prompt_float("Fee per transaction", default=DEFAULT_FEE)
    dry_run = input("Dry run? [Y/n]: ").strip().lower() not in {"n", "no"}

    amounts = _parse_amounts_csv(amounts_raw)
    mode = "DRY RUN" if dry_run else "BROADCAST"
    print(
        textwrap.dedent(
            f"""
            You are about to:
            Command: enigmatic-dgb send-sequence
            To: {to_address}
            Amounts: {amounts}
            Fee per tx: {fee}
            Mode: {mode}
            """
    )
    )
    if not _confirm():
        print("Cancelled.")
        return

    args = [
        "send-sequence",
        "--to-address",
        to_address,
        "--amounts",
        amounts_raw,
        "--fee",
        str(fee if fee is not None else DEFAULT_FEE),
    ]
    if dry_run:
        args.append("--dry-run")

    code = run_enigmatic_cli(args)
    print(f"Command finished with exit code {code}\n")
    _pause()


def handle_dialect_symbols() -> None:
    """Plan or send a symbol defined by a dialect file."""

    current_dialect_path = DEFAULT_DIALECT

    while True:
        print(
            textwrap.dedent(
                """
                Dialect-driven symbols
                [1] Plan symbol (plan-symbol)
                [2] Send symbol (send-symbol)
                [L] List symbols in a dialect
                [B] Back
                """
            )
        )
        choice = input("Select an option: ").strip().lower()
        if choice in {"b", "0"}:
            return
        if choice == "l":
            dialect_path = prompt_str(
                "Dialect YAML path", default=current_dialect_path
            )
            current_dialect_path = dialect_path
            _list_dialect_symbols(dialect_path)
            continue
        if choice not in {"1", "2"}:
            print("Invalid selection, please try again.\n")
            continue

        dialect_path = prompt_str("Dialect YAML path", default=current_dialect_path)
        current_dialect_path = dialect_path
        symbol = prompt_str("Symbol name (use [L] to list)")
        to_address = None
        if choice == "2":
            to_address = prompt_str("Destination address")
        receiver_override = None
        if choice == "1":
            receiver_override = prompt_str("Receiver address (optional)", default="")
        channel = prompt_str("Channel", default="default") if choice == "2" else ""
        fee = prompt_float("Fee override (optional)", default=None) if choice == "2" else None
        dry_run = False
        broadcast_plan = False
        if choice == "2":
            dry_run = input("Dry run? [Y/n]: ").strip().lower() not in {"n", "no"}
        else:
            broadcast_plan = input("Broadcast after planning? [y/N]: ").strip().lower().startswith("y")

        args = ["send-symbol" if choice == "2" else "plan-symbol", "--dialect-path", dialect_path]
        if symbol:
            args.extend(["--symbol", symbol])
        if to_address:
            args.extend(["--to-address", to_address])
        if receiver_override:
            args.extend(["--receiver-address", receiver_override])
        if channel:
            args.extend(["--channel", channel])
        if fee is not None:
            args.extend(["--fee", str(fee)])
        if choice == "2" and dry_run:
            args.append("--dry-run")
        if choice == "1" and broadcast_plan:
            args.append("--broadcast")

        print(f"Running command: enigmatic-dgb {' '.join(args)}")
        code = run_enigmatic_cli(args)
        print(f"Command finished with exit code {code}\n")
        _pause()


def _list_dialect_symbols(dialect_path: str) -> None:
    """Load a dialect and print available symbols with descriptions."""

    try:
        dialect = load_dialect(dialect_path)
    except DialectError as exc:
        if _should_debug():
            traceback.print_exc()
        print(f"Failed to load dialect: {exc}")
        _pause()
        return

    print(
        textwrap.dedent(
            f"""
            Symbols available in {dialect.name} ({dialect_path}):
            Fee punctuation: {dialect.fee_punctuation}
            """
        )
    )
    for name, symbol in sorted(dialect.symbols.items()):
        print(f"  - {name}: {symbol.description}")
    _pause()


def handle_numeric_sequences() -> None:
    """Plan or send a numeric sequence pattern."""

    while True:
        print(
            textwrap.dedent(
                """
                Numeric sequences
                [1] Plan sequence
                [2] Send sequence
                [B] Back
                """
            )
        )
        choice = input("Select an option: ").strip().lower()
        if choice in {"b", "0"}:
            return
        if choice not in {"1", "2"}:
            print("Invalid selection, please try again.\n")
            continue

        to_address = prompt_str("Destination address")
        amounts_raw = prompt_str("Comma-separated amounts")
        fee = prompt_float("Fee per transaction", default=DEFAULT_FEE)
        dry_run = input("Dry run? [Y/n]: ").strip().lower() not in {"n", "no"}
        op_return_ascii = prompt_str("OP_RETURN ASCII hint (optional)", default="")
        single_tx = False
        mode_label = "MULTI-TX (frames)"
        if choice == "2":
            single_tx, mode_label = _prompt_send_mode()

        args = [
            "send-sequence" if choice == "2" else "plan-sequence",
            "--to-address",
            to_address,
            "--amounts",
            amounts_raw,
            "--fee",
            str(fee if fee is not None else DEFAULT_FEE),
        ]
        if op_return_ascii:
            args.extend(["--op-return-ascii", op_return_ascii])
        if dry_run:
            args.append("--dry-run")
        if single_tx:
            args.append("--single-tx")

        print(f"Running command: enigmatic-dgb {' '.join(args)}")
        print(f"Mode: {mode_label}")
        code = run_enigmatic_cli(args)
        print(f"Command finished with exit code {code}\n")
        _pause()


def _format_amount(amount: float) -> str:
    return f"{amount:.8f}".rstrip("0").rstrip(".")


def _collect_prime_burst_amounts() -> list[float]:
    """Prompt for a set of ladder indices to include in a fan-out burst."""

    print("Available ladder indices and ratios:")
    for index, p, q, ratio in prime_ladder.iter_prime_pairs():
        print(f"  [{index}] {p}/{q} = {ratio:.8f}")

    while True:
        raw_indices = prompt_str(
            "Comma-separated ladder indices to include", default="0,1,2"
        ).strip()
        try:
            indices = [int(piece.strip()) for piece in raw_indices.split(",") if piece.strip()]
        except ValueError:
            print("Invalid indices; please enter comma-separated integers.\n")
            continue
        if not indices:
            print("Please provide at least one index.\n")
            continue
        amounts: list[float] = []
        try:
            for idx in indices:
                amounts.append(prime_ladder.ladder_step_ratio(idx))
        except (IndexError, ValueError) as exc:
            print(f"Unable to compute ratios: {exc}\n")
            continue
        return amounts


def handle_prime_ladder() -> None:
    """Plan or send a prime ladder step using p_n / p_{n+1} ratios."""

    default_index = 3 if len(prime_ladder.PRIME_SEQUENCE) > 4 else 0
    while True:
        print(
            textwrap.dedent(
                """
                Prime ladder mode
                [1] Plan prime ladder step
                [2] Send prime ladder step
                [3] Prime burst (fan-out reflection)
                [B] Back
                """
            )
        )
        choice = input("Select an option: ").strip().lower()
        if choice in {"b", "0"}:
            return
        if choice not in {"1", "2", "3"}:
            print("Invalid selection, please try again.\n")
            continue

        if choice == "3":
            _run_prime_burst()
            continue

        to_address = prompt_str("Destination address")
        use_custom = input("Override prime pair? [y/N]: ").strip().lower().startswith("y")
        if use_custom:
            numerator = prompt_int("Numerator prime (p)")
            denominator = prompt_int("Denominator prime (q)")
            if numerator is None or denominator is None:
                print("Prime values are required when overriding the pair.\n")
                continue
            ratio = prime_ladder.prime_ratio(numerator, denominator)
        else:
            index = prompt_int(
                "Prime ladder index (0 = first pair in sequence)", default=default_index
            )
            if index is None:
                print("Prime ladder index is required.\n")
                continue
            try:
                ratio = prime_ladder.ladder_step_ratio(index)
                numerator = prime_ladder.PRIME_SEQUENCE[index]
                denominator = prime_ladder.PRIME_SEQUENCE[index + 1]
            except (IndexError, ValueError) as exc:
                print(f"Unable to compute ratio: {exc}\n")
                continue

        include_register = (
            input("Include balancing register output? [Y/n]: ").strip().lower()
            not in {"n", "no"}
        )
        balancing_amount = None
        if include_register:
            balancing_amount = prompt_float(
                "Balancing register amount (optional)", default=0.65082779
            )
        fee = prompt_float("Fee per transaction", default=0.21021)
        dry_run = input("Dry run? [Y/n]: ").strip().lower() not in {"n", "no"}
        single_tx = False
        mode_label = "MULTI-TX (frames)"
        if choice == "2":
            single_tx, mode_label = _prompt_send_mode()

        amounts = [ratio]
        if balancing_amount is not None:
            amounts.append(balancing_amount)
        amounts_csv = ",".join(_format_amount(value) for value in amounts)
        mode = "DRY RUN" if dry_run else "BROADCAST"
        plan_or_send = "plan-sequence" if choice == "1" else "send-sequence"

        print(
            textwrap.dedent(
                f"""
                Prime ladder step summary
                p/q: {numerator}/{denominator}
                ladder amount: {ratio:.8f}
                outputs: {amounts_csv}
                fee: {fee}
                mode: {mode}
                transaction mode: {mode_label}
                """
            )
        )
        if not _confirm():
            print("Cancelled.\n")
            continue

        args = [
            plan_or_send,
            "--to-address",
            to_address,
            "--amounts",
            amounts_csv,
            "--fee",
            str(fee if fee is not None else DEFAULT_FEE),
        ]
        if dry_run:
            args.append("--dry-run")
        if single_tx:
            args.append("--single-tx")

        print(f"Running command: enigmatic-dgb {' '.join(args)}")
        code = run_enigmatic_cli(args)
        print(f"Command finished with exit code {code}\n")
        _pause()


def _run_prime_burst() -> None:
    """Send a fan-out transaction containing multiple prime ladder ratios."""

    print("\nPrime burst / reflection\n" + "-" * 30)
    to_address = prompt_str("Destination address")
    amounts = _collect_prime_burst_amounts()
    extra_amounts_raw = prompt_str(
        "Additional custom amounts (optional, comma-separated)", default=""
    )
    if extra_amounts_raw.strip():
        try:
            extra_amounts = [
                float(piece.strip()) for piece in extra_amounts_raw.split(",") if piece.strip()
            ]
            amounts.extend(extra_amounts)
        except ValueError:
            print("Ignoring invalid custom amounts input; proceeding with ladder indices only.")

    fee = prompt_float("Fee for the fan-out transaction", default=0.21021)
    dry_run = input("Dry run? [Y/n]: ").strip().lower() not in {"n", "no"}
    amounts_csv = ",".join(_format_amount(value) for value in amounts)

    print(
        textwrap.dedent(
            f"""
            Prime burst summary
            outputs: {amounts_csv}
            fee: {fee}
            mode: {'DRY RUN' if dry_run else 'BROADCAST'}
            transaction mode: SINGLE-TX (fan-out)
            """
        )
    )
    if not _confirm():
        print("Cancelled.\n")
        return

    args = [
        "send-sequence",
        "--to-address",
        to_address,
        "--amounts",
        amounts_csv,
        "--fee",
        str(fee if fee is not None else DEFAULT_FEE),
        "--single-tx",
    ]
    if dry_run:
        args.append("--dry-run")

    print(f"Running command: enigmatic-dgb {' '.join(args)}")
    code = run_enigmatic_cli(args)
    print(f"Command finished with exit code {code}\n")
    _pause()


def handle_dtsp_messaging() -> None:
    """Encode DTSP text into a fee- or amount-plane sequence."""

    print(
        textwrap.dedent(
            """
            DTSP messaging helper
            This will encode plaintext into the DTSP alphabet and prepare a send plan.
            """
        )
    )

    to_address = prompt_str("Destination address")
    message = prompt_str("Plaintext message")
    include_handshake = input("Include START/END handshake? [Y/n]: ").strip().lower() not in {
        "n",
        "no",
    }
    encode_via_fee = input("Encode on fee plane? [Y/n]: ").strip().lower() not in {"n", "no"}
    base_amount = prompt_float(
        "Base amount per transaction (for fee-plane carrier or amount-plane)",
        default=0.0001,
    )
    carrier_fee = prompt_float("Fee per tx when using amount-plane", default=DEFAULT_FEE)
    dry_run = input("Dry run (no broadcast)? [Y/n]: ").strip().lower() not in {"n", "no"}

    sequence = encode_message_to_dtsp_sequence(message, include_start_end=include_handshake)
    preview = decode_dtsp_sequence_to_message(
        sequence, require_start_end=include_handshake if sequence else False
    )
    print("\nDTSP sequence prepared:")
    print("  values:", ",".join(f"{value:.8f}" for value in sequence))
    print(f"  decoded preview: {preview}")
    print(f"  frames: {len(sequence)}")
    mode_label = "plan" if dry_run else "broadcast"
    print(f"Mode: {mode_label} using {'fee' if encode_via_fee else 'amount'} plane")

    if not _confirm():
        print("Cancelled.")
        return

    if encode_via_fee:
        for index, value in enumerate(sequence, start=1):
            args = [
                "plan-sequence" if dry_run else "send-sequence",
                "--to-address",
                to_address,
                "--amounts",
                str(base_amount),
                "--fee",
                f"{value:.8f}",
            ]
            print(f"Running command for symbol #{index}: enigmatic-dgb {' '.join(args)}")
            run_enigmatic_cli(args)
    else:
        amounts_csv = ",".join(f"{value:.8f}" for value in sequence)
        args = [
            "plan-sequence" if dry_run else "send-sequence",
            "--to-address",
            to_address,
            "--amounts",
            amounts_csv,
            "--fee",
            str(carrier_fee if carrier_fee is not None else DEFAULT_FEE),
        ]
        print(f"Running command: enigmatic-dgb {' '.join(args)}")
        run_enigmatic_cli(args)

    _pause()


def handle_chains() -> None:
    """Plan or send chained patterns from dialect frames."""

    dialect_path = prompt_str("Dialect path", default=DEFAULT_DIALECT)
    symbol = prompt_str("Symbol name (optional)", default="")
    to_address = prompt_str("Destination address")
    max_frames = prompt_int("Max frames (optional)", default=None)
    min_conf = prompt_int("Min confirmations", default=None)
    min_conf_between = prompt_int("Min confirmations between steps", default=None)
    wait_between = prompt_float("Wait between txs (seconds)", default=None)
    max_wait = prompt_float("Max wait seconds", default=None)
    broadcast = input("Broadcast after planning? [y/N]: ").strip().lower().startswith("y")

    args = [
        "plan-chain",
        "--dialect-path",
        dialect_path,
        "--to-address",
        to_address,
    ]
    if symbol:
        args.extend(["--symbol", symbol])
    if max_frames is not None:
        args.extend(["--max-frames", str(max_frames)])
    if min_conf is not None:
        args.extend(["--min-confirmations", str(min_conf)])
    if min_conf_between is not None:
        args.extend(["--min-confirmations-between-steps", str(min_conf_between)])
    if wait_between is not None:
        args.extend(["--wait-between-txs", str(wait_between)])
    if max_wait is not None:
        args.extend(["--max-wait-seconds", str(max_wait)])
    args.append("--broadcast" if broadcast else "--dry-run")

    print(f"Running command: enigmatic-dgb {' '.join(args)}")
    code = run_enigmatic_cli(args)
    print(f"Command finished with exit code {code}\n")
    _pause()


def _decode_once(addresses: Sequence[str]) -> None:
    rpc = DigiByteRPC.from_env()
    config = EncodingConfig.enigmatic_default()
    watcher = Watcher(rpc, addresses=addresses, config=config)
    messages = watcher.poll_once()
    if not messages:
        print("No decoded packets observed in the recent window.")
        return
    for message in messages:
        print(f"Channel: {message.channel} | Intent: {message.intent} | Payload: {message.payload}")


def handle_decode_watch() -> None:
    """Decode ledger activity for one or more addresses."""

    addresses_raw = prompt_str("Addresses to watch (comma-separated)")
    start_height = prompt_int("Start height (optional)", default=None)
    end_height = prompt_int("End height (optional)", default=None)
    start_time = prompt_int("Start timestamp (epoch, optional)", default=None)
    end_time = prompt_int("End timestamp (epoch, optional)", default=None)

    mode = input("Mode: [D]ecode window or [L]ive watch? ").strip().lower()
    addresses = [piece.strip() for piece in addresses_raw.split(",") if piece.strip()]

    print(
        "Selected window: "
        f"heights {start_height or 'any'}-{end_height or 'any'}, "
        f"timestamps {start_time or 'any'}-{end_time or 'any'}"
    )

    if mode.startswith("l"):
        print("Starting live watch (Ctrl+C to stop)...")
        try:
            rpc = DigiByteRPC.from_env()
            config = EncodingConfig.enigmatic_default()
            watcher = Watcher(rpc, addresses=addresses, config=config)
            watcher.run_forever(
                lambda msg: print(
                    f"[{msg.timestamp.isoformat()}] {msg.channel} {msg.intent} -> {msg.payload}"
                )
            )
        except Exception as exc:
            if _should_debug():
                traceback.print_exc()
            print(f"Watcher error: {exc}")
        return

    try:
        _decode_once(addresses)
    except (RPCError, Exception) as exc:  # pragma: no cover - interactive path
        if _should_debug():
            traceback.print_exc()
        print(f"Decode failed: {exc}")
    _pause()


def _group_transactions_by_txid(observed: Sequence[ObservedTx]) -> dict[str, list[ObservedTx]]:
    grouped: dict[str, list[ObservedTx]] = {}
    for tx in observed:
        grouped.setdefault(tx.txid, []).append(tx)
    return grouped


def _dedupe_addresses(entries: Sequence[ObservedTx]) -> list[str]:
    return sorted({entry.address for entry in entries if entry.address})


def _is_close(value: float, target: float, tolerance: float = 1e-8) -> bool:
    return abs(value - target) <= tolerance


def _detect_prime_ladder_activity(
    observed: Sequence[ObservedTx], tolerance: float = 1e-8
) -> dict[str, list[dict]]:
    grouped = _group_transactions_by_txid(observed)
    ladder_steps: list[dict] = []
    register_folds: list[dict] = []
    handshakes: list[dict] = []
    fee_targets = (0.21, 0.21021)

    for txid, entries in grouped.items():
        fees = [entry.fee for entry in entries if entry.fee is not None]
        fee = fees[0] if fees else None
        addresses = _dedupe_addresses(entries)
        seen_pairs: set[tuple[int, int]] = set()

        for entry in entries:
            match = prime_ladder.match_prime_ratio(entry.amount, tolerance=tolerance)
            if match is None:
                continue
            _, numerator, denominator, ratio = match
            pair_key = (numerator, denominator)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            ladder_steps.append(
                {
                    "txid": txid,
                    "p": numerator,
                    "q": denominator,
                    "ratio": ratio,
                    "amount": entry.amount,
                    "timestamp": entry.timestamp,
                    "block_height": entry.block_height,
                    "addresses": addresses,
                    "fee": fee,
                }
            )

        unit_outputs = [entry for entry in entries if _is_close(entry.amount, 1.0, tolerance)]
        remainders = [entry.amount for entry in entries if not _is_close(entry.amount, 1.0, tolerance)]
        if unit_outputs and remainders:
            register_folds.append(
                {
                    "txid": txid,
                    "remainder": max(remainders),
                    "timestamp": entries[0].timestamp,
                    "block_height": entries[0].block_height,
                    "addresses": addresses,
                    "fee": fee,
                }
            )

        fee_matches = fee is not None and any(_is_close(fee, target, tolerance) for target in fee_targets)
        if unit_outputs and fee_matches:
            handshakes.append(
                {
                    "txid": txid,
                    "amount": unit_outputs[0].amount,
                    "timestamp": unit_outputs[0].timestamp,
                    "block_height": unit_outputs[0].block_height,
                    "addresses": addresses,
                    "fee": fee,
                }
            )

    return {
        "ladder_steps": ladder_steps,
        "register_folds": register_folds,
        "handshake_units": handshakes,
    }


def analyze_address_activity(
    addresses: Sequence[str],
    start_height: int | None,
    end_height: int | None,
    start_time: int | None = None,
    end_time: int | None = None,
    mode: str = "full",
) -> dict:
    """Lightweight analysis stub over observed address activity."""

    rpc = DigiByteRPC.from_env()
    watcher = Watcher(rpc, addresses=addresses, config=EncodingConfig.enigmatic_default())
    observed: List = []
    for addr in addresses:
        observed.extend(watcher._fetch_address_transactions(addr))  # noqa: SLF001

    if start_time is not None:
        observed = [tx for tx in observed if tx.timestamp.timestamp() >= start_time]
    if end_time is not None:
        observed = [tx for tx in observed if tx.timestamp.timestamp() <= end_time]
    if start_height is not None:
        observed = [
            tx
            for tx in observed
            if tx.block_height is None or tx.block_height >= start_height
        ]
    if end_height is not None:
        observed = [
            tx
            for tx in observed
            if tx.block_height is None or tx.block_height <= end_height
        ]

    observed.sort(key=lambda tx: tx.timestamp)
    binary_candidates: List[dict] = []
    for tx in observed:
        payload = tx.op_return_data or b""
        if not payload:
            continue
        printable = sum(1 for b in payload if 32 <= b <= 126)
        ratio = printable / len(payload) if payload else 0
        if ratio >= 0.6:
            preview = payload[:32].decode(errors="replace")
            binary_candidates.append(
                {
                    "txid": tx.txid,
                    "printable_ratio": ratio,
                    "preview": preview,
                    "bit_length": len(payload) * 8,
                    "byte_length": len(payload),
                }
            )

    dtsp_metrics: List[dict] = []
    for first, second in zip(observed, observed[1:]):
        dtsp_metrics.append(
            {
                "delta_time": (second.timestamp - first.timestamp).total_seconds(),
                "fee": second.fee,
                "amount": second.amount,
            }
        )

    span_seconds = 0
    if observed:
        span_seconds = (observed[-1].timestamp - observed[0].timestamp).total_seconds()

    dtsp_candidates = []
    for tx in observed:
        if tx.fee is None:
            continue
        symbol, error = closest_dtsp_symbol(tx.fee, DTSP_TOLERANCE)
        if symbol is None:
            continue
        dtsp_candidates.append(
            {
                "txid": tx.txid,
                "value": tx.fee,
                "symbol": symbol,
                "error": error,
                "timestamp": tx.timestamp,
                "block_height": tx.block_height,
            }
        )

    dtsp_decoding = _decode_dtsp_candidates(dtsp_candidates)
    prime_ladder_activity = (
        _detect_prime_ladder_activity(observed)
        if mode != "binary-only"
        else {"ladder_steps": [], "register_folds": [], "handshake_units": []}
    )

    return {
        "address_count": len(addresses),
        "tx_count": len(observed),
        "time_span_seconds": span_seconds,
        "mode": mode,
        "dtsp_metrics": dtsp_metrics,
        "dtsp_candidates": dtsp_candidates,
        "dtsp_decoding": dtsp_decoding,
        "binary_candidates": binary_candidates,
        "prime_ladder": prime_ladder_activity,
        "start_height": start_height,
        "end_height": end_height,
        "start_time": start_time,
        "end_time": end_time,
    }


def _decode_dtsp_candidates(candidates: List[dict]) -> dict:
    """Attempt to group and decode DTSP candidates into messages."""

    if not candidates:
        return {"raw_values": [], "decoded_messages": []}

    ordered = sorted(candidates, key=lambda entry: entry["timestamp"])
    segments: List[List[dict]] = [[ordered[0]]]
    for current in ordered[1:]:
        previous = segments[-1][-1]
        gap = (current["timestamp"] - previous["timestamp"]).total_seconds()
        if gap > DTSP_GAP_SECONDS or previous["symbol"] == "END" or current["symbol"] == "START":
            segments.append([current])
            continue
        segments[-1].append(current)

    decoded_messages: List[dict] = []
    for segment in segments:
        values = [entry["value"] for entry in segment]
        start_height = segment[0].get("block_height")
        end_height = segment[-1].get("block_height")
        start_time = segment[0]["timestamp"].isoformat()
        end_time = segment[-1]["timestamp"].isoformat()
        handshake_present = {entry["symbol"] for entry in segment} & set(DTSP_CONTROL)
        notes: str
        valid = False
        text = ""
        try:
            text = decode_dtsp_sequence_to_message(
                values, require_start_end=True, tolerance=DTSP_TOLERANCE
            )
            valid = True
            notes = "Decoded with handshake"
        except DTSPEncodingError as exc:
            try:
                text = decode_dtsp_sequence_to_message(
                    values, require_start_end=False, tolerance=DTSP_TOLERANCE
                )
                notes = f"Decoded without handshake: {exc}"
            except DTSPEncodingError as inner:
                notes = f"Failed to decode: {inner}"
        if handshake_present and "start" not in text.lower():
            notes += "; handshake markers observed"
        decoded_messages.append(
            {
                "start_height": start_height,
                "end_height": end_height,
                "start_time": start_time,
                "end_time": end_time,
                "values": values,
                "text": text,
                "valid": valid,
                "notes": notes,
            }
        )

    return {"raw_values": [entry["value"] for entry in ordered], "decoded_messages": decoded_messages}


def handle_address_analysis() -> None:
    """Run DTSP/binary-oriented address analysis."""

    addresses_raw = prompt_str("Enter one or more DigiByte addresses (comma-separated)")
    start_height = prompt_int("Enter start height (or leave blank)", default=None)
    end_height = prompt_int("Enter end height (or leave blank)", default=None)
    start_time = prompt_int("Enter start timestamp (epoch, optional)", default=None)
    end_time = prompt_int("Enter end timestamp (epoch, optional)", default=None)

    print(
        textwrap.dedent(
            """
            [1] Run full analysis
            [2] DTSP only
            [3] Binary scan only
            [B] Back
            """
        )
    )
    choice = input("Select mode: ").strip().lower()
    if choice in {"b", "0"}:
        return
    if choice not in {"1", "2", "3"}:
        print("Invalid selection.")
        return
    mode = "full" if choice == "1" else "dtsp-only" if choice == "2" else "binary-only"

    addresses = [piece.strip() for piece in addresses_raw.split(",") if piece.strip()]
    if not addresses:
        print("No addresses provided.")
        return

    print(
        "Running analysis... (height/time filters will be applied when block data is available)"
    )
    try:
        result = analyze_address_activity(
            addresses,
            start_height=start_height,
            end_height=end_height,
            start_time=start_time,
            end_time=end_time,
            mode=mode,
        )
    except Exception as exc:  # pragma: no cover - interactive path
        if _should_debug():
            traceback.print_exc()
        print(f"Analysis failed: {exc}")
        _pause()
        return

    print("\nAnalysis summary:")
    print(f"Addresses: {addresses}")
    print(f"Transactions inspected: {result.get('tx_count')}")
    print(f"Time span (seconds): {result.get('time_span_seconds')}")
    print(f"Mode: {result.get('mode')}")
    print("\nDTSP candidates:")
    candidates = result.get("dtsp_candidates", [])
    for cand in candidates:
        height = cand.get("block_height")
        height_desc = height if height is not None else "?"
        print(
            "  h={height} t={time} fee={fee:.8f} -> {symbol} (error {error:.2e})".format(
                height=height_desc,
                time=cand.get("timestamp"),
                fee=cand.get("value"),
                symbol=cand.get("symbol"),
                error=cand.get("error", 0.0),
            )
        )
    if not candidates:
        print("  (no DTSP-like fee values detected)")

    handshakes = [c for c in candidates if c.get("symbol") in DTSP_CONTROL]
    if handshakes:
        print("  Handshake markers detected:")
        for marker in handshakes:
            print(
                "    {symbol} at height {height} time {time}".format(
                    symbol=marker.get("symbol"),
                    height=marker.get("block_height"),
                    time=marker.get("timestamp"),
                )
            )

    print("\nDTSP decoded messages:")
    decoded_messages = result.get("dtsp_decoding", {}).get("decoded_messages", [])
    if not decoded_messages:
        print("  (no decodable DTSP messages)")
    for message in decoded_messages:
        print(
            "  text='{text}' valid={valid} notes={notes}".format(
                text=message.get("text"),
                valid=message.get("valid"),
                notes=message.get("notes"),
            )
        )
        print(
            "    values={values}".format(
                values=[f"{value:.8f}" for value in message.get("values", [])]
            )
        )
        print(
            "    blocks={start}->{end} time={start_time}->{end_time}".format(
                start=message.get("start_height"),
                end=message.get("end_height"),
                start_time=message.get("start_time"),
                end_time=message.get("end_time"),
            )
        )

    prime_ladder_results = result.get("prime_ladder", {})
    ladder_steps = prime_ladder_results.get("ladder_steps", [])
    register_folds = prime_ladder_results.get("register_folds", [])
    handshake_units = prime_ladder_results.get("handshake_units", [])

    print("\nPrime ladder detections:")
    if ladder_steps:
        print("  Ladder steps:")
        for step in ladder_steps:
            destinations = ",".join(step.get("addresses") or []) or "(address unknown)"
            print(
                "    {p}/{q} -> {ratio:.8f} at h={height} to {dest} fee={fee}".format(
                    p=step.get("p"),
                    q=step.get("q"),
                    ratio=step.get("ratio", 0.0),
                    height=step.get("block_height") or "?",
                    dest=destinations,
                    fee=step.get("fee"),
                )
            )
    else:
        print("  (no prime ladder steps detected)")

    if register_folds:
        print("  Register folds:")
        for fold in register_folds:
            destinations = ",".join(fold.get("addresses") or []) or "(address unknown)"
            print(
                "    1.0 -> remainder {remainder:.8f} at h={height} to {dest} fee={fee}".format(
                    remainder=fold.get("remainder", 0.0),
                    height=fold.get("block_height") or "?",
                    dest=destinations,
                    fee=fold.get("fee"),
                )
            )
    if handshake_units:
        print("  Handshake units:")
        for hs in handshake_units:
            destinations = ",".join(hs.get("addresses") or []) or "(address unknown)"
            print(
                "    1.0 at h={height} to {dest} fee={fee}".format(
                    height=hs.get("block_height") or "?",
                    dest=destinations,
                    fee=hs.get("fee"),
                )
            )

    print("\nBinary decoding candidates:")
    for candidate in result.get("binary_candidates", []):
        print(
            "  txid={txid} printable={ratio:.2f} preview='{preview}' bits={bits} bytes={bytes}".format(
                txid=candidate.get("txid"),
                ratio=candidate.get("printable_ratio", 0.0),
                preview=candidate.get("preview", ""),
                bits=candidate.get("bit_length", 0),
                bytes=candidate.get("byte_length", 0),
            )
        )
    if not result.get("binary_candidates"):
        print("  (no printable binary candidates)")

    _pause()


def handle_help() -> None:
    """Display pointers to documentation and environment requirements."""

    print(
        textwrap.dedent(
            """
            Enigmatic console help

            Enigmatic enables ledger-native signaling across value, fee, cardinality,
            and timing planes using dialect-driven patterns. Explore the following
            resources within this repository:
              * README.md
              * docs/TOOLING.md (if present)
              * specs/ (protocol specs)
              * examples/ (dialects and sample configs)
              * DigiByte Transaction Signaling Protocol (DTSP) helpers for fee-plane
                messaging with START/ACCEPT/END handshakes
              * Prime burst mode: send a reflection of prior prime ladder steps in a
                single transaction (fan-out) to avoid long ancestor chains

            RPC environment variables typically required:
              * DGB_RPC_USER
              * DGB_RPC_PASSWORD
              * DGB_RPC_HOST
              * DGB_RPC_PORT
            """
        )
    )
    _pause()


def _wizard_print_policy(rpc: DigiByteRPC) -> None:
    ok_mem, mempool = _safe_rpc_call(rpc.getmempoolinfo, friendly_name="getmempoolinfo")
    ok_net, netinfo = _safe_rpc_call(rpc.getnetworkinfo, friendly_name="getnetworkinfo")
    if not (ok_mem or ok_net):
        return
    mem_min = None
    inc_fee = None
    relay_fee = None
    if isinstance(mempool, dict):
        mem_min = mempool.get("mempoolminfee")
    if isinstance(netinfo, dict):
        inc_fee = netinfo.get("incrementalfee")
        relay_fee = netinfo.get("minrelaytxfee") or netinfo.get("relayfee")
    print(
        "policy: mempoolminfee=%s, incrementalfee=%s, minrelaytxfee=%s (DGB/kvB)"
        % (mem_min, inc_fee, relay_fee)
    )


def _get_block_height() -> int | None:
    """Fetch the current block height via RPC, returning None on error."""

    try:
        rpc = DigiByteRPC.from_env()
        return rpc.getblockcount()
    except (ConfigurationError, RPCError, Exception):  # pragma: no cover - RPC plumbing
        if _should_debug():
            traceback.print_exc()
        return None


def _prompt_multi_line(prompt: str) -> str:
    print(prompt)
    print("Enter content, then EOF (Ctrl-D) to finish:")
    lines: list[str] = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines)


def _prompt_back_exit() -> bool:
    return input("[B] Back | [S] Save plan & exit | Enter to continue: ").strip().lower().startswith("b")


def _render_menu() -> None:
    block_height = _get_block_height()

    block_line = (
        f"Current block height: {block_height}"
        if block_height is not None
        else "Block height: unavailable (RPC)"
    )

    print(
        "=" * 37
        + "\nEnigmatic Console (DigiByte Layer-0)\n"
        + "=" * 37
        + f"\n{block_line}\n"
        + textwrap.dedent(
            """

            [1] Quickstart: send a simple pattern
            [2] Dialect-driven symbols (plan/send)
            [3] Numeric sequences (plan/send)
            [4] DTSP messaging (encode/send)
            [5] Chained patterns (plan-chain)
            [6] Decode / watch ledger activity
            [7] Address analysis (DTSP + binary)
            [8] Prime ladder (ladder steps)
            [9] Taproot inscription wizard
            [H] Help / Docs pointers
            [Q] Quit
            --------
            """
        )
    )


def console_main() -> None:
    """Launch the interactive ASCII console."""

    while True:
        _render_menu()
        selection = input("Select an option: ").strip().lower()
        if selection in {"q", "quit"}:
            print("Goodbye!")
            return
        if selection == "1":
            handle_quickstart()
        elif selection == "2":
            handle_dialect_symbols()
        elif selection == "3":
            handle_numeric_sequences()
        elif selection == "4":
            handle_dtsp_messaging()
        elif selection == "5":
            handle_chains()
        elif selection == "6":
            handle_decode_watch()
        elif selection == "7":
            handle_address_analysis()
        elif selection == "8":
            handle_prime_ladder()
        elif selection == "9":
            handle_taproot_wizard()
        elif selection in {"h", "?"}:
            handle_help()
        else:
            print("Invalid selection, please try again.\n")


def handle_taproot_wizard() -> None:
    """Interactive Taproot inscription wizard inside the console."""

    print("\nTaproot Inscription Wizard\n" + "-" * 32)
    wallet_name = prompt_str("Which wallet name?", default=DEFAULT_TAPROOT_WALLET)

    # Environment checks
    try:
        rpc = DigiByteRPC.from_env()
    except (ConfigurationError, RPCTransportError) as exc:
        message = str(exc)
        if isinstance(exc, RPCTransportError) and exc.status_code == 401:
            print(
                "Unauthorized: set DGB_RPC_USER/DGB_RPC_PASSWORD or pass --rpc-user/--rpc-password"
            )
        print(message)
        _pause()
        return

    rpc.set_wallet(wallet_name)

    ok_info, info = _safe_rpc_call(rpc.getblockchaininfo, friendly_name="RPC connectivity (getblockchaininfo)")
    if not ok_info:
        _pause()
        return

    ok_wallet, wallet_info = _safe_rpc_call(rpc.getwalletinfo, friendly_name="getwalletinfo")
    if not ok_wallet:
        wallets = rpc.listwallets()
        print(f"Loaded wallets: {wallets}")
        if wallet_name not in wallets:
            choice = input(
                f"Wallet {wallet_name!r} not loaded. Load now with loadwallet? [y/N]: "
            ).strip().lower()
            if choice.startswith("y"):
                _safe_rpc_call(lambda: rpc.loadwallet(wallet_name), friendly_name="loadwallet")
                ok_wallet, wallet_info = _safe_rpc_call(
                    rpc.getwalletinfo, friendly_name="getwalletinfo"
                )
            else:
                _pause()
                return
    print("Wallet ready.")
    _wizard_print_policy(rpc)

    # Payload capture
    while True:
        print("Choose payload type: (1) Plain text (2) JSON (3) Hex (0x…)")
        choice = input("Selection [1]: ").strip().lower() or "1"
        payload_bytes: bytes
        if choice == "2":
            raw_json = _prompt_multi_line("Enter JSON payload (blank line to finish)")
            try:
                parsed = json.loads(raw_json)
                payload_bytes = json.dumps(parsed, separators=(",", ":")).encode("utf-8")
            except json.JSONDecodeError as exc:
                print(f"JSON parse error: {exc}")
                continue
            default_ct = "application/json"
        elif choice == "3":
            raw_hex = prompt_str("Hex payload (0x… or plain hex)")
            raw_hex = raw_hex[2:] if raw_hex.lower().startswith("0x") else raw_hex
            try:
                payload_bytes = bytes.fromhex(raw_hex)
            except ValueError:
                print("Invalid hex; try again")
                continue
            default_ct = "application/octet-stream"
        else:
            text = _prompt_multi_line("Enter plain text payload (multi-line supported)")
            payload_bytes = text.encode("utf-8")
            default_ct = "text/plain"

        content_type = prompt_str("Content-Type", default=default_ct)
        try:
            stats = compute_taproot_envelope_stats(payload_bytes, content_type)
        except ValueError as exc:
            print(f"Envelope error: {exc}")
            back = _prompt_back_exit()
            if back:
                return
            continue
        print(
            "Payload bytes=%s | envelope=%s | push=%s | leaf_script=%s"
            % (
                stats["payload_bytes"],
                stats["envelope_bytes"],
                stats["push_bytes"],
                stats["leaf_script_bytes"],
            )
        )
        if stats["push_bytes"] > 520:
            print("Taproot single element push exceeds 520 bytes; cannot proceed.")
            back = _prompt_back_exit()
            if back:
                return
            continue
        break

    # Fee selection
    print("Fee mode: (1) Automatic (2) Manual sats/vB")
    fee_choice = input("Selection [1]: ").strip().lower() or "1"
    user_rate = None
    if fee_choice == "2":
        raw = prompt_str("sats/vB", default="10500")
        try:
            user_rate = float(raw)
        except ValueError:
            print("Invalid fee rate; using automatic")
            user_rate = None

    min_floor_raw = prompt_str("Minimum fee rate floor (sats/vB)", default="10500")
    try:
        min_floor = float(min_floor_raw)
    except ValueError:
        min_floor = None

    prepared = prepare_inscription_transaction(
        rpc,
        payload_bytes,
        content_type,
        scheme="taproot",
        user_fee_rate_satvb=user_rate,
        min_fee_rate_satvb_floor=min_floor,
        broadcast=False,
    )

    est_fee = calculate_fee_sats(prepared.fee_selection.fee_rate_sat_vb, prepared.vsize)
    suggested_cap = suggest_max_fee_sats(est_fee)
    print(
        f"Estimated fee: ~{est_fee} sats (vsize={prepared.vsize} at {prepared.fee_selection.fee_rate_sat_vb:.0f} sat/vB)"
    )
    cap_input = prompt_str(
        f"Set max-fee-sats to {suggested_cap}?", default=str(suggested_cap)
    )
    try:
        max_fee = int(cap_input)
    except ValueError:
        max_fee = suggested_cap

    prepared = prepare_inscription_transaction(
        rpc,
        payload_bytes,
        content_type,
        scheme="taproot",
        user_fee_rate_satvb=user_rate,
        min_fee_rate_satvb_floor=min_floor,
        max_fee_sats=max_fee,
        broadcast=False,
    )

    print("Dry run (no broadcast). Summary:")
    summary = prepared.summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print("Signed hex (truncated):", prepared.raw_tx[:120] + "…")

    proceed = input("Proceed to broadcast? Type BROADCAST to confirm: ").strip()
    if proceed != "BROADCAST":
        print("Cancelled before broadcast.")
        _pause()
        return

    prepared = prepare_inscription_transaction(
        rpc,
        payload_bytes,
        content_type,
        scheme="taproot",
        user_fee_rate_satvb=user_rate,
        min_fee_rate_satvb_floor=min_floor,
        max_fee_sats=max_fee,
        broadcast=True,
    )

    txid = prepared.txid or "?"
    print(f"Broadcasted txid: {txid}")
    _safe_rpc_call(lambda: rpc.getmempoolentry(txid), friendly_name="getmempoolentry (post-broadcast)")
    _safe_rpc_call(lambda: rpc.gettransaction(txid), friendly_name="gettransaction (wallet)")

    replacements: list[str] = []
    confirmed_blockhash: str | None = None
    confirmed_height: int | None = None

    monitor = input("Monitor until confirmed? [y/N]: ").strip().lower().startswith("y")
    if monitor:
        threshold_seconds = prompt_int("Auto-bump after how many seconds?", default=120) or 120
        bump_rate_default = max(prepared.fee_selection.fee_rate_sat_vb, min_floor or 0) + 1000
        start = time.time()
        while True:
            ok_tx, tx_info = _safe_rpc_call(lambda: rpc.gettransaction(txid), friendly_name="gettransaction")
            if ok_tx and isinstance(tx_info, dict):
                confirmations = tx_info.get("confirmations") or 0
                if confirmations > 0:
                    confirmed_blockhash = tx_info.get("blockhash")
                    confirmed_height = tx_info.get("blockheight")
                    print(f"Confirmed in block {confirmed_blockhash} (height {confirmed_height})")
                    break
            if time.time() - start >= threshold_seconds:
                bump_choice = input("Unconfirmed. Bump fee now? [y/N]: ").strip().lower()
                if bump_choice.startswith("y"):
                    new_rate_raw = prompt_str("New fee rate (sats/vB)", default=str(int(bump_rate_default)))
                    try:
                        new_rate = float(new_rate_raw)
                    except ValueError:
                        new_rate = bump_rate_default
                    try:
                        bump_resp = rpc.bumpfee(
                            txid,
                            {"fee_rate": sat_vb_to_dgb_per_kvb(new_rate)},
                        )
                        new_txid = bump_resp.get("txid")
                        if new_txid:
                            replacements.append(new_txid)
                            txid = new_txid
                            start = time.time()
                            print(f"Bump successful. New txid: {txid}")
                            continue
                        print("bumpfee returned no txid; stopping monitor")
                        break
                    except Exception as exc:  # pragma: no cover - RPC path
                        print(f"bumpfee failed: {exc}")
                        break
                else:
                    print("Monitor stopped without bump.")
                    break
            time.sleep(10)

    receipt_path = Path("./receipts") / f"ordinal_{txid}.json"
    write_receipt(
        receipt_path,
        payload_bytes,
        content_type,
        {
            "wallet": wallet_name,
            "fee_rate_sat_vb": prepared.fee_selection.fee_rate_sat_vb,
            "max_fee_sats": max_fee,
            "txids": [prepared.txid] + replacements if prepared.txid else replacements,
            "final_txid": txid,
            "scheme": prepared.scheme,
            "blockhash": confirmed_blockhash,
            "blockheight": confirmed_height,
        },
    )
    print(f"Receipt saved to {receipt_path}")
    _pause()\n*** End Patch


if __name__ == "__main__":
    console_main()
