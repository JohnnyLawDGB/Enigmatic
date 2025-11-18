"""Automation helpers for planning Enigmatic dialect heartbeats."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, getcontext
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import yaml

from .rpc_client import DigiByteRPC

getcontext().prec = 16

DUST_LIMIT = Decimal("0.00010000")
EIGHT_DP = Decimal("0.00000001")
PREVIOUS_CHANGE_SENTINEL = "__PREVIOUS_CHANGE__"


class PlanningError(RuntimeError):
    """Raised when an automation plan cannot be satisfied."""


@dataclass
class AutomationMetadata:
    endpoint: str
    wallet: str | None
    min_confirmations: int
    max_drift_blocks: int
    rebroadcast_misses: int


@dataclass
class AutomationSymbol:
    name: str
    value: Decimal
    fee: Decimal
    inputs: int
    outputs: int
    delta: int
    sigma: int


@dataclass
class AutomationDialect:
    name: str
    version: str
    symbols: dict[str, AutomationSymbol]
    automation: AutomationMetadata

    @classmethod
    def load(cls, path: str | Path) -> "AutomationDialect":
        path = Path(path)
        if not path.exists():
            raise PlanningError(f"Dialect file does not exist: {path}")
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:  # pragma: no cover - delegated to yaml
            raise PlanningError(f"Failed to parse dialect YAML: {exc}") from exc
        name = str(data.get("name", "unknown"))
        version = str(data.get("version", "0.0.0"))
        automation_cfg = data.get("automation", {})
        rpc_cfg = automation_cfg.get("rpc", {})
        scheduling_cfg = automation_cfg.get("scheduling", {})
        automation = AutomationMetadata(
            endpoint=str(rpc_cfg.get("endpoint", "http://127.0.0.1:14022")),
            wallet=rpc_cfg.get("wallet"),
            min_confirmations=int(rpc_cfg.get("min_confirmations", 1)),
            max_drift_blocks=int(scheduling_cfg.get("max_drift_blocks", 1)),
            rebroadcast_misses=int(scheduling_cfg.get("rebroadcast_misses", 2)),
        )
        symbols_data = data.get("symbols", [])
        if not isinstance(symbols_data, list) or not symbols_data:
            raise PlanningError(f"Dialect {name} must define a non-empty symbols list")
        symbols: dict[str, AutomationSymbol] = {}
        for entry in symbols_data:
            match = entry.get("match") or {}
            if not match:
                raise PlanningError(f"Symbol {entry.get('name')} missing match section")
            symbol = AutomationSymbol(
                name=str(entry["name"]),
                value=Decimal(str(match["value"])),
                fee=Decimal(str(match["fee"])),
                inputs=int(match["m"]),
                outputs=int(match["n"]),
                delta=int(match.get("delta", 0)),
                sigma=int(match.get("sigma", 0)),
            )
            symbols[symbol.name] = symbol
        if not symbols:
            raise PlanningError(f"Dialect {name} does not define any symbols")
        return cls(name=name, version=version, symbols=symbols, automation=automation)

    def get_symbol(self, name: str | None) -> AutomationSymbol:
        if name is None:
            return next(iter(self.symbols.values()))
        if name not in self.symbols:
            raise PlanningError(f"Symbol {name} not found in dialect {self.name}")
        return self.symbols[name]


@dataclass
class SymbolPlan:
    symbol: AutomationSymbol
    inputs: List[Dict[str, Any]]
    outputs: Dict[str, Decimal]
    change_amount: Decimal
    fee: Decimal
    block_target: int | None

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol.name,
            "value": str(self.symbol.value),
            "fee": str(self.fee),
            "inputs": self.inputs,
            "outputs": {addr: str(amount) for addr, amount in self.outputs.items()},
            "change": str(self.change_amount.quantize(EIGHT_DP)),
            "block_target": self.block_target,
        }


@dataclass
class PatternInput:
    txid: str
    vout: int
    amount: Decimal

    def to_jsonable(self) -> Dict[str, Any]:
        return {"txid": self.txid, "vout": self.vout, "amount": str(self.amount)}


@dataclass
class PatternOutput:
    address: str
    amount: Decimal

    def to_jsonable(self, index: int) -> Dict[str, Any]:
        return {"index": index, "address": self.address, "amount": str(self.amount)}


@dataclass
class PatternPlan:
    inputs: List[PatternInput]
    outputs: List[PatternOutput]
    change_output: PatternOutput | None
    fee: Decimal

    def as_rpc_inputs(self) -> List[Dict[str, Any]]:
        return [{"txid": item.txid, "vout": item.vout} for item in self.inputs]

    def as_rpc_outputs(self) -> List[Dict[str, float]]:
        serialized = [{output.address: float(output.amount)} for output in self.outputs]
        if self.change_output is not None:
            serialized.append({self.change_output.address: float(self.change_output.amount)})
        return serialized

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "fee": str(self.fee),
            "inputs": [item.to_jsonable() for item in self.inputs],
            "outputs": [output.to_jsonable(index) for index, output in enumerate(self.outputs)],
            "change": self.change_output.to_jsonable(len(self.outputs))
            if self.change_output is not None
            else None,
        }


@dataclass
class PatternPlanSequence:
    steps: List[PatternPlan]

    def to_jsonable(self) -> Dict[str, Any]:
        return {"steps": [step.to_jsonable() for step in self.steps]}


class SymbolPlanner:
    def __init__(self, rpc: DigiByteRPC, automation: AutomationMetadata) -> None:
        self.rpc = rpc
        self.automation = automation

    def plan(self, symbol: AutomationSymbol, receiver: str | None = None) -> SymbolPlan:
        current_height = self.rpc.getblockcount()
        block_target = current_height + symbol.delta if symbol.delta > 0 else None
        utxos = self.rpc.listunspent(self.automation.min_confirmations)
        selected, total = self._select_utxos(utxos, symbol.inputs, symbol.value + symbol.fee)
        receiver_address = receiver or self.rpc.getnewaddress()
        outputs: Dict[str, Decimal] = {receiver_address: symbol.value}
        change_amount = (total - symbol.value - symbol.fee).quantize(EIGHT_DP, rounding=ROUND_DOWN)
        if symbol.outputs > 1:
            if change_amount <= 0:
                raise PlanningError(
                    f"Symbol {symbol.name} requires {symbol.outputs} outputs but change pool is empty"
                )
            outputs.update(self._distribute_change(symbol.outputs - 1, change_amount))
        elif change_amount > 0:
            outputs[receiver_address] = (outputs[receiver_address] + change_amount).quantize(
                EIGHT_DP,
                rounding=ROUND_DOWN,
            )
            change_amount = Decimal("0")
        return SymbolPlan(
            symbol=symbol,
            inputs=[{"txid": utxo["txid"], "vout": utxo["vout"]} for utxo in selected],
            outputs=outputs,
            change_amount=change_amount,
            fee=symbol.fee,
            block_target=block_target,
        )

    def broadcast(self, plan: SymbolPlan) -> str:
        outputs_json = {addr: float(amount) for addr, amount in plan.outputs.items()}
        raw_hex = self.rpc.createrawtransaction(plan.inputs, outputs_json)
        signed = self.rpc.signrawtransactionwithwallet(raw_hex)
        if not signed.get("complete"):
            raise PlanningError("signrawtransactionwithwallet returned incomplete signature")
        return self.rpc.sendrawtransaction(signed["hex"])

    def _select_utxos(
        self,
        utxos: Sequence[Mapping[str, Any]],
        required_inputs: int,
        minimum_total: Decimal,
    ) -> tuple[list[Mapping[str, Any]], Decimal]:
        spendable = [
            utxo
            for utxo in utxos
            if utxo.get("spendable", True)
        ]
        if len(spendable) < required_inputs:
            raise PlanningError(
                f"Wallet only has {len(spendable)} spendable UTXOs, requires {required_inputs}"
            )
        candidates = sorted(
            spendable,
            key=lambda item: Decimal(str(item["amount"])),
            reverse=True,
        )
        selected = candidates[:required_inputs]
        total = sum(Decimal(str(item["amount"])) for item in selected)
        if total < minimum_total:
            raise PlanningError(
                f"Selected inputs total {total} but need at least {minimum_total} to cover symbol value and fee"
            )
        return selected, total

    def _distribute_change(self, branches: int, change_amount: Decimal) -> Dict[str, Decimal]:
        if change_amount <= 0:
            return {}
        per_branch = (change_amount / branches).quantize(EIGHT_DP, rounding=ROUND_DOWN)
        if per_branch < DUST_LIMIT:
            raise PlanningError(
                f"Change per branch ({per_branch}) would be below dust limit for {branches} outputs"
            )
        outputs: Dict[str, Decimal] = {}
        distributed = Decimal("0")
        for index in range(branches):
            address = self.rpc.getrawchangeaddress()
            amount = (
                per_branch
                if index < branches - 1
                else (change_amount - distributed).quantize(EIGHT_DP, rounding=ROUND_DOWN)
            )
            outputs[address] = amount
            distributed += amount
        return outputs


def plan_explicit_pattern(
    rpc: DigiByteRPC,
    *,
    to_address: str,
    amounts: Sequence[Decimal],
    fee: Decimal,
    min_confirmations: int = 1,
) -> PatternPlanSequence:
    if not amounts:
        raise PlanningError("At least one output amount must be provided")
    normalized_amounts: list[Decimal] = []
    total_pattern = Decimal("0")
    for amount in amounts:
        if amount <= 0:
            raise PlanningError("Each output amount must be greater than zero")
        quantized = amount.quantize(EIGHT_DP, rounding=ROUND_DOWN)
        normalized_amounts.append(quantized)
        total_pattern += quantized
    if total_pattern <= 0:
        raise PlanningError("Total output amount must be greater than zero")
    if fee < 0:
        raise PlanningError("Fee must be non-negative")
    required_total = total_pattern + (fee * len(normalized_amounts))
    utxos = rpc.listunspent(min_confirmations)
    selected, total = _select_utxos_covering_total(utxos, required_total)
    pattern_inputs = [
        PatternInput(
            txid=str(entry["txid"]),
            vout=int(entry["vout"]),
            amount=Decimal(str(entry["amount"])),
        )
        for entry in selected
    ]
    available_pool = total
    pending_change_amount: Decimal | None = None
    steps: list[PatternPlan] = []
    for index, amount in enumerate(normalized_amounts):
        if index == 0:
            step_inputs = pattern_inputs
        else:
            if pending_change_amount is None:
                raise PlanningError("Chained plan expected change from previous step")
            if pending_change_amount < DUST_LIMIT:
                raise PlanningError(
                    "Intermediate chained change would fall below dust limit; adjust fee or amounts"
                )
            available_pool = pending_change_amount
            step_inputs = [
                PatternInput(
                    txid=PREVIOUS_CHANGE_SENTINEL,
                    vout=0,
                    amount=pending_change_amount,
                )
            ]
        if available_pool < amount + fee:
            raise PlanningError("Insufficient funds for requested pattern amounts and fees")
        change_amount = (available_pool - amount - fee).quantize(EIGHT_DP, rounding=ROUND_DOWN)
        step_outputs = [PatternOutput(address=to_address, amount=amount)]
        change_output: PatternOutput | None = None
        is_last = index == len(normalized_amounts) - 1
        if change_amount > 0:
            if change_amount < DUST_LIMIT and not is_last:
                raise PlanningError(
                    "Intermediate chained change would fall below dust limit; adjust fee or amounts"
                )
            if change_amount >= DUST_LIMIT:
                change_address = rpc.getrawchangeaddress()
                change_output = PatternOutput(address=change_address, amount=change_amount)
            else:
                step_outputs[-1] = PatternOutput(
                    address=step_outputs[-1].address,
                    amount=(step_outputs[-1].amount + change_amount).quantize(
                        EIGHT_DP, rounding=ROUND_DOWN
                    ),
                )
                change_amount = Decimal("0")
        steps.append(
            PatternPlan(
                inputs=step_inputs,
                outputs=step_outputs,
                change_output=change_output,
                fee=fee,
            )
        )
        pending_change_amount = change_amount
    return PatternPlanSequence(steps=steps)


def broadcast_pattern_plan(rpc: DigiByteRPC, plan: PatternPlanSequence) -> list[str]:
    txids: list[str] = []
    previous_change_ref: tuple[str, int] | None = None
    for step in plan.steps:
        rpc_inputs: list[Dict[str, Any]] = []
        for entry in step.inputs:
            if entry.txid == PREVIOUS_CHANGE_SENTINEL:
                if previous_change_ref is None:
                    raise PlanningError(
                        "Chained plan referenced previous change output before it was created"
                    )
                rpc_inputs.append({"txid": previous_change_ref[0], "vout": previous_change_ref[1]})
            else:
                rpc_inputs.append({"txid": entry.txid, "vout": entry.vout})
        outputs = step.as_rpc_outputs()
        raw_hex = rpc.createrawtransaction(rpc_inputs, outputs)
        signed = rpc.signrawtransactionwithwallet(raw_hex)
        if not signed.get("complete"):
            raise PlanningError("signrawtransactionwithwallet returned incomplete signature")
        txid = rpc.sendrawtransaction(signed["hex"])
        txids.append(txid)
        if step.change_output is not None:
            previous_change_ref = (txid, len(step.outputs))
        else:
            previous_change_ref = None
    return txids


def _select_utxos_covering_total(
    utxos: Sequence[Mapping[str, Any]], minimum_total: Decimal
) -> tuple[list[Mapping[str, Any]], Decimal]:
    spendable = [
        utxo
        for utxo in utxos
        if utxo.get("spendable", True)
    ]
    if not spendable:
        raise PlanningError("Wallet has no spendable UTXOs")
    candidates = sorted(
        spendable,
        key=lambda item: Decimal(str(item["amount"])),
        reverse=True,
    )
    selected: list[Mapping[str, Any]] = []
    total = Decimal("0")
    for utxo in candidates:
        selected.append(utxo)
        total += Decimal(str(utxo["amount"]))
        if total >= minimum_total:
            break
    if total < minimum_total:
        raise PlanningError(
            f"Selected inputs total {total} but need at least {minimum_total} to cover requested outputs and fee"
        )
    return selected, total
