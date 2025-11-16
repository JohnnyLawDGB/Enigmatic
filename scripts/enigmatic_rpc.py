#!/usr/bin/env python3
"""Utilities for orchestrating Enigmatic heartbeat transactions via DigiByte RPC."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, getcontext
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import requests
import yaml

getcontext().prec = 16

DUST_LIMIT = Decimal("0.00010000")
EIGHT_DP = Decimal("0.00000001")


@dataclass
class DialectAutomation:
    endpoint: str
    wallet: Optional[str]
    min_confirmations: int
    max_drift_blocks: int
    rebroadcast_misses: int


@dataclass
class SymbolDefinition:
    name: str
    value: Decimal
    fee: Decimal
    inputs: int
    outputs: int
    delta: int
    sigma: int

    @classmethod
    def from_yaml(cls, payload: Dict[str, object]) -> "SymbolDefinition":
        match = payload.get("match", {})
        return cls(
            name=payload["name"],
            value=Decimal(str(match["value"])),
            fee=Decimal(str(match["fee"])),
            inputs=int(match["m"]),
            outputs=int(match["n"]),
            delta=int(match.get("delta", 0)),
            sigma=int(match.get("sigma", 0)),
        )


class Dialect:
    def __init__(
        self,
        name: str,
        version: str,
        symbols: Sequence[SymbolDefinition],
        automation: DialectAutomation,
    ) -> None:
        self.name = name
        self.version = version
        self.symbols = list(symbols)
        self.automation = automation

    @classmethod
    def load(cls, path: Path) -> "Dialect":
        payload = yaml.safe_load(path.read_text())
        automation_cfg = payload.get("automation", {})
        rpc_cfg = automation_cfg.get("rpc", {})
        scheduling_cfg = automation_cfg.get("scheduling", {})
        automation = DialectAutomation(
            endpoint=rpc_cfg.get("endpoint", "http://127.0.0.1:14022"),
            wallet=rpc_cfg.get("wallet"),
            min_confirmations=int(rpc_cfg.get("min_confirmations", 1)),
            max_drift_blocks=int(scheduling_cfg.get("max_drift_blocks", 1)),
            rebroadcast_misses=int(scheduling_cfg.get("rebroadcast_misses", 2)),
        )
        symbols = [SymbolDefinition.from_yaml(entry) for entry in payload.get("symbols", [])]
        if not symbols:
            raise ValueError("Dialect does not define any symbols")
        return cls(
            name=payload.get("name", "unknown"),
            version=payload.get("version", "0.0.0"),
            symbols=symbols,
            automation=automation,
        )

    def get_symbol(self, name: Optional[str]) -> SymbolDefinition:
        if name is None:
            return self.symbols[0]
        for symbol in self.symbols:
            if symbol.name == name:
                return symbol
        raise ValueError(f"Symbol '{name}' not found in dialect {self.name}")


class RpcError(RuntimeError):
    pass


class RpcClient:
    def __init__(self, endpoint: str, user: str, password: str, wallet: Optional[str] = None):
        self.base_endpoint = endpoint.rstrip("/")
        self.wallet = wallet
        self.user = user
        self.password = password

    @property
    def endpoint(self) -> str:
        if self.wallet:
            return f"{self.base_endpoint}/wallet/{self.wallet}"
        return self.base_endpoint

    def call(self, method: str, params: Optional[Sequence[object]] = None) -> object:
        payload = {"jsonrpc": "1.0", "id": "enigmatic", "method": method, "params": params or []}
        response = requests.post(
            self.endpoint,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            auth=(self.user, self.password),
            timeout=30,
        )
        if response.status_code != 200:
            raise RpcError(f"RPC HTTP {response.status_code}: {response.text}")
        body = response.json()
        if body.get("error"):
            raise RpcError(body["error"])
        return body.get("result")

    def load_wallet(self, wallet: Optional[str]) -> None:
        self.wallet = wallet

    # Convenience helpers -------------------------------------------------
    def get_block_count(self) -> int:
        return int(self.call("getblockcount"))

    def list_unspent(self, min_conf: int) -> List[Dict[str, object]]:
        return list(self.call("listunspent", [min_conf]))

    def get_new_address(self, label: str) -> str:
        return str(self.call("getnewaddress", [label]))

    def get_change_address(self) -> str:
        return str(self.call("getrawchangeaddress"))

    def create_raw_transaction(self, inputs: List[Dict[str, object]], outputs: Dict[str, Decimal]) -> str:
        outputs_json = {address: float(amount) for address, amount in outputs.items()}
        return str(self.call("createrawtransaction", [inputs, outputs_json]))

    def sign_raw_transaction(self, raw_hex: str) -> str:
        result = self.call("signrawtransactionwithwallet", [raw_hex])
        if not result.get("complete"):
            raise RpcError("signrawtransactionwithwallet returned incomplete signature")
        return str(result["hex"])

    def send_raw_transaction(self, raw_hex: str) -> str:
        return str(self.call("sendrawtransaction", [raw_hex]))


@dataclass
class SymbolPlan:
    symbol: SymbolDefinition
    inputs: List[Dict[str, object]]
    outputs: Dict[str, Decimal]
    change_amount: Decimal
    fee: Decimal
    block_target: Optional[int]


class SymbolPlanner:
    def __init__(self, rpc: RpcClient, automation: DialectAutomation) -> None:
        self.rpc = rpc
        self.automation = automation

    def plan(self, symbol: SymbolDefinition, receiver: Optional[str]) -> SymbolPlan:
        current_height = self.rpc.get_block_count()
        block_target = None
        if symbol.delta > 0:
            block_target = current_height + symbol.delta
        utxos = self.rpc.list_unspent(self.automation.min_confirmations)
        selected, total = self._select_utxos(utxos, symbol.inputs, symbol.value + symbol.fee)
        receiver_address = receiver or self.rpc.get_new_address(symbol.name)
        outputs: Dict[str, Decimal] = {receiver_address: symbol.value}
        change_amount = (total - symbol.value - symbol.fee).quantize(EIGHT_DP)
        if change_amount < Decimal("0"):
            raise RpcError("Selected UTXOs do not cover value + fee")
        if symbol.outputs > 1:
            outputs.update(self._distribute_change(symbol.outputs - 1, change_amount))
        elif change_amount > 0:
            # If no change outputs requested, fold change back into receiver.
            outputs[receiver_address] = (outputs[receiver_address] + change_amount).quantize(EIGHT_DP)
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
        raw_hex = self.rpc.create_raw_transaction(plan.inputs, plan.outputs)
        signed = self.rpc.sign_raw_transaction(raw_hex)
        return self.rpc.send_raw_transaction(signed)

    def _select_utxos(
        self,
        utxos: Sequence[Dict[str, object]],
        required: int,
        minimum_total: Decimal,
    ) -> tuple[List[Dict[str, object]], Decimal]:
        candidates = sorted(
            (
                utxo
                for utxo in utxos
                if utxo.get("spendable", True)
            ),
            key=lambda item: Decimal(str(item["amount"])),
            reverse=True,
        )
        if len(candidates) < required:
            raise RpcError(f"Wallet only has {len(candidates)} spendable UTXOs, requires {required}")
        selected = candidates[:required]
        total = sum(Decimal(str(item["amount"])) for item in selected)
        if total < minimum_total:
            raise RpcError(
                f"Selected inputs total {total} but need at least {minimum_total} to cover symbol value and fee"
            )
        return selected, total

    def _distribute_change(self, branches: int, change_amount: Decimal) -> Dict[str, Decimal]:
        if change_amount <= 0:
            return {}
        per_branch = (change_amount / branches).quantize(EIGHT_DP)
        if per_branch < DUST_LIMIT:
            raise RpcError(
                f"Change per branch ({per_branch}) would be below dust limit for {branches} outputs"
            )
        outputs: Dict[str, Decimal] = {}
        distributed = Decimal("0")
        for index in range(branches):
            address = self.rpc.get_change_address()
            amount = per_branch if index < branches - 1 else (change_amount - distributed).quantize(EIGHT_DP)
            outputs[address] = amount
            distributed += amount
        return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit Enigmatic heartbeat transactions over RPC")
    parser.add_argument("--dialect", default="examples/dialect-heartbeat.yaml", help="Path to dialect YAML")
    parser.add_argument("--symbol", help="Symbol name defined in the dialect")
    parser.add_argument("--endpoint", help="Override RPC endpoint URL")
    parser.add_argument("--wallet", help="Override RPC wallet name")
    parser.add_argument("--receiver", help="Optional receiver address for the value-plane output")
    parser.add_argument("--broadcast", action="store_true", help="Broadcast the transaction instead of dry-run planning")
    parser.add_argument("--rpc-user", default=os.environ.get("DGB_RPC_USER"), help="RPC username (env DGB_RPC_USER)")
    parser.add_argument("--rpc-password", default=os.environ.get("DGB_RPC_PASSWORD"), help="RPC password (env DGB_RPC_PASSWORD)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.rpc_user or not args.rpc_password:
        raise SystemExit("RPC credentials must be provided via --rpc-user/--rpc-password or environment variables")
    dialect = Dialect.load(Path(args.dialect))
    automation = dialect.automation
    endpoint = args.endpoint or automation.endpoint
    wallet = args.wallet or automation.wallet
    rpc = RpcClient(endpoint=endpoint, user=args.rpc_user, password=args.rpc_password, wallet=wallet)
    symbol = dialect.get_symbol(args.symbol)
    planner = SymbolPlanner(rpc, automation)
    plan = planner.plan(symbol, args.receiver)
    print("Prepared symbol plan:")
    print(json.dumps(
        {
            "symbol": plan.symbol.name,
            "value": str(plan.symbol.value),
            "fee": str(plan.fee),
            "inputs": plan.inputs,
            "outputs": {addr: str(amount) for addr, amount in plan.outputs.items()},
            "change": str(plan.change_amount),
            "block_target": plan.block_target,
        },
        indent=2,
    ))
    if args.broadcast:
        txid = planner.broadcast(plan)
        print(f"Broadcast transaction {txid}")
    else:
        print("Dry run complete. Re-run with --broadcast to submit the transaction.")


if __name__ == "__main__":
    main()
