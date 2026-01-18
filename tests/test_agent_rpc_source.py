from datetime import datetime, timezone

from enigmatic_dgb.agent.dgb_rpc_source import DigiByteWalletEventSource


class DummyRPC:
    def __init__(self, entries):
        self.entries = entries
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method != "listtransactions":
            raise AssertionError(f"Unexpected RPC method: {method}")
        return self.entries


def test_rpc_source_filters_and_dedupes() -> None:
    entries = [
        {
            "txid": "tx1",
            "category": "receive",
            "address": "addr1",
            "amount": 2.0,
            "time": 0,
        },
        {
            "txid": "tx2",
            "category": "send",
            "address": "addr2",
            "amount": -1.0,
            "time": 0,
        },
    ]
    source = DigiByteWalletEventSource(DummyRPC(entries), addresses=["addr1"])
    events = source.poll()
    assert len(events) == 1
    assert events[0].event_type == "incoming_transaction"
    assert events[0].payload["txid"] == "tx1"
    assert source.poll() == []


def test_rpc_source_uses_timestamp() -> None:
    entries = [
        {
            "txid": "tx1",
            "category": "receive",
            "address": "addr1",
            "amount": 2.0,
            "time": 10,
        }
    ]
    source = DigiByteWalletEventSource(DummyRPC(entries))
    events = source.poll()
    assert events[0].occurred_at == datetime.fromtimestamp(10, timezone.utc)
