"""Transaction builder utilities for DigiByte."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

from .rpc_client import DigiByteRPC, RPCError
from .script_plane import ScriptPlane
from .fees import sat_vb_to_dgb_per_kvb
from .fees import sat_vb_to_dgb_per_kvb

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

    def list_unspent(
        self, addresses: Iterable[str] | None = None, min_confirmations: int = 1
    ) -> List[Dict[str, Any]]:
        addr_list = list(addresses) if addresses is not None else None
        return self.rpc.listunspent(min_confirmations, addresses=addr_list)

    def select_utxos(
        self, target_amount: float, fee: float, min_confirmations: int = 1
    ) -> Tuple[List[UTXO], float]:
        """Select UTXOs to cover target amount + fee."""

        utxos = [
            UTXO(
                txid=item["txid"],
                vout=item["vout"],
                amount=float(item["amount"]),
                address=item.get("address"),
            )
            for item in self.rpc.listunspent(min_confirmations)
        ]
        if not utxos:
            logger.warning(
                "Wallet has no spendable UTXOs (min_confirmations=%s); fund or unlock the wallet.",
                min_confirmations,
            )
            raise RuntimeError(
                "Wallet has no spendable UTXOs. Fund or unlock the wallet and consider lowering --min-confirmations if you need to spend recent receipts."
            )

        needed = target_amount + fee
        selected: List[UTXO] = []
        total = 0.0

        for utxo in sorted(utxos, key=lambda u: u.amount):
            selected.append(utxo)
            total += utxo.amount
            if total >= needed:
                break

        if total < needed:
            logger.warning(
                "Insufficient funds for spend: needed=%.8f, available=%.8f (min_confirmations=%s)",
                needed,
                total,
                min_confirmations,
            )
            raise RuntimeError(
                f"Insufficient funds: needed {needed}, selected {total}. Fund or unlock the wallet and consider lowering --min-confirmations."
            )

        change = total - target_amount - fee
        return selected, change


class TransactionBuilder:
    """Build and send DigiByte transactions without encoding knowledge."""

    DEFAULT_RELAY_SAFE_FEE_RATE = 0.0002

    def __init__(self, rpc: DigiByteRPC) -> None:
        self.rpc = rpc
        self.utxo_manager = UTXOManager(rpc)

    def build_payment_tx(
        self,
        outputs: Dict[str, float],
        fee: float,
        op_return_data: list[str] | None = None,
        inputs: List[Dict[str, Any]] | None = None,
        script_plane: ScriptPlane | None = None,
        fee_rate_override: float | None = None,
        replaceable: bool | None = None,
    ) -> str:
        """Create a signed raw transaction paying outputs with the provided fee."""

        extra_log: Dict[str, Any] = {}
        if script_plane is not None:
            extra_log["script_plane"] = script_plane.to_dict()
        logger.info(
            "Building transaction for %d outputs", len(outputs), extra=extra_log or None
        )
        if inputs is not None:
            prepared_outputs = self._prepare_outputs_payload(outputs, op_return_data)
            formatted_outputs = self._format_outputs_for_rpc(prepared_outputs)
            # DigiByte/Bitcoin RPC: each outputs entry must be an object with exactly one key (address->amount or data->hex).
            raw_tx = self.rpc.createrawtransaction(inputs, formatted_outputs)
            selected_utxos: List[UTXO] = []
            change_amount = 0.0
        else:
            total_output = sum(outputs.values())
            selected_utxos = []
            change_amount = 0.0

            raw_tx: str | None = None

            prepared_outputs = self._prepare_outputs_payload(outputs, op_return_data)
            formatted_outputs = self._format_outputs_for_rpc(prepared_outputs)

            try:
                logger.debug("Attempting automatic funding via fundrawtransaction")
                tmp_raw = self.rpc.createrawtransaction([], formatted_outputs)
                options = self._build_fund_options(
                    fee, fee_rate_override=fee_rate_override, replaceable=replaceable
                )
                funded = self.rpc.fundrawtransaction(tmp_raw, options)
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
                manual_outputs = self._format_outputs_for_rpc(manual_outputs)

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

    def build_custom_tx(
        self,
        outputs_payload: list[Dict[str, Any]] | Dict[str, Any],
        fee: float,
        inputs: List[Dict[str, Any]] | None = None,
        fee_rate_override: float | None = None,
        replaceable: bool | None = None,
    ) -> str:
        """Build and sign a transaction using preformatted outputs.

        Parameters
        ----------
        outputs_payload
            Output objects in the shape expected by ``createrawtransaction``. Entries
            should collapse to single-key dictionaries mapping addresses to amounts
            or OP_RETURN ``{"data": hex}`` payloads.
        fee
            Absolute fee target in DGB.
        inputs
            Optional explicit funding inputs. When omitted, the node is asked to
            fund the transaction via ``fundrawtransaction`` to maintain parity
            with the wallet's policy.
        """

        logger.info("Building custom transaction with %d output entries", len(outputs_payload))

        raw_tx: str | None = None
        formatted_outputs = self._format_outputs_for_rpc(outputs_payload)

        if inputs is not None:
            # IMPORTANT: For DigiByte/Bitcoin RPC, each outputs entry must be an object
            # with exactly one key, and that key must be a valid address string or
            # "data" (for OP_RETURN). Do not use "script" or other metadata keys here.
            raw_tx = self.rpc.createrawtransaction(inputs, formatted_outputs)
        else:
            try:
                # IMPORTANT: For DigiByte/Bitcoin RPC, each outputs entry must be an object
                # with exactly one key, and that key must be a valid address string or
                # "data" (for OP_RETURN). Do not use "script" or other metadata keys here.
                tmp_raw = self.rpc.createrawtransaction([], formatted_outputs)
                options = self._build_fund_options(
                    fee, fee_rate_override=fee_rate_override, replaceable=replaceable
                )
                funded = self.rpc.fundrawtransaction(tmp_raw, options)
                raw_tx = funded["hex"]
            except RPCError as exc:
                logger.error(
                    "Wallet could not fund the inscription transaction via fundrawtransaction: %s",
                    exc,
                    exc_info=logger.isEnabledFor(logging.DEBUG),
                )
                raise RuntimeError(
                    "Wallet could not fund the inscription transaction; add UTXOs, unlock the wallet, or specify --min-confirmations/inputs explicitly."
                ) from exc

        signed = self.rpc.signrawtransactionwithwallet(raw_tx)
        if not signed.get("complete"):
            raise RuntimeError("Node failed to produce a complete signature set for inscription")

        return signed["hex"]

    def send_payment_tx(
        self,
        outputs: Dict[str, float],
        fee: float,
        op_return_data: list[str] | None = None,
        inputs: List[Dict[str, Any]] | None = None,
        script_plane: ScriptPlane | None = None,
    ) -> str:
        """Build and broadcast a payment transaction, returning the txid."""

        raw_tx = self.build_payment_tx(
            outputs,
            fee,
            op_return_data=op_return_data,
            inputs=inputs,
            script_plane=script_plane,
        )
        txid = self.rpc.sendrawtransaction(raw_tx)
        logger.info("Broadcasted transaction %s", txid)
        return txid

    def send_multi_output_tx(
        self,
        to_address: str,
        amounts: list[float],
        fee: float,
        op_return_data: list[str] | None = None,
        script_plane: ScriptPlane | None = None,
    ) -> str:
        """Build and broadcast a single payment transaction with many outputs."""

        if not amounts:
            raise ValueError("At least one amount is required for multi-output transactions")

        extra_log: Dict[str, Any] = {}
        if script_plane is not None:
            extra_log["script_plane"] = script_plane.to_dict()
        logger.info(
            "Building single fan-out transaction for %d outputs", len(amounts), extra=extra_log or None
        )

        total_output = sum(float(amount) for amount in amounts)
        selected_utxos, change_amount = self.utxo_manager.select_utxos(total_output, fee)

        tx_inputs = [{"txid": utxo.txid, "vout": utxo.vout} for utxo in selected_utxos]
        aggregated_outputs: Dict[str, float] = {}
        for amount in amounts:
            aggregated_outputs[to_address] = round(
                aggregated_outputs.get(to_address, 0.0) + float(amount), 8
            )

        if change_amount > 1e-8:
            change_address = self.rpc.getnewaddress()
            aggregated_outputs[change_address] = round(change_amount, 8)

        outputs_payload = self._prepare_outputs_payload(
            aggregated_outputs, op_return_data
        )
        formatted_outputs = self._format_outputs_for_rpc(outputs_payload)

        raw_tx = self.rpc.createrawtransaction(tx_inputs, formatted_outputs)
        signed = self.rpc.signrawtransactionwithwallet(raw_tx)
        if not signed.get("complete"):
            raise RuntimeError("Node failed to produce a complete signature set")
        signed_hex = signed["hex"]

        total_in = sum(u.amount for u in selected_utxos)
        total_out = total_output + max(change_amount, 0)
        actual_fee = total_in - total_out
        if abs(actual_fee - fee) > 0.01:
            logger.warning(
                "Manual selection fee %.8f differs from requested %.8f", actual_fee, fee
            )

        txid = self.rpc.sendrawtransaction(signed_hex)
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
    def _format_outputs_for_rpc(
        outputs_payload: list[Dict[str, Any]] | Dict[str, Any]
    ) -> list[Dict[str, Any]]:
        """Return outputs formatted as an array of single-key objects for RPC."""

        if isinstance(outputs_payload, dict):
            return [{addr: amount} for addr, amount in outputs_payload.items()]

        formatted: list[Dict[str, Any]] = []
        for entry in outputs_payload:
            if len(entry) == 1:
                formatted.append(entry)
                continue

            if "address" in entry and "amount" in entry:
                formatted.append({entry["address"]: entry["amount"]})
                continue

            if "script" in entry:
                raise ValueError(
                    "Raw script outputs are not supported; provide a destination address instead"
                )

            raise ValueError(
                "Output entries must collapse to a single key for createrawtransaction"
            )

        return formatted

    @staticmethod
    def _estimate_fee_rate(fee: float, assumed_vbytes: int = 250) -> float:
        """Rudimentary conversion from absolute fee to feeRate (coin/kvB)."""

        kvb = assumed_vbytes / 1000
        if kvb == 0:
            kvb = 0.001
        return fee / kvb

    def _build_fund_options(
        self,
        fee: float,
        fee_rate_override: float | None = None,
        options: Dict[str, Any] | None = None,
        replaceable: bool | None = None,
    ) -> Dict[str, Any]:
        """Prepare fundrawtransaction-style options with a relay-safe feeRate."""

        options = dict(options or {})
        if fee_rate_override is not None:
            options["feeRate"] = fee_rate_override

        if "feeRate" not in options and "fee_rate" not in options:
            # Ensure inscriptions meet node relay policy:
            # DigiByte/Bitcoin RPC enforces a min relay fee; without an explicit feeRate
            # the default estimate can be below that threshold, causing
            # "min relay fee not met" errors. We choose a conservative default here.
            options["feeRate"] = max(
                self._estimate_fee_rate(fee), self.DEFAULT_RELAY_SAFE_FEE_RATE
            )

        if replaceable is not None:
            options.setdefault("replaceable", bool(replaceable))

        # Backward compatibility: accept sats/vbyte overrides by converting to coin/kvB
        if isinstance(options.get("feeRate"), (int, float)):
            # Some callers may pass sats/vbyte; detect likely magnitudes (>1.0)
            fee_rate_val = float(options["feeRate"])
            if fee_rate_val > 1.0:
                options["feeRate"] = sat_vb_to_dgb_per_kvb(fee_rate_val)

        return options
