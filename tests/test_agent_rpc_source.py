from datetime import datetime, timezone

from enigmatic_dgb.agent.dgb_rpc_source import DigiByteWalletEventSource


class DummyRPC:
    def __init__(self, entries, decoded_txs=None):
        self.entries = entries
        self.decoded_txs = decoded_txs or {}
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "listtransactions":
            return self.entries
        if method == "getrawtransaction":
            txid = params[0] if params else None
            return self.decoded_txs.get(txid)
        raise AssertionError(f"Unexpected RPC method: {method}")


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


# --- Segwit address fallback tests ---


def test_rpc_source_segwit_null_address_falls_back() -> None:
    """When address is None (segwit), falls back to getrawtransaction."""
    entries = [
        {"txid": "tx1", "category": "receive", "address": None, "amount": 2.0, "time": 0},
    ]
    decoded = {
        "tx1": {
            "vout": [{"scriptPubKey": {"address": "dgb1segwit"}, "value": 2.0}],
        },
    }
    source = DigiByteWalletEventSource(
        DummyRPC(entries, decoded), addresses=["dgb1segwit"]
    )
    events = source.poll()
    assert len(events) == 1
    assert events[0].payload["txid"] == "tx1"
    assert events[0].payload["address"] == "dgb1segwit"


def test_rpc_source_segwit_null_address_no_match_skipped() -> None:
    """When address is None and scriptPubKey doesn't match, tx is skipped."""
    entries = [
        {"txid": "tx1", "category": "receive", "address": None, "amount": 2.0, "time": 0},
    ]
    decoded = {
        "tx1": {
            "vout": [{"scriptPubKey": {"address": "dgb1other"}, "value": 2.0}],
        },
    }
    source = DigiByteWalletEventSource(
        DummyRPC(entries, decoded), addresses=["dgb1segwit"]
    )
    events = source.poll()
    assert len(events) == 0


def test_rpc_source_segwit_addresses_array_fallback() -> None:
    """Older DigiByte Core uses 'addresses' array in scriptPubKey."""
    entries = [
        {"txid": "tx1", "category": "receive", "address": None, "amount": 2.0, "time": 0},
    ]
    decoded = {
        "tx1": {
            "vout": [{"scriptPubKey": {"addresses": ["dgb1segwit"]}, "value": 2.0}],
        },
    }
    source = DigiByteWalletEventSource(
        DummyRPC(entries, decoded), addresses=["dgb1segwit"]
    )
    events = source.poll()
    assert len(events) == 1


def test_rpc_source_different_address_skipped_no_fallback() -> None:
    """When address field is present but wrong, no fallback RPC call is made."""
    entries = [
        {"txid": "tx1", "category": "receive", "address": "addr_other", "amount": 2.0, "time": 0},
    ]
    rpc = DummyRPC(entries)
    source = DigiByteWalletEventSource(rpc, addresses=["dgb1segwit"])
    events = source.poll()
    assert len(events) == 0
    # Only listtransactions should have been called, not getrawtransaction.
    assert all(m == "listtransactions" for m, _ in rpc.calls)
