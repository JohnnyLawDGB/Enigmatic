"""DigiByte RPC event source adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Sequence

from .events import AgentEvent
from .monitor import EventSource
from ..rpc_client import DigiByteRPC


def _normalize_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromtimestamp(int(value), timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _build_event_id(entry: dict[str, Any]) -> str:
    txid = str(entry.get("txid", "unknown"))
    category = str(entry.get("category", "transaction"))
    address = str(entry.get("address") or "")
    vout = str(entry.get("vout") or "")
    amount = str(entry.get("amount") or "")
    return ":".join([txid, category, address, vout, amount])


def _entry_to_event(entry: dict[str, Any]) -> AgentEvent:
    category = str(entry.get("category", "transaction"))
    event_type = {
        "receive": "incoming_transaction",
        "send": "outgoing_transaction",
    }.get(category, "transaction")
    payload = {
        "txid": entry.get("txid"),
        "category": category,
        "address": entry.get("address"),
        "amount": entry.get("amount"),
        "confirmations": entry.get("confirmations"),
        "vout": entry.get("vout"),
        "label": entry.get("label"),
        "fee": entry.get("fee"),
    }
    return AgentEvent.create(
        event_type=event_type,
        source="digibyte_rpc",
        payload=payload,
        occurred_at=_normalize_timestamp(
            entry.get("time") or entry.get("timereceived") or entry.get("blocktime")
        ),
        event_id=_build_event_id(entry),
        tags=[category],
    )


@dataclass
class DigiByteWalletEventSource(EventSource):
    rpc: DigiByteRPC
    addresses: Sequence[str] | None = None
    max_count: int = 1000
    include_watchonly: bool = True

    def __post_init__(self) -> None:
        self._seen_ids: set[str] = set()
        self._address_set = set(self.addresses or [])

    def _tx_touches_any_watched(self, txid: str) -> str | None:
        """Return the first watched address found in ``txid`` outputs, or None.

        Fallback for when ``listtransactions`` omits the ``address`` field
        (common with segwit/bech32 outputs).
        """
        try:
            decoded = self.rpc.call("getrawtransaction", [txid, 1])
        except Exception:
            return None
        if not isinstance(decoded, dict):
            return None
        for vout in decoded.get("vout", []) or []:
            spk = vout.get("scriptPubKey") or {}
            addr = spk.get("address")
            if addr and addr in self._address_set:
                return addr
            for a in spk.get("addresses") or []:
                if a in self._address_set:
                    return a
        return None

    def poll(self) -> List[AgentEvent]:
        entries = self.rpc.call(
            "listtransactions",
            ["*", int(self.max_count), 0, bool(self.include_watchonly)],
        )
        events: List[AgentEvent] = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            address = entry.get("address")
            if self._address_set and address not in self._address_set:
                # Address field present but not watched — skip.
                if address is not None:
                    continue
                # Address field missing (segwit) — fall back to scriptPubKey.
                txid = entry.get("txid")
                resolved = self._tx_touches_any_watched(str(txid)) if txid else None
                if not resolved:
                    continue
                # Patch the entry so downstream consumers see the address.
                entry = {**entry, "address": resolved}
            if not entry.get("txid"):
                continue
            event_id = _build_event_id(entry)
            if event_id in self._seen_ids:
                continue
            self._seen_ids.add(event_id)
            events.append(_entry_to_event(entry))
        return events

    def prime_seen(self, entries: Iterable[dict[str, Any]]) -> None:
        for entry in entries:
            self._seen_ids.add(_build_event_id(entry))
