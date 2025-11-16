"""Watcher service polling a DigiByte node and decoding Enigmatic packets."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable, List, Set

from .decoder import EnigmaticDecoder, ObservedTx, group_into_packets
from .model import EncodingConfig, EnigmaticMessage
from .rpc_client import DigiByteRPC

logger = logging.getLogger(__name__)


class Watcher:
    """Poll for address activity and decode packets as they arrive."""

    def __init__(
        self,
        rpc: DigiByteRPC,
        address: str,
        config: EncodingConfig,
        poll_interval_seconds: int = 30,
    ) -> None:
        self.rpc = rpc
        self.address = address
        self.config = config
        self.poll_interval_seconds = poll_interval_seconds
        self.decoder = EnigmaticDecoder(config)
        self._seen_txids: Set[str] = set()

    def poll_once(self) -> List[EnigmaticMessage]:
        """Poll the node for transactions touching the watched address."""

        txs = self._fetch_address_transactions()
        new_txs = [tx for tx in txs if tx.txid not in self._seen_txids]
        for tx in new_txs:
            self._seen_txids.add(tx.txid)
        if not new_txs:
            return []

        packets = group_into_packets(new_txs, self.config)
        messages = [self.decoder.decode_packet(packet, self.address) for packet in packets]
        return messages

    def run_forever(self, callback: Callable[[EnigmaticMessage], None]) -> None:
        """Continuously poll and emit decoded messages via callback."""

        logger.info("Starting watcher for %s", self.address)
        while True:
            try:
                for message in self.poll_once():
                    callback(message)
            except Exception as exc:  # pragma: no cover - best effort logging
                logger.exception("Watcher error: %s", exc)
            time.sleep(self.poll_interval_seconds)

    def _fetch_address_transactions(self) -> List[ObservedTx]:
        """Fetch recent transactions for the address.

        DigiByte Core does not provide an out-of-the-box address index. This method
        uses ``listtransactions`` as a reasonable default, but integrators can
        replace it with a custom indexer by subclassing ``Watcher``.
        """

        raw = self.rpc.call("listtransactions", ["*", 1000, 0, True])
        observed: List[ObservedTx] = []
        for entry in raw:
            if entry.get("address") != self.address:
                continue
            txid = entry.get("txid")
            if not txid:
                continue
            amount = float(entry.get("amount", 0.0))
            timestamp = datetime.utcfromtimestamp(entry.get("time", int(time.time())))
            fee = float(entry.get("fee", 0.0)) if "fee" in entry else None
            observed.append(
                ObservedTx(
                    txid=txid,
                    timestamp=timestamp,
                    amount=abs(amount),
                    fee=abs(fee) if fee is not None else None,
                )
            )
        return observed
