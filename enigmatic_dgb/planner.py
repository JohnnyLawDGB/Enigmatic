"""Automation helpers for planning Enigmatic dialect heartbeats."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, getcontext
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence

import yaml

from .rpc_client import DigiByteRPC
from .script_plane import ScriptPlane, parse_script_plane_block
from .tx_builder import TransactionBuilder

getcontext().prec = 16

DUST_LIMIT = Decimal("0.00010000")
EIGHT_DP = Decimal("0.00000001")
PREVIOUS_CHANGE_SENTINEL = "__PREVIOUS_CHANGE__"

ProgressCallback = Callable[[str], None]


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
class AutomationFrame:
    """Describes a single frame within a chained symbolic message."""

    value: Decimal
    fee: Decimal | None = None
    inputs: int | None = None
    outputs: int | None = None
    delta: int | None = None
    sigma: int | None = None
    script_plane: ScriptPlane | None = None


@dataclass
class AutomationSymbol:
    name: str
    value: Decimal
    fee: Decimal
    inputs: int
    outputs: int
    delta: int
    sigma: int
    frames: list[AutomationFrame] | None = None
    script_plane: ScriptPlane | None = None

    def chained_frames(self) -> list[AutomationFrame]:
        """Return the frames that define a chained symbol, if any."""

        return list(self.frames or [])


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
            frames_cfg = match.get("frames")
            frames: list[AutomationFrame] | None = None
            if frames_cfg is not None:
                if not isinstance(frames_cfg, list) or not frames_cfg:
                    raise PlanningError(
                        f"Symbol {entry.get('name')} frames must be a non-empty list"
                    )
                frames = []
                for idx, frame_cfg in enumerate(frames_cfg):
                    if "value" not in frame_cfg:
                        raise PlanningError(
                            f"Frame #{idx + 1} for symbol {entry.get('name')} missing value"
                        )
                    frame_script_plane = None
                    if frame_cfg.get("script_plane") is not None:
                        frame_script_plane = parse_script_plane_block(
                            frame_cfg["script_plane"],
                            lambda msg, name=entry.get("name"):
                                PlanningError(
                                    f"Frame #{idx + 1} for symbol {name}: {msg}"
                                ),
                        )
                    frames.append(
                        AutomationFrame(
                            value=Decimal(str(frame_cfg["value"])),
                            fee=Decimal(str(frame_cfg["fee"])) if "fee" in frame_cfg else None,
                            inputs=int(frame_cfg["m"]) if "m" in frame_cfg else None,
                            outputs=int(frame_cfg["n"]) if "n" in frame_cfg else None,
                            delta=int(frame_cfg["delta"]) if "delta" in frame_cfg else None,
                            sigma=int(frame_cfg["sigma"]) if "sigma" in frame_cfg else None,
                            script_plane=frame_script_plane,
                        )
                    )
            symbol_script_plane = None
            if match.get("script_plane") is not None:
                symbol_script_plane = parse_script_plane_block(
                    match["script_plane"],
                    lambda msg, sym_name=entry.get("name"):
                        PlanningError(f"Symbol {sym_name}: {msg}"),
                )
            symbol = AutomationSymbol(
                name=str(entry["name"]),
                value=Decimal(str(match["value"])),
                fee=Decimal(str(match["fee"])),
                inputs=int(match["m"]),
                outputs=int(match["n"]),
                delta=int(match.get("delta", 0)),
                sigma=int(match.get("sigma", 0)),
                frames=frames,
                script_plane=symbol_script_plane,
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
    enforce_block_target: bool = False
    script_plane: ScriptPlane | None = None

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol.name,
            "value": str(self.symbol.value),
            "fee": str(self.fee),
            "inputs": self.inputs,
            "outputs": {addr: str(amount) for addr, amount in self.outputs.items()},
            "change": str(self.change_amount.quantize(EIGHT_DP)),
            "block_target": self.block_target,
            "enforce_block_target": self.enforce_block_target,
            "script_plane": self.script_plane.to_dict() if self.script_plane else None,
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
    script_plane: ScriptPlane | None = None

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
            "script_plane": self.script_plane.to_dict() if self.script_plane else None,
        }


@dataclass
class PatternPlanSequence:
    steps: List[PatternPlan]

    def to_jsonable(self) -> Dict[str, Any]:
        return {"steps": [step.to_jsonable() for step in self.steps]}


@dataclass
class PlannedTx:
    """Represents a single transaction inside a chained plan."""

    inputs: List[PatternInput]
    to_output: PatternOutput
    change_output: PatternOutput | None
    fee: Decimal
    script_plane: ScriptPlane | None = None

    def as_rpc_inputs(self) -> List[Dict[str, Any]]:
        return [{"txid": item.txid, "vout": item.vout} for item in self.inputs]

    def as_rpc_outputs(self) -> List[Dict[str, float]]:
        outputs = [{self.to_output.address: float(self.to_output.amount)}]
        if self.change_output is not None:
            outputs.append({self.change_output.address: float(self.change_output.amount)})
        return outputs

    def to_jsonable(self, index: int) -> Dict[str, Any]:
        return {
            "index": index,
            "fee": str(self.fee),
            "inputs": [item.to_jsonable() for item in self.inputs],
            "to_output": self.to_output.to_jsonable(0),
            "change": self.change_output.to_jsonable(1)
            if self.change_output is not None
            else None,
            "script_plane": self.script_plane.to_dict() if self.script_plane else None,
        }


@dataclass
class PlannedChain:
    """Ordered set of transactions that encode a chained symbolic message."""

    to_address: str
    transactions: List[PlannedTx]
    initial_utxos: List[PatternInput]
    block_target: int | None = None
    enforce_block_target: bool = False

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "to_address": self.to_address,
            "transactions": [tx.to_jsonable(index) for index, tx in enumerate(self.transactions)],
            "initial_utxos": [entry.to_jsonable() for entry in self.initial_utxos],
            "block_target": self.block_target,
            "enforce_block_target": self.enforce_block_target,
        }

    def as_pattern_sequence(self) -> PatternPlanSequence:
        """Convert the planned chain into a pattern sequence for broadcasting."""

        steps: list[PatternPlan] = []
        for tx in self.transactions:
            outputs = [tx.to_output]
            steps.append(
                PatternPlan(
                    inputs=tx.inputs,
                    outputs=outputs,
                    change_output=tx.change_output,
                    fee=tx.fee,
                    script_plane=tx.script_plane,
                )
            )
        return PatternPlanSequence(steps=steps)


class SymbolPlanner:
    def __init__(self, rpc: DigiByteRPC, automation: AutomationMetadata) -> None:
        self.rpc = rpc
        self.automation = automation

    def plan(
        self,
        symbol: AutomationSymbol,
        receiver: str | None = None,
        *,
        block_target: int | None = None,
        enforce_block_target: bool = False,
    ) -> SymbolPlan:
        current_height = self.rpc.getblockcount()
        if block_target is not None:
            if block_target <= current_height:
                raise PlanningError("Block target must be greater than the current height")
            enforce_block_target = True
        else:
            block_target = current_height + symbol.delta if symbol.delta > 0 else None
        utxos = self.rpc.listunspent(self.automation.min_confirmations)
        selected, total = self._select_utxos(utxos, symbol.inputs, symbol.value + symbol.fee)
        script_plane = symbol.script_plane
        receiver_address = receiver or self._address_for_script_plane(script_plane)
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
            enforce_block_target=enforce_block_target,
            script_plane=script_plane,
        )

    def plan_chain(
        self,
        symbol: AutomationSymbol,
        *,
        receiver: str | None = None,
        max_frames: int | None = None,
        min_confirmations: int | None = None,
        block_target: int | None = None,
        enforce_block_target: bool = False,
    ) -> PlannedChain:
        """Plan a chained representation of a symbol using its declared frames."""
        frames = symbol.chained_frames()
        if not frames:
            raise PlanningError(f"Symbol {symbol.name} does not define chained frames")
        if max_frames is not None:
            frames = frames[:max_frames]
        if not frames:
            raise PlanningError("max_frames truncated the chain to zero frames")
        to_address = receiver or self._address_for_script_plane(symbol.script_plane)
        normalized_frames: list[AutomationFrame] = []
        for frame in frames:
            normalized_frames.append(
                AutomationFrame(
                    value=frame.value.quantize(EIGHT_DP, rounding=ROUND_DOWN),
                    fee=(frame.fee or symbol.fee).quantize(EIGHT_DP, rounding=ROUND_DOWN),
                    inputs=frame.inputs,
                    outputs=frame.outputs,
                    delta=frame.delta,
                    sigma=frame.sigma,
                )
            )
        required_inputs = normalized_frames[0].inputs or symbol.inputs
        if required_inputs <= 0:
            raise PlanningError("Chained plan requires at least one input in the first frame")
        if block_target is not None and block_target <= self.rpc.getblockcount():
            raise PlanningError("Block target must be greater than the current height")
        if block_target is not None:
            enforce_block_target = True
        total_required = sum(frame.value + frame.fee for frame in normalized_frames)
        minconf = (
            min_confirmations
            if min_confirmations is not None
            else self.automation.min_confirmations
        )
        utxos = self.rpc.listunspent(minconf)
        selected, total = self._select_utxos(utxos, required_inputs, total_required)
        transactions: list[PlannedTx] = []
        available_pool = total
        previous_change_amount: Decimal | None = None
        initial_utxos: list[PatternInput] | None = None
        for index, frame in enumerate(normalized_frames):
            fee = frame.fee
            if fee < 0:
                raise PlanningError("Fee must be non-negative for chained plans")
            value = frame.value
            if value <= 0:
                raise PlanningError("Each chained frame must send a positive value")
            remaining_required = sum(
                next_frame.value + next_frame.fee for next_frame in normalized_frames[index + 1 :]
            )
            if index > 0 and frame.inputs not in (None, 1):
                raise PlanningError("Only the first chained frame may specify multiple inputs")
            if index == 0:
                inputs = [
                    PatternInput(
                        txid=str(entry["txid"]),
                        vout=int(entry["vout"]),
                        amount=Decimal(str(entry["amount"])),
                    )
                    for entry in selected
                ]
            else:
                if previous_change_amount is None:
                    raise PlanningError("Previous change amount missing for chained frame")
                inputs = [
                    PatternInput(
                        txid=PREVIOUS_CHANGE_SENTINEL,
                        vout=1,
                        amount=previous_change_amount,
                    )
                ]
            if available_pool < value + fee:
                raise PlanningError("Insufficient funds to satisfy chained plan")
            change_amount = (available_pool - value - fee).quantize(EIGHT_DP, rounding=ROUND_DOWN)
            if index < len(normalized_frames) - 1 and change_amount < DUST_LIMIT:
                raise PlanningError("Intermediate change would fall below dust limit")
            if change_amount < remaining_required:
                raise PlanningError("Change does not cover downstream frames; adjust fees or values")
            to_output = PatternOutput(address=to_address, amount=value)
            change_output: PatternOutput | None = None
            if change_amount >= DUST_LIMIT:
                change_address = self.rpc.getrawchangeaddress()
                change_output = PatternOutput(address=change_address, amount=change_amount)
                previous_change_amount = change_amount
                available_pool = change_amount
            else:
                available_pool = change_amount
                if change_amount > 0:
                    to_output = PatternOutput(
                        address=to_output.address,
                        amount=(to_output.amount + change_amount).quantize(
                            EIGHT_DP, rounding=ROUND_DOWN
                        ),
                    )
                previous_change_amount = None
            if index == 0:
                initial_utxos = list(inputs)
            tx_script_plane = frame.script_plane or symbol.script_plane
            transactions.append(
                PlannedTx(
                    inputs=inputs,
                    to_output=to_output,
                    change_output=change_output,
                    fee=fee,
                    script_plane=tx_script_plane,
                )
            )
        assert initial_utxos is not None  # for mypy; first frame always sets it
        funding_inputs = [item for item in initial_utxos if item.txid != PREVIOUS_CHANGE_SENTINEL]
        return PlannedChain(
            to_address=to_address,
            transactions=transactions,
            initial_utxos=funding_inputs,
            block_target=block_target,
            enforce_block_target=enforce_block_target,
        )

    def _wait_for_block_target(
        self,
        block_target: int,
        *,
        progress_callback: ProgressCallback | None = None,
        poll_seconds: float = 15.0,
    ) -> None:
        """Pause until the chain is within the scheduling window for the target block."""

        drift = self.automation.max_drift_blocks
        current_height = self.rpc.getblockcount()
        if current_height > block_target + drift:
            raise PlanningError(
                f"Current height {current_height} exceeds drift window for target {block_target}"
            )
        while current_height < block_target - drift:
            remaining = block_target - current_height
            if progress_callback is not None:
                progress_callback(
                    f"Waiting for block {block_target} (current {current_height}, remaining {remaining})"
                )
            time.sleep(poll_seconds)
            current_height = self.rpc.getblockcount()

    def broadcast(
        self, plan: SymbolPlan, *, poll_seconds: float = 15.0, progress_callback: ProgressCallback | None = None
    ) -> str:
        if plan.enforce_block_target and plan.block_target is not None:
            self._wait_for_block_target(
                plan.block_target, progress_callback=progress_callback, poll_seconds=poll_seconds
            )
        outputs_json = {addr: float(amount) for addr, amount in plan.outputs.items()}
        raw_hex = self.rpc.createrawtransaction(plan.inputs, outputs_json)
        signed = self.rpc.signrawtransactionwithwallet(raw_hex)
        if not signed.get("complete"):
            raise PlanningError("signrawtransactionwithwallet returned incomplete signature")
        return self.rpc.sendrawtransaction(signed["hex"])

    def broadcast_chain(
        self,
        plan: PlannedChain,
        *,
        wait_between_txs: float = 0.0,
        min_confirmations_between_steps: int = 0,
        max_wait_seconds: float | None = None,
        progress_callback: ProgressCallback | None = None,
        builder: TransactionBuilder | None = None,
        poll_seconds: float = 15.0,
    ) -> list[str]:
        """Broadcast each transaction in a chained plan sequentially."""

        if plan.enforce_block_target and plan.block_target is not None:
            self._wait_for_block_target(
                plan.block_target, progress_callback=progress_callback, poll_seconds=poll_seconds
            )
        pattern_sequence = plan.as_pattern_sequence()
        return broadcast_pattern_plan(
            self.rpc,
            pattern_sequence,
            wait_between_txs=wait_between_txs,
            min_confirmations_between_steps=min_confirmations_between_steps,
            max_wait_seconds=max_wait_seconds,
            progress_callback=progress_callback,
            builder=builder,
        )

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

    def _address_for_script_plane(self, script_plane: ScriptPlane | None) -> str:
        if script_plane and script_plane.script_type.lower() == "p2tr":
            try:
                return self.rpc.getnewaddress(address_type="bech32m")
            except TypeError:  # pragma: no cover - older node compatibility
                return self.rpc.getnewaddress()
        return self.rpc.getnewaddress()


def plan_explicit_pattern(
    rpc: DigiByteRPC,
    *,
    to_address: str,
    amounts: Sequence[Decimal],
    fee: Decimal,
    min_confirmations: int = 1,
    script_plane: ScriptPlane | None = None,
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
                script_plane=script_plane,
            )
        )
        pending_change_amount = change_amount
    return PatternPlanSequence(steps=steps)


def broadcast_pattern_plan(
    rpc: DigiByteRPC,
    plan: PatternPlanSequence,
    *,
    op_returns: Sequence[str | None] | None = None,
    wait_between_txs: float = 0.0,
    min_confirmations_between_steps: int = 0,
    max_wait_seconds: float | None = None,
    progress_callback: ProgressCallback | None = None,
    builder: TransactionBuilder | None = None,
    single_tx: bool = False,
) -> list[str]:
    """Broadcast a chained pattern plan using the transaction builder."""

    if op_returns is not None and len(op_returns) != len(plan.steps):
        raise PlanningError("OP_RETURN payload count must match the number of transactions")

    tx_builder = builder or TransactionBuilder(rpc)
    txids: list[str] = []

    if single_tx:
        if not plan.steps:
            return []

        primary_outputs = [step.outputs[0] for step in plan.steps]
        destination_addresses = {output.address for output in primary_outputs}
        if len(destination_addresses) != 1:
            raise PlanningError("Single fan-out mode requires a consistent destination address")
        to_address = destination_addresses.pop()

        fanout_fee = plan.steps[0].fee
        if any(step.fee != fanout_fee for step in plan.steps):
            raise PlanningError("Single fan-out mode requires a uniform fee across frames")

        script_planes = {step.script_plane for step in plan.steps}
        script_plane = script_planes.pop() if len(script_planes) == 1 else None
        if len(script_planes) > 1:
            raise PlanningError("Single fan-out mode does not support mixed script planes")

        payload = None
        if op_returns is not None:
            non_null_payloads = [value for value in op_returns if value]
            if len(non_null_payloads) > 1:
                raise PlanningError(
                    "Single fan-out mode supports at most one OP_RETURN payload across frames"
                )
            payload = non_null_payloads[0] if non_null_payloads else None

        amounts = [output.amount for output in primary_outputs]
        if progress_callback is not None:
            progress_callback(
                f"Building single fan-out transaction with {len(amounts)} outputs and fee {fanout_fee}"
            )

        payload_list = [payload] if payload else None
        txid = tx_builder.send_multi_output_tx(
            to_address,
            amounts,
            float(fanout_fee),
            op_return_data=payload_list,
            script_plane=script_plane,
        )
        txids.append(txid)
        if progress_callback is not None:
            progress_callback(f"Broadcasted fan-out transaction {txid}")
        return txids
    previous_change_ref: tuple[str, int] | None = None
    for index, step in enumerate(plan.steps, start=1):
        rpc_inputs = _resolve_chained_inputs(step.inputs, previous_change_ref)
        ordered_outputs: "OrderedDict[str, float]" = OrderedDict()
        for output in step.outputs:
            ordered_outputs[output.address] = float(output.amount)
        change_index: int | None = None
        if step.change_output is not None:
            change_index = len(ordered_outputs)
            ordered_outputs[step.change_output.address] = float(step.change_output.amount)
        payload = op_returns[index - 1] if op_returns is not None else None
        payload_list = [payload] if payload else None
        txid = tx_builder.send_payment_tx(
            ordered_outputs,
            float(step.fee),
            op_return_data=payload_list,
            inputs=rpc_inputs,
            script_plane=step.script_plane,
        )
        txids.append(txid)
        if progress_callback is not None:
            progress_callback(f"Tx{index}: broadcast {txid}")
        if change_index is not None:
            previous_change_ref = (txid, change_index)
        else:
            previous_change_ref = None
        is_last_step = index == len(plan.steps)
        if not is_last_step:
            if previous_change_ref is None:
                raise PlanningError("Chained plan ended before downstream steps could be funded")
            if min_confirmations_between_steps > 0:
                _wait_for_confirmations(
                    rpc,
                    txid,
                    index,
                    min_confirmations_between_steps,
                    wait_between_txs,
                    max_wait_seconds,
                    progress_callback,
                )
            elif wait_between_txs > 0:
                time.sleep(wait_between_txs)
    return txids


def _resolve_chained_inputs(
    inputs: Sequence[PatternInput], previous_change_ref: tuple[str, int] | None
) -> list[Dict[str, Any]]:
    rpc_inputs: list[Dict[str, Any]] = []
    for entry in inputs:
        if entry.txid == PREVIOUS_CHANGE_SENTINEL:
            if previous_change_ref is None:
                raise PlanningError(
                    "Chained plan referenced previous change output before it was created"
                )
            rpc_inputs.append({"txid": previous_change_ref[0], "vout": previous_change_ref[1]})
        else:
            rpc_inputs.append({"txid": entry.txid, "vout": entry.vout})
    return rpc_inputs


def _wait_for_confirmations(
    rpc: DigiByteRPC,
    txid: str,
    tx_index: int,
    required_confirmations: int,
    wait_between_txs: float,
    max_wait_seconds: float | None,
    progress_callback: ProgressCallback | None,
) -> None:
    poll_interval = wait_between_txs if wait_between_txs > 0 else 5.0
    waited = 0.0
    while True:
        confirmations = _query_confirmations(rpc, txid)
        if confirmations >= required_confirmations:
            if progress_callback is not None:
                progress_callback(
                    f"Tx{tx_index}: reached {confirmations} confirmations "
                    f"(required {required_confirmations})"
                )
            return
        if progress_callback is not None:
            progress_callback(
                f"Tx{tx_index}: waiting for {required_confirmations} confirmations "
                f"(current: {confirmations})"
            )
        if max_wait_seconds is not None and waited >= max_wait_seconds:
            raise PlanningError(
                f"Tx{tx_index} did not reach {required_confirmations} confirmations "
                f"within {max_wait_seconds} seconds"
            )
        time.sleep(poll_interval)
        waited += poll_interval


def _query_confirmations(rpc: DigiByteRPC, txid: str) -> int:
    try:
        info = rpc.gettransaction(txid)
    except Exception:  # pragma: no cover - defensive against transient RPC failures
        return 0
    confirmations = info.get("confirmations")
    try:
        return int(confirmations)
    except (TypeError, ValueError):  # pragma: no cover - defensive parsing
        return 0


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
