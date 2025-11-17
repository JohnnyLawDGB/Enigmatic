from __future__ import annotations

from decimal import Decimal

import pytest

from enigmatic_dgb.planner import (
    AutomationDialect,
    AutomationMetadata,
    AutomationSymbol,
    PatternPlan,
    PlanningError,
    SymbolPlan,
    SymbolPlanner,
    broadcast_pattern_plan,
    plan_explicit_pattern,
)


class DummyRPC:
    def __init__(self) -> None:
        self._change_index = 0
        self.last_tx = None

    def getblockcount(self) -> int:
        return 100

    def listunspent(self, minconf: int) -> list[dict[str, object]]:
        return [
            {"txid": "a", "vout": 0, "amount": "4.0", "spendable": True},
            {"txid": "b", "vout": 1, "amount": "3.0", "spendable": True},
            {"txid": "c", "vout": 2, "amount": "2.0", "spendable": True},
        ]

    def getnewaddress(self) -> str:
        return "dgb1receiver"

    def getrawchangeaddress(self) -> str:
        addr = f"dgb1change{self._change_index}"
        self._change_index += 1
        return addr

    def createrawtransaction(self, inputs, outputs):
        self.last_tx = (inputs, outputs)
        return "rawtx"

    def signrawtransactionwithwallet(self, raw_hex):
        assert raw_hex == "rawtx"
        return {"hex": "signed", "complete": True}

    def sendrawtransaction(self, signed_hex):
        assert signed_hex == "signed"
        return "broadcast-txid"


@pytest.fixture()
def automation() -> AutomationMetadata:
    return AutomationMetadata(
        endpoint="http://127.0.0.1:14022",
        wallet="enigmatic",
        min_confirmations=1,
        max_drift_blocks=1,
        rebroadcast_misses=2,
    )


@pytest.fixture()
def symbol() -> AutomationSymbol:
    return AutomationSymbol(
        name="HEARTBEAT",
        value=Decimal("5.0"),
        fee=Decimal("0.5"),
        inputs=2,
        outputs=3,
        delta=3,
        sigma=1,
    )


def test_symbol_planner_plan_distribution(automation: AutomationMetadata, symbol: AutomationSymbol) -> None:
    rpc = DummyRPC()
    planner = SymbolPlanner(rpc, automation)
    plan = planner.plan(symbol)
    assert isinstance(plan, SymbolPlan)
    assert len(plan.inputs) == symbol.inputs
    assert len(plan.outputs) == symbol.outputs
    receiver_amount = plan.outputs["dgb1receiver"]
    assert receiver_amount >= symbol.value
    assert plan.block_target == 103


def test_symbol_planner_broadcast(automation: AutomationMetadata, symbol: AutomationSymbol) -> None:
    rpc = DummyRPC()
    planner = SymbolPlanner(rpc, automation)
    plan = planner.plan(symbol)
    txid = planner.broadcast(plan)
    assert txid == "broadcast-txid"
    inputs, outputs = rpc.last_tx
    assert len(inputs) == symbol.inputs
    assert len(outputs) == symbol.outputs


def test_symbol_planner_requires_change_for_cardinality(automation: AutomationMetadata) -> None:
    rpc = DummyRPC()
    tight_symbol = AutomationSymbol(
        name="TIGHT",
        value=Decimal("8.5"),
        fee=Decimal("0.5"),
        inputs=3,
        outputs=2,
        delta=0,
        sigma=0,
    )
    planner = SymbolPlanner(rpc, automation)
    with pytest.raises(PlanningError):
        planner.plan(tight_symbol)


def test_load_automation_dialect(tmp_path) -> None:
    content = """
name: Test Dialect
version: 1.0
symbols:
  - name: TEST
    match:
      value: 1.5
      fee: 0.1
      m: 1
      n: 1
automation:
  rpc:
    endpoint: http://127.0.0.1:14022
"""
    path = tmp_path / "dialect.yaml"
    path.write_text(content)
    dialect = AutomationDialect.load(path)
    assert dialect.get_symbol("TEST").value == Decimal("1.5")


def test_load_missing_symbol_section(tmp_path) -> None:
    path = tmp_path / "dialect.yaml"
    path.write_text("symbols: []")
    with pytest.raises(PlanningError):
        AutomationDialect.load(path)


def test_plan_explicit_pattern_builds_outputs() -> None:
    rpc = DummyRPC()
    plan = plan_explicit_pattern(
        rpc,
        to_address="dgb1target",
        amounts=[Decimal("1.0"), Decimal("2.0"), Decimal("3.0")],
        fee=Decimal("0.1"),
    )
    assert isinstance(plan, PatternPlan)
    assert len(plan.outputs) == 3
    assert plan.outputs[0].amount == Decimal("1.00000000")
    assert plan.change_output is not None


def test_broadcast_pattern_plan_uses_same_stack() -> None:
    rpc = DummyRPC()
    plan = plan_explicit_pattern(
        rpc,
        to_address="dgb1target",
        amounts=[Decimal("1.0")],
        fee=Decimal("0.1"),
    )
    txid = broadcast_pattern_plan(rpc, plan)
    assert txid == "broadcast-txid"
    inputs, outputs = rpc.last_tx
    assert len(inputs) == len(plan.inputs)
    assert len(outputs) >= len(plan.outputs)
