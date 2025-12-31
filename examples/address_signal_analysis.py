"""Address-level DigiByte DTSP + binary signaling analysis.

This module ingests DigiByte transaction history for one or more addresses,
projects the activity into multiple "state planes" (value, fee, cardinality,
timing), and performs lightweight discrete-time signal processing alongside
simple binary encoding scans.

It is intended to be side-effect free except for printing summaries and
optionally writing a CSV snapshot of the extracted features.
"""

from __future__ import annotations

import dataclasses
import logging
from collections import Counter
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from enigmatic_dgb.config import load_rpc_config
from enigmatic_dgb.rpc_client import DigiByteRPC

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User-tunable configuration
# ---------------------------------------------------------------------------

TARGET_ADDRESSES: list[str] = []
START_HEIGHT: int | None = None
END_HEIGHT: int | None = None
START_TIME: int | None = None  # Unix epoch seconds
END_TIME: int | None = None

MIN_VALUE_SATS: int = 0
MIN_FEE_SATS: int = 0
FEE_THRESHOLD_SATS: int = 2000000  # example: 0.02 DGB
PRINT_BINARY_PREVIEW_MAX_CHARS: int = 120


# ---------------------------------------------------------------------------
# Data models and helpers
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class TxRecord:
    """Lightweight transaction projection used for analysis."""

    txid: str
    block_height: int
    block_time: int
    tx_index: int
    total_input_value: int
    total_output_value: int
    fee_value: int
    input_count: int
    output_count: int
    output_details: list[tuple[int, str]]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _rpc_from_env() -> DigiByteRPC:
    """Instantiate an RPC client using standard environment variables."""

    return DigiByteRPC(load_rpc_config())


def _resolve_height_range(
    rpc: DigiByteRPC,
    start_height: int | None,
    end_height: int | None,
    start_time: int | None,
    end_time: int | None,
) -> tuple[int, int]:
    """Resolve an inclusive block height range, optionally using timestamps.

    When heights are missing but timestamps are present, a binary search over
    the chain is used to find the nearest block satisfying the constraint.
    """

    tip = rpc.getblockcount()

    def block_time(height: int) -> int:
        block_hash = rpc.getblockhash(height)
        block = rpc.getblock(block_hash, 1)
        return int(block["time"])

    def search_height(target_time: int, look_for_start: bool) -> int:
        low, high = 0, tip
        result = 0 if look_for_start else tip
        while low <= high:
            mid = (low + high) // 2
            mid_time = block_time(mid)
            if look_for_start:
                if mid_time >= target_time:
                    result = mid
                    high = mid - 1
                else:
                    low = mid + 1
            else:
                if mid_time <= target_time:
                    result = mid
                    low = mid + 1
                else:
                    high = mid - 1
        return result

    resolved_start = start_height
    resolved_end = end_height

    if resolved_start is None and start_time is not None:
        resolved_start = search_height(start_time, look_for_start=True)
    if resolved_end is None and end_time is not None:
        resolved_end = search_height(end_time, look_for_start=False)

    if resolved_start is None:
        resolved_start = 0
    if resolved_end is None:
        resolved_end = tip

    if resolved_start > resolved_end:
        raise ValueError("start_height must be <= end_height")

    return resolved_start, resolved_end


def _extract_output_details(tx: dict, target_addresses: set[str]) -> tuple[list[tuple[int, str]], int, bool]:
    """Return output detail list, total output value, and whether target hit."""

    outputs: list[tuple[int, str]] = []
    total_out = 0
    touched = False
    for vout in tx.get("vout", []):
        value_sats = int(round(vout.get("value", 0) * 1e8))
        if value_sats < MIN_VALUE_SATS:
            continue
        script = vout.get("scriptPubKey", {})
        addresses = script.get("addresses") or []
        for addr in addresses:
            outputs.append((value_sats, addr))
            if addr in target_addresses:
                touched = True
        total_out += value_sats
    return outputs, total_out, touched


def _extract_input_totals(
    rpc: DigiByteRPC,
    tx: dict,
    target_addresses: set[str],
    tx_cache: dict[str, dict],
) -> tuple[int, bool]:
    """Compute total input value and whether a target address appears in vin."""

    total_in = 0
    touched = False
    for vin in tx.get("vin", []):
        if "coinbase" in vin:
            continue
        prev_txid = vin.get("txid")
        vout_index = vin.get("vout")
        if prev_txid is None or vout_index is None:
            continue

        if prev_txid not in tx_cache:
            tx_cache[prev_txid] = rpc.getrawtransaction(prev_txid, True)
        prev_tx = tx_cache[prev_txid]
        prev_vout = prev_tx.get("vout", [])[vout_index]
        value_sats = int(round(prev_vout.get("value", 0) * 1e8))
        if value_sats >= MIN_VALUE_SATS:
            total_in += value_sats
        addresses = prev_vout.get("scriptPubKey", {}).get("addresses") or []
        if not touched and any(addr in target_addresses for addr in addresses):
            touched = True
    return total_in, touched


def load_transactions_for_addresses(
    addresses: list[str],
    start_height: int | None,
    end_height: int | None,
    start_time: int | None,
    end_time: int | None,
) -> list[dict]:
    """Collect transactions touching ``addresses`` in the specified window."""

    if not addresses:
        raise ValueError("At least one target address must be provided")

    rpc = _rpc_from_env()
    addr_set = set(addresses)
    start_h, end_h = _resolve_height_range(rpc, start_height, end_height, start_time, end_time)
    logger.info("Scanning heights %s-%s for addresses %s", start_h, end_h, addresses)

    tx_cache: dict[str, dict] = {}
    records: list[TxRecord] = []

    for height in range(start_h, end_h + 1):
        block_hash = rpc.getblockhash(height)
        block = rpc.getblock(block_hash, 2)
        block_time = int(block.get("time", 0))
        if start_time is not None and block_time < start_time:
            continue
        if end_time is not None and block_time > end_time:
            continue

        for tx_index, tx in enumerate(block.get("tx", [])):
            outputs, total_out, output_hit = _extract_output_details(tx, addr_set)
            total_in, input_hit = _extract_input_totals(rpc, tx, addr_set, tx_cache)

            touched = output_hit or input_hit
            if not touched:
                continue

            fee = max(total_in - total_out, 0)
            if fee < MIN_FEE_SATS:
                fee = 0

            record = TxRecord(
                txid=tx.get("txid", ""),
                block_height=height,
                block_time=block_time,
                tx_index=tx_index,
                total_input_value=total_in,
                total_output_value=total_out,
                fee_value=fee,
                input_count=len([vin for vin in tx.get("vin", []) if "coinbase" not in vin]),
                output_count=len(outputs),
                output_details=outputs,
            )
            records.append(record)

    return [r.to_dict() for r in records]


def project_to_state_planes(tx_records: list[dict]) -> pd.DataFrame:
    """Project raw transaction records into analysis-friendly DataFrame."""

    if not tx_records:
        return pd.DataFrame()

    df = pd.DataFrame(tx_records)
    df = df.sort_values(["block_height", "tx_index"]).reset_index(drop=True)
    df["delta_height"] = df["block_height"].diff().fillna(0).astype(int)
    df["delta_time"] = df["block_time"].diff().fillna(0).astype(int)
    df["value_net"] = df["total_output_value"] - df["total_input_value"]
    df = df.rename(columns={
        "total_input_value": "value_total_in",
        "total_output_value": "value_total_out",
        "fee_value": "fee",
    })
    return df


def _autocorrelation_peak(series: np.ndarray) -> int | None:
    if len(series) < 3:
        return None
    centered = series - series.mean()
    corr = np.correlate(centered, centered, mode="full")
    half = corr[corr.size // 2 :]
    if len(half) < 2:
        return None
    peak_index = int(np.argmax(half[1:]) + 1)
    return peak_index


def analyze_periodicity(series: pd.Series, label: str) -> dict:
    """Return summary stats and lightweight periodicity hints for a series."""

    clean = series.dropna().to_numpy()
    if clean.size == 0:
        return {"label": label, "empty": True}

    stats = {
        "label": label,
        "empty": False,
        "mean": float(np.mean(clean)),
        "std": float(np.std(clean)),
        "min": float(np.min(clean)),
        "max": float(np.max(clean)),
    }

    peak_lag = _autocorrelation_peak(clean)
    stats["dominant_lag"] = peak_lag

    centered = clean - np.mean(clean)
    spectrum = np.fft.rfft(centered)
    magnitudes = np.abs(spectrum)
    if magnitudes.size > 1:
        dominant_index = int(np.argmax(magnitudes[1:]) + 1)
        stats["dominant_freq_index"] = dominant_index
        stats["dominant_freq_magnitude"] = float(magnitudes[dominant_index])
    else:
        stats["dominant_freq_index"] = None
        stats["dominant_freq_magnitude"] = 0.0

    stats["periodic"] = peak_lag is not None and peak_lag > 0 and magnitudes.size > 1
    return stats


def scan_dtsp_patterns(df: pd.DataFrame) -> dict:
    """Run DTSP heuristics across select channels."""

    if df.empty:
        return {}

    channels = ["delta_height", "delta_time", "fee", "input_count", "output_count"]
    results = {}
    for channel in channels:
        if channel in df.columns:
            results[channel] = analyze_periodicity(df[channel], channel)

    # Motif detection via simple run-length encoding on fee buckets
    fee_buckets = (df.get("fee", pd.Series(dtype=int)) // max(FEE_THRESHOLD_SATS, 1)).astype(int)
    runs: list[tuple[int, int]] = []
    last_val = None
    run_len = 0
    for val in fee_buckets:
        if val == last_val:
            run_len += 1
        else:
            if last_val is not None:
                runs.append((last_val, run_len))
            last_val = val
            run_len = 1
    if last_val is not None:
        runs.append((last_val, run_len))
    run_counts = Counter(run_len for _, run_len in runs)
    results["fee_run_lengths"] = dict(run_counts)
    return results


def build_bitstream(df: pd.DataFrame, mapping_fn: Callable[[pd.Series], int]) -> list[int]:
    """Apply mapping_fn row-wise to build a bitstream."""

    bits: list[int] = []
    for _, row in df.iterrows():
        try:
            bits.append(int(mapping_fn(row)))
        except Exception:  # pragma: no cover - defensive against mapping errors
            continue
    return bits


def bits_to_bytes(bitstream: Iterable[int], msb_first: bool = True) -> bytes:
    """Pack a bitstream into bytes, dropping any incomplete trailing chunk."""

    bits = list(bitstream)
    byte_values: list[int] = []
    for i in range(0, len(bits) - len(bits) % 8, 8):
        chunk = bits[i : i + 8]
        value = 0
        for idx, bit in enumerate(chunk):
            if msb_first:
                value |= (bit & 1) << (7 - idx)
            else:
                value |= (bit & 1) << idx
        byte_values.append(value)
    return bytes(byte_values)


def try_decode_ascii(byte_data: bytes) -> tuple[str | None, float]:
    """Attempt ASCII decoding and return (text, printable_ratio)."""

    if not byte_data:
        return None, 0.0
    printable = sum(32 <= b <= 126 or b in {9, 10, 13} for b in byte_data)
    ratio = printable / len(byte_data)
    if ratio < 0.8:
        return None, ratio
    try:
        return byte_data.decode("utf-8", errors="ignore"), ratio
    except Exception:
        return None, ratio


def scan_binary_encodings(df: pd.DataFrame) -> list[dict]:
    """Try simple bit mappings and report candidate decodes."""

    if df.empty:
        return []

    mappings: list[tuple[str, Callable[[pd.Series], int]]] = [
        ("value_out_parity", lambda row: int(row["value_total_out"] % 2)),
        (
            f"fee_threshold_{FEE_THRESHOLD_SATS}",
            lambda row: 1 if row.get("fee", 0) >= FEE_THRESHOLD_SATS else 0,
        ),
        ("input_parity", lambda row: int(row.get("input_count", 0) % 2)),
        ("output_parity", lambda row: int(row.get("output_count", 0) % 2)),
    ]

    findings: list[dict] = []
    for name, fn in mappings:
        bitstream = build_bitstream(df, fn)
        if not bitstream:
            continue
        for msb_first in (True, False):
            byte_data = bits_to_bytes(bitstream, msb_first=msb_first)
            decoded, ratio = try_decode_ascii(byte_data)
            if decoded:
                preview = decoded[:PRINT_BINARY_PREVIEW_MAX_CHARS]
                findings.append(
                    {
                        "mapping": name,
                        "bit_order": "msb_first" if msb_first else "lsb_first",
                        "decoded_preview": preview,
                        "printable_ratio": ratio,
                        "length_bits": len(bitstream),
                        "length_bytes": len(byte_data),
                    }
                )
    return findings


def analyze_address_activity(
    addresses: list[str],
    start_height: int | None,
    end_height: int | None,
    start_time: int | None = None,
    end_time: int | None = None,
) -> None:
    """Top-level orchestration to run analysis and print summaries."""

    tx_records = load_transactions_for_addresses(addresses, start_height, end_height, start_time, end_time)
    if not tx_records:
        print("No transactions found for the given parameters.")
        return

    df = project_to_state_planes(tx_records)
    print(
        f"Analyzing {len(df)} transactions for addresses: {addresses}\n"
        f"Blocks: {df['block_height'].min()} -> {df['block_height'].max()} (span {df['delta_height'].sum()})\n"
        f"Time:   {df['block_time'].min()} -> {df['block_time'].max()} (span {df['delta_time'].sum()} seconds)"
    )

    dtsp_results = scan_dtsp_patterns(df)
    print("\n[DTSP channels]")
    for label, result in dtsp_results.items():
        if isinstance(result, dict) and result.get("empty"):
            print(f"  [{label}] empty")
            continue
        if isinstance(result, dict):
            print(f"  [{label}]")
            for key, value in result.items():
                if key == "label":
                    continue
                print(f"    {key}: {value}")
        else:
            print(f"  [{label}] {result}")

    binary_findings = scan_binary_encodings(df)
    print("\n[Binary candidates]")
    if not binary_findings:
        print("  none")
    for finding in binary_findings:
        print(
            f"  Mapping: {finding['mapping']}, bit_order={finding['bit_order']}\n"
            f"    printable_ratio={finding['printable_ratio']:.2f}, "
            f"length_bits={finding['length_bits']}, length_bytes={finding['length_bytes']}\n"
            f"    preview=\"{finding['decoded_preview']}\""
        )

    first_addr = addresses[0].replace(" ", "_")
    csv_name = f"enigmatic_analysis_{first_addr}_{start_height or start_time}_{end_height or end_time}.csv"
    df.to_csv(csv_name, index=False)
    print(f"\nSaved features to {csv_name}")


if __name__ == "__main__":
    analyze_address_activity(
        addresses=TARGET_ADDRESSES,
        start_height=START_HEIGHT,
        end_height=END_HEIGHT,
        start_time=START_TIME,
        end_time=END_TIME,
    )
