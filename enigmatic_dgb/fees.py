"""Fee selection and conversion helpers for DigiByte transactions."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

logger = logging.getLogger(__name__)

DEFAULT_CONF_TARGET = 6
DEFAULT_ESTIMATE_MODE = "conservative"
DEFAULT_FALLBACK_FEE_RATE_SATVB = 10000.0
ENV_MIN_FEE_RATE_FLOOR = "ENIGMATIC_MIN_FEE_RATE_SATVB"
ENV_FALLBACK_FEE_RATE = "ENIGMATIC_FALLBACK_FEE_RATE_SATVB"


def dgb_per_kvb_to_sat_vb(rate: float | int) -> float:
    """Convert a DGB/kvB fee rate to sat/vB."""

    return float(rate) * 1e8 / 1000


def sat_vb_to_dgb_per_kvb(rate: float | int) -> float:
    """Convert a sat/vB fee rate to DGB/kvB."""

    return float(rate) / 1e5


def calculate_fee_sats(fee_rate_sat_vb: float, vsize: int) -> int:
    """Return the ceil'd fee in satoshis for the provided vsize."""

    return int(math.ceil(fee_rate_sat_vb * vsize))


@dataclass
class FeeSelectionResult:
    """Container for fee-rate decisions."""

    fee_rate_sat_vb: float
    source: str
    floors_applied: list[Tuple[str, float]]
    fee_sats: int | None = None
    vsize: int | None = None

    def with_vsize(self, vsize: int) -> "FeeSelectionResult":
        fee_sats = calculate_fee_sats(self.fee_rate_sat_vb, vsize)
        return FeeSelectionResult(
            fee_rate_sat_vb=self.fee_rate_sat_vb,
            source=self.source,
            floors_applied=self.floors_applied,
            fee_sats=fee_sats,
            vsize=vsize,
        )


def _extract_estimate_rate(estimate_resp: Dict[str, Any]) -> Tuple[float | None, str | None]:
    """Return a sat/vB fee rate from an estimatesmartfee-style response."""

    if not estimate_resp:
        return None, None

    rate_val = estimate_resp.get("feerate") or estimate_resp.get("feeRate")
    if rate_val is None:
        return None, None

    try:
        parsed = float(rate_val)
    except (TypeError, ValueError):
        return None, None

    # Heuristic: DGB/kvB responses should always be well below 1.0.
    if parsed < 1.0:
        return dgb_per_kvb_to_sat_vb(parsed), "dgb/kvb"
    return parsed, "sat/vb"


def _policy_floor_from_rpc(rpc_client: Any) -> Tuple[float | None, list[Tuple[str, float]]]:
    """Return policy fee floors (sat/vB) derived from node state."""

    floors: list[Tuple[str, float]] = []

    try:
        mempool = rpc_client.getmempoolinfo()
    except Exception:  # pragma: no cover - defensive: RPC optional
        mempool = None
    if isinstance(mempool, dict):
        mempool_min = mempool.get("mempoolminfee")
        if mempool_min is not None:
            try:
                rate = dgb_per_kvb_to_sat_vb(float(mempool_min))
                floors.append(("mempoolminfee", rate))
            except (TypeError, ValueError):
                logger.debug("Unable to parse mempoolminfee: %s", mempool_min)

    try:
        network_info = rpc_client.getnetworkinfo()
    except Exception:  # pragma: no cover - defensive: RPC optional
        network_info = None
    if isinstance(network_info, dict):
        for key in ("incrementalfee", "relayfee", "minrelaytxfee"):
            value = network_info.get(key)
            if value is None:
                continue
            try:
                rate = dgb_per_kvb_to_sat_vb(float(value))
            except (TypeError, ValueError):
                logger.debug("Unable to parse %s: %s", key, value)
                continue
            floors.append((key, rate))

    if not floors:
        return None, []

    max_floor = max(rate for _, rate in floors)
    return max_floor, floors


def _env_override(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float in %s=%s; ignoring", name, raw)
        return None


def select_fee_rate(
    rpc_client: Any,
    *,
    conf_target: int | None = None,
    estimate_mode: str | None = None,
    user_fee_rate_satvb: float | None = None,
    min_fee_rate_satvb_floor: float | None = None,
    max_fee_sats: int | None = None,
    tx_vsize_estimate: int | None = None,
    fallback_fee_rate_satvb: float | None = None,
) -> FeeSelectionResult:
    """Select a sane fee rate with node-aware floors and optional caps."""

    env_floor = _env_override(ENV_MIN_FEE_RATE_FLOOR)
    floor_candidates: list[Tuple[str, float]] = []
    for label, raw in (
        ("env", env_floor),
        ("cli_floor", min_fee_rate_satvb_floor),
    ):
        if raw is not None:
            floor_candidates.append((label, float(raw)))

    policy_floor, policy_components = _policy_floor_from_rpc(rpc_client)
    floor_candidates.extend(policy_components)
    if policy_floor is not None:
        floor_candidates.append(("policy_floor", policy_floor))

    floors_applied: list[Tuple[str, float]] = []
    floor_value = None
    if floor_candidates:
        floor_value = max(rate for _, rate in floor_candidates)
        floors_applied = [(label, rate) for label, rate in floor_candidates if rate == floor_value]

    fee_rate = None
    source = "unknown"

    if user_fee_rate_satvb is not None:
        fee_rate = float(user_fee_rate_satvb)
        source = "user"
    else:
        est_rate = None
        est_unit = None
        try:
            est_resp = rpc_client.estimatesmartfee(
                conf_target or DEFAULT_CONF_TARGET,
                estimate_mode or DEFAULT_ESTIMATE_MODE,
            )
            est_rate, est_unit = _extract_estimate_rate(est_resp or {})
        except Exception as exc:  # pragma: no cover - RPC errors vary
            logger.info("estimatesmartfee unavailable: %s", exc)

        if est_rate is not None:
            fee_rate = est_rate
            source = f"estimatesmartfee[{est_unit or 'unknown'}]"

    if fee_rate is None:
        fallback = (
            user_fee_rate_satvb
            or min_fee_rate_satvb_floor
            or _env_override(ENV_FALLBACK_FEE_RATE)
            or fallback_fee_rate_satvb
            or DEFAULT_FALLBACK_FEE_RATE_SATVB
        )
        fee_rate = float(fallback)
        source = "fallback"

    if floor_value is not None and fee_rate < floor_value:
        logger.debug(
            "Applying fee floor %.2f sat/vB over %s", floor_value, fee_rate
        )
        fee_rate = floor_value

    selection = FeeSelectionResult(
        fee_rate_sat_vb=fee_rate,
        source=source,
        floors_applied=floors_applied,
    )

    if tx_vsize_estimate:
        selection = selection.with_vsize(tx_vsize_estimate)

    if max_fee_sats is not None and selection.fee_sats is not None:
        if selection.fee_sats > max_fee_sats:
            raise ValueError(
                f"Computed fee {selection.fee_sats} sats exceeds max-fee-sats {max_fee_sats}"
            )

    return selection


def format_floors_for_log(floors: Iterable[Tuple[str, float]]) -> str:
    """Format fee floors for user-facing logs."""

    entries = [f"{label}={rate:.2f} sat/vB" for label, rate in floors]
    return ", ".join(entries) if entries else "none"
