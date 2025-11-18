"""Watcher service polling DigiByte nodes and decoding Enigmatic traffic."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Sequence, Set

from .decoder import EnigmaticDecoder, ObservedTx, group_into_packets
from .model import EncodingConfig, EnigmaticMessage
from .rpc_client import DigiByteRPC
from .script_plane import ScriptPlane

logger = logging.getLogger(__name__)


class Watcher:
    """Observe on-chain activity and decode Enigmatic messages as they appear."""

    def __init__(
        self,
        rpc: DigiByteRPC,
        addresses: Sequence[str],
        config: EncodingConfig,
        poll_interval_seconds: int = 30,
    ) -> None:
        if not addresses:
            raise ValueError("Watcher requires at least one address to observe")

        self.rpc = rpc
        self.addresses: List[str] = list(addresses)
        self.config = config
        self.poll_interval_seconds = poll_interval_seconds
        self.decoder = EnigmaticDecoder(config)
        self._seen_txids: Dict[str, Set[str]] = {addr: set() for addr in self.addresses}

    def poll_once(self) -> List[EnigmaticMessage]:
        """Poll the node for transactions touching the watched addresses."""

        messages: List[EnigmaticMessage] = []
        for address in self.addresses:
            try:
                observed = self._fetch_address_transactions(address)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to fetch transactions for address %s", address)
                continue

            new_txs = self._filter_new_transactions(address, observed)
            if not new_txs:
                continue

            packets = group_into_packets(new_txs, self.config)
            for packet in packets:
                try:
                    message = self.decoder.decode_packet(packet, address)
                except Exception:  # pragma: no cover - decoding errors should not stop loop
                    logger.exception("Failed to decode packet for %s", address)
                    continue
                messages.append(message)
        return messages

    def run_forever(self, callback: Callable[[EnigmaticMessage], None]) -> None:
        """Continuously poll and emit decoded messages via callback."""

        logger.info("Starting watcher for %d addresses", len(self.addresses))
        while True:
            try:
                for message in self.poll_once():
                    callback(message)
            except Exception:  # pragma: no cover - best effort logging
                logger.exception("Watcher loop encountered an error")
            time.sleep(self.poll_interval_seconds)

    def _filter_new_transactions(
        self, address: str, observed: Iterable[ObservedTx]
    ) -> List[ObservedTx]:
        """Return only transactions we have not processed yet for ``address``."""

        seen = self._seen_txids.setdefault(address, set())
        new_txs: List[ObservedTx] = []
        for tx in observed:
            if tx.txid in seen:
                continue
            seen.add(tx.txid)
            new_txs.append(tx)
        return new_txs

    def _fetch_address_transactions(self, address: str) -> List[ObservedTx]:
        """Fetch recent transactions for ``address``.

        DigiByte Core does not provide an out-of-the-box address index.  Integrators
        may want to provide a custom address indexer or cache in production.  This
        implementation uses ``listtransactions`` and filters results as a
        placeholder.
        """

        params = ["*", 1000, 0, True]
        raw = self.rpc.call("listtransactions", params)
        observed: List[ObservedTx] = []
        for entry in raw:
            if entry.get("address") != address:
                continue
            txid = entry.get("txid")
            if not txid:
                continue
            timestamp = entry.get("time")
            if timestamp is None:
                # TODO: use block timestamp from gettransaction if available.
                timestamp = int(time.time())
            decoded_tx = self._get_decoded_transaction(str(txid))
            op_return = self._extract_op_return_from_decoded(decoded_tx)
            script_plane = self._extract_script_plane(decoded_tx)
            observed.append(
                ObservedTx(
                    txid=str(txid),
                    timestamp=datetime.utcfromtimestamp(int(timestamp)),
                    amount=abs(float(entry.get("amount", 0.0))),
                    fee=(
                        abs(float(entry.get("fee")))
                        if entry.get("fee") is not None
                        else None
                    ),
                    op_return_data=op_return,
                    script_plane=script_plane,
                )
            )
        return observed

    def _get_decoded_transaction(self, txid: str) -> dict | None:
        try:
            decoded = self.rpc.getrawtransaction(txid, True)
        except Exception:  # pragma: no cover - RPC issues surfaced at call site
            logger.debug("Failed to decode transaction %s", txid)
            return None
        if not isinstance(decoded, dict):
            return None
        return decoded

    def _extract_op_return_from_decoded(self, decoded: dict | None) -> bytes | None:
        if not decoded:
            return None
        for vout in decoded.get("vout", []) or []:
            script = vout.get("scriptPubKey") or {}
            if script.get("type") != "nulldata":
                continue
            asm = script.get("asm")
            data_hex: str | None = None
            if isinstance(asm, str):
                parts = asm.split(" ", 1)
                if len(parts) == 2:
                    data_hex = parts[1]
            if not data_hex:
                maybe_hex = script.get("hex")
                if isinstance(maybe_hex, str) and maybe_hex.startswith("6a"):
                    data_hex = maybe_hex[2:]
            if not data_hex:
                continue
            try:
                return bytes.fromhex(data_hex)
            except ValueError:  # pragma: no cover - malformed script
                continue
        return None

    def _extract_script_plane(self, decoded: dict | None) -> ScriptPlane | None:
        if not decoded:
            return None
        vins = decoded.get("vin") or []
        for vin in vins:
            witness = vin.get("txinwitness") or []
            if not witness:
                continue
            if len(witness) == 1:
                return ScriptPlane(script_type="p2tr", taproot_mode="key_path")
            script_hex: str | None = None
            if len(witness) >= 2:
                script_hex = witness[-2]
            branch_id = None
            if script_hex:
                branch_id = self._branch_id_from_script(script_hex)
            return ScriptPlane(
                script_type="p2tr",
                taproot_mode="script_path",
                branch_id=branch_id,
            )
        return None

    @staticmethod
    def _branch_id_from_script(script_hex: str) -> int:
        try:
            script_bytes = bytes.fromhex(script_hex)
        except ValueError:  # pragma: no cover - malformed witness data
            return 0
        digest = hashlib.sha256(script_bytes).digest()
        return digest[0]
