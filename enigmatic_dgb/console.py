"""Interactive ASCII console for Enigmatic DigiByte tooling."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
import traceback
from typing import List, Sequence

from . import cli
from .dialect import DialectError, load_dialect
from .model import EncodingConfig
from .rpc_client import DigiByteRPC, RPCError
from .watcher import Watcher

DEFAULT_FEE = 0.21
DEFAULT_DIALECT = "examples/dialect-showcase.yaml"


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


def _should_debug() -> bool:
    return bool(int(os.environ.get("ENIGMATIC_DEBUG", "0")))


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

        print(f"Running command: enigmatic-dgb {' '.join(args)}")
        code = run_enigmatic_cli(args)
        print(f"Command finished with exit code {code}\n")
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

    return {
        "address_count": len(addresses),
        "tx_count": len(observed),
        "time_span_seconds": span_seconds,
        "mode": mode,
        "dtsp_metrics": dtsp_metrics,
        "binary_candidates": binary_candidates,
        "start_height": start_height,
        "end_height": end_height,
        "start_time": start_time,
        "end_time": end_time,
    }


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

    print("Running analysis... (defaults to most recent 1000 transactions per address)")
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
    print("\nDTSP deltas (time/fee/amount):")
    for entry in result.get("dtsp_metrics", []):
        print(f"  Δt={entry['delta_time']}s fee={entry['fee']} amount={entry['amount']}")
    if not result.get("dtsp_metrics"):
        print("  (no DTSP metrics available)")

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

            RPC environment variables typically required:
              * DGB_RPC_USER
              * DGB_RPC_PASSWORD
              * DGB_RPC_HOST
              * DGB_RPC_PORT
            """
        )
    )
    _pause()


def _render_menu() -> None:
    print(
        "=" * 37
        + "\nEnigmatic Console (DigiByte Layer-0)\n"
        + "=" * 37
        + textwrap.dedent(
            """

            [1] Quickstart: send a simple pattern
            [2] Dialect-driven symbols (plan/send)
            [3] Numeric sequences (plan/send)
            [4] Chained patterns (plan-chain)
            [5] Decode / watch ledger activity
            [6] Address analysis (DTSP + binary)
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
            handle_chains()
        elif selection == "5":
            handle_decode_watch()
        elif selection == "6":
            handle_address_analysis()
        elif selection in {"h", "?"}:
            handle_help()
        else:
            print("Invalid selection, please try again.\n")


if __name__ == "__main__":
    console_main()
