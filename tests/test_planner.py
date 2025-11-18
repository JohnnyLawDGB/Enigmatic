from __future__ import annotations

from decimal import Decimal

import pytest

from enigmatic_dgb.planner import (
    AutomationDialect,
    AutomationFrame,
    AutomationMetadata,
    AutomationSymbol,
    PatternPlan,
    PatternPlanSequence,
    PREVIOUS_CHANGE_SENTINEL,
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
        self.tx_history: list[tuple[list, list]] = []
        self._tx_index = 0
        self.sent_txids: list[str] = []

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
        self.tx_history.append((inputs, outputs))
        return "rawtx"

    def signrawtransactionwithwallet(self, raw_hex):
        assert raw_hex == "rawtx"
        return {"hex": "signed", "complete": True}

    def sendrawtransaction(self, signed_hex):
        assert signed_hex == "signed"
        txid = f"broadcast-txid-{self._tx_index}"
        self._tx_index += 1
        self.sent_txids.append(txid)
        return txid


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
    assert txid == "broadcast-txid-0"
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
    assert isinstance(plan, PatternPlanSequence)
    assert len(plan.steps) == 3
    first = plan.steps[0]
    assert first.outputs[0].amount == Decimal("1.00000000")
    assert first.change_output is not None
    second = plan.steps[1]
    assert second.inputs[0].txid == PREVIOUS_CHANGE_SENTINEL


def test_broadcast_pattern_plan_uses_same_stack() -> None:
    rpc = DummyRPC()
    plan = plan_explicit_pattern(
        rpc,
        to_address="dgb1target",
        amounts=[Decimal("1.0"), Decimal("0.5")],
        fee=Decimal("0.1"),
    )
    txids = broadcast_pattern_plan(rpc, plan)
    assert txids == ["broadcast-txid-0", "broadcast-txid-1"]
    assert len(rpc.tx_history) == 2
    first_inputs, _ = rpc.tx_history[0]
    second_inputs, _ = rpc.tx_history[1]
    assert len(first_inputs) == len(plan.steps[0].inputs)
    assert second_inputs[0]["txid"] == txids[0]


def test_plan_explicit_pattern_rejects_dust_chain() -> None:
    class TinyUTXORPC(DummyRPC):
        def listunspent(self, minconf: int) -> list[dict[str, object]]:  # type: ignore[override]
            return [
                {"txid": "tiny1", "vout": 0, "amount": "0.0003", "spendable": True},
            ]

    rpc = TinyUTXORPC()
    with pytest.raises(PlanningError):
        plan_explicit_pattern(
            rpc,
            to_address="dgb1target",
            amounts=[Decimal("0.0002"), Decimal("0.00002")],
            fee=Decimal("0.00001"),
        )


def test_symbol_planner_chain_links_change(automation: AutomationMetadata) -> None:
    class ChainRPC(DummyRPC):
        def listunspent(self, minconf: int) -> list[dict[str, object]]:  # type: ignore[override]
            return [
                {"txid": "aa", "vout": 0, "amount": "6.0", "spendable": True},
                {"txid": "bb", "vout": 1, "amount": "5.0", "spendable": True},
            ]

    rpc = ChainRPC()
    frames = [
        AutomationFrame(value=Decimal("2"), fee=Decimal("0.1"), inputs=2, outputs=2, delta=0, sigma=0),
        AutomationFrame(value=Decimal("3"), fee=Decimal("0.1"), inputs=1, outputs=2, delta=0, sigma=0),
        AutomationFrame(value=Decimal("5"), fee=Decimal("0.1"), inputs=1, outputs=2, delta=0, sigma=0),
    ]
    symbol = AutomationSymbol(
        name="PRIME_CHAIN",
        value=Decimal("2"),
        fee=Decimal("0.1"),
        inputs=2,
        outputs=2,
        delta=0,
        sigma=0,
        frames=frames,
    )
    planner = SymbolPlanner(rpc, automation)
    chain = planner.plan_chain(symbol, receiver="dgb1target")
    assert len(chain.transactions) == 3
    assert [tx.to_output.amount for tx in chain.transactions] == [
        Decimal("2.00000000"),
        Decimal("3.00000000"),
        Decimal("5.00000000"),
    ]
    for tx in chain.transactions:
        assert tx.to_output.address == "dgb1target"
        assert tx.change_output is None or tx.change_output.address != "dgb1target"
    for idx in range(2):
        next_inputs = chain.transactions[idx + 1].inputs
        assert len(next_inputs) == 1
        assert next_inputs[0].txid == PREVIOUS_CHANGE_SENTINEL
        assert next_inputs[0].vout == 1
        assert chain.transactions[idx].change_output is not None
