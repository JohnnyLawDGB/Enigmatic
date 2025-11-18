"""Transaction builder utilities for DigiByte."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

from .rpc_client import DigiByteRPC, RPCError

logger = logging.getLogger(__name__)


@dataclass
class UTXO:
    txid: str
    vout: int
    amount: float
    address: str | None = None


class UTXOManager:
    """Helper for selecting UTXOs from a DigiByte wallet."""

    def __init__(self, rpc: DigiByteRPC) -> None:
        self.rpc = rpc

    def list_unspent(self, addresses: Iterable[str] | None = None) -> List[Dict[str, Any]]:
        addr_list = list(addresses) if addresses is not None else None
        return self.rpc.listunspent(addresses=addr_list)

    def select_utxos(self, target_amount: float, fee: float) -> Tuple[List[UTXO], float]:
        """Select UTXOs to cover target amount + fee."""

        utxos = [
            UTXO(
                txid=item["txid"],
                vout=item["vout"],
                amount=float(item["amount"]),
                address=item.get("address"),
            )
            for item in self.rpc.listunspent()
        ]
        if not utxos:
            raise RuntimeError("Wallet has no spendable UTXOs")

        needed = target_amount + fee
        selected: List[UTXO] = []
        total = 0.0

        for utxo in sorted(utxos, key=lambda u: u.amount):
            selected.append(utxo)
            total += utxo.amount
            if total >= needed:
                break

        if total < needed:
            raise RuntimeError(
                f"Insufficient funds: needed {needed}, selected {total}"
            )

        change = total - target_amount - fee
        return selected, change


class TransactionBuilder:
    """Build and send DigiByte transactions without encoding knowledge."""

    def __init__(self, rpc: DigiByteRPC) -> None:
        self.rpc = rpc
        self.utxo_manager = UTXOManager(rpc)

    def build_payment_tx(
        self,
        outputs: Dict[str, float],
        fee: float,
        op_return_data: list[str] | None = None,
        inputs: List[Dict[str, Any]] | None = None,
    ) -> str:
        """Create a signed raw transaction paying outputs with the provided fee."""

        logger.info("Building transaction for %d outputs", len(outputs))
        if inputs is not None:
            prepared_outputs = self._prepare_outputs_payload(outputs, op_return_data)
            raw_tx = self.rpc.createrawtransaction(inputs, prepared_outputs)
            selected_utxos: List[UTXO] = []
            change_amount = 0.0
        else:
            total_output = sum(outputs.values())
            selected_utxos = []
            change_amount = 0.0

            raw_tx: str | None = None

            prepared_outputs = self._prepare_outputs_payload(outputs, op_return_data)

            try:
                logger.debug("Attempting automatic funding via fundrawtransaction")
                tmp_raw = self.rpc.createrawtransaction([], prepared_outputs)
                fee_rate = self._estimate_fee_rate(fee)
                funded = self.rpc.fundrawtransaction(tmp_raw, {"feeRate": fee_rate})
                raw_tx = funded["hex"]
                actual_fee = funded.get("fee")
                if actual_fee is not None and abs(actual_fee - fee) > 0.01:
                    logger.warning(
                        "Wallet chose fee %.8f different from requested %.8f", actual_fee, fee
                    )
            except RPCError as exc:
                logger.info("fundrawtransaction unavailable or failed: %s", exc)

            if raw_tx is None:
                total_output = sum(outputs.values())
                selected_utxos, change_amount = self.utxo_manager.select_utxos(total_output, fee)
                logger.debug("Selected %d UTXOs totaling %.8f DGB", len(selected_utxos), sum(u.amount for u in selected_utxos))
                tx_inputs = [{"txid": utxo.txid, "vout": utxo.vout} for utxo in selected_utxos]
                if change_amount > 1e-8:
                    change_address = self.rpc.getnewaddress()
                    outputs[change_address] = round(change_amount, 8)

                manual_outputs = self._prepare_outputs_payload(outputs, op_return_data)

                raw_tx = self.rpc.createrawtransaction(tx_inputs, manual_outputs)

        signed = self.rpc.signrawtransactionwithwallet(raw_tx)
        if not signed.get("complete"):
            raise RuntimeError("Node failed to produce a complete signature set")
        signed_hex = signed["hex"]

        # Best effort fee check
        if selected_utxos:
            total_in = sum(u.amount for u in selected_utxos)
            total_out = sum(outputs.values()) + max(change_amount, 0)
            actual_fee = total_in - total_out
            if abs(actual_fee - fee) > 0.01:
                logger.warning(
                    "Manual selection fee %.8f differs from requested %.8f", actual_fee, fee
                )
        return signed_hex

    def send_payment_tx(
        self,
        outputs: Dict[str, float],
        fee: float,
        op_return_data: list[str] | None = None,
        inputs: List[Dict[str, Any]] | None = None,
    ) -> str:
        """Build and broadcast a payment transaction, returning the txid."""

        raw_tx = self.build_payment_tx(
            outputs,
            fee,
            op_return_data=op_return_data,
            inputs=inputs,
        )
        txid = self.rpc.sendrawtransaction(raw_tx)
        logger.info("Broadcasted transaction %s", txid)
        return txid

    @staticmethod
    def _prepare_outputs_payload(
        outputs: Dict[str, float], op_return_data: list[str] | None
    ) -> list[Dict[str, Any]] | Dict[str, float]:
        if not op_return_data:
            return dict(outputs)
        payload: list[Dict[str, Any]] = [{addr: amount} for addr, amount in outputs.items()]
        for data in op_return_data:
            payload.append({"data": data})
        return payload

    @staticmethod
    def _estimate_fee_rate(fee: float, assumed_vbytes: int = 250) -> float:
        """Rudimentary conversion from absolute fee to feeRate (coin/kvB)."""

        kvb = assumed_vbytes / 1000
        if kvb == 0:
            kvb = 0.001
        return fee / kvb
