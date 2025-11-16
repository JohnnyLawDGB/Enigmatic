"""Watcher service polling DigiByte nodes and decoding Enigmatic traffic."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Sequence, Set

from .decoder import EnigmaticDecoder, ObservedTx, group_into_packets
from .model import EncodingConfig, EnigmaticMessage
from .rpc_client import DigiByteRPC

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
                )
            )
        return observed
