from __future__ import annotations

import math
import pytest

from enigmatic_dgb.fees import (
    DEFAULT_CONF_TARGET,
    calculate_fee_sats,
    select_fee_rate,
)


class StubRPC:
    def __init__(self, estimate_rate: float | None = None, mempool_min: float | None = None) -> None:
        self.estimate_rate = estimate_rate
        self.mempool_min = mempool_min

    def estimatesmartfee(self, conf_target, mode=None):
        if self.estimate_rate is None:
            return {}
        return {"feerate": self.estimate_rate}

    def getmempoolinfo(self):
        if self.mempool_min is None:
            return {}
        return {"mempoolminfee": self.mempool_min}

    def getnetworkinfo(self):
        return {}


def test_explicit_fee_rate_wins() -> None:
    rpc = StubRPC(estimate_rate=0.0001)
    selection = select_fee_rate(rpc, user_fee_rate_satvb=2500)
    assert selection.fee_rate_sat_vb == 2500
    assert selection.source == "user"


def test_estimate_applies_floor() -> None:
    rpc = StubRPC(estimate_rate=0.00002, mempool_min=0.0001)  # 2 vs 10 sat/vB
    selection = select_fee_rate(rpc, conf_target=DEFAULT_CONF_TARGET)
    assert math.isclose(selection.fee_rate_sat_vb, 10.0)
    assert selection.floors_applied


def test_fee_with_vsize() -> None:
    rpc = StubRPC()
    selection = select_fee_rate(rpc, user_fee_rate_satvb=10500, tx_vsize_estimate=154)
    assert selection.fee_sats == 10500 * 154
    assert selection.vsize == 154


def test_max_fee_cap_raises() -> None:
    rpc = StubRPC()
    with pytest.raises(ValueError):
        select_fee_rate(
            rpc,
            user_fee_rate_satvb=1000,
            tx_vsize_estimate=300,
            max_fee_sats=200000,
        )


def test_calculate_fee_sats_rounds_up() -> None:
    assert calculate_fee_sats(100.5, 3) == 302
