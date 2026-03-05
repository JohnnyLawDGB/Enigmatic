import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from enigmatic_dgb.model import EncodingConfig
from enigmatic_dgb.watcher import Watcher


def _watcher_for_tests() -> Watcher:
    rpc = SimpleNamespace()
    return Watcher(rpc, ["dgb1watch"], EncodingConfig.enigmatic_default())


def _mock_rpc(listtx_entries=None, decoded_txs=None):
    """Build an RPC mock that supports listtransactions and getrawtransaction."""
    rpc = MagicMock()
    rpc.call.return_value = listtx_entries or []
    decoded_txs = decoded_txs or {}
    rpc.getrawtransaction.side_effect = lambda txid, verbose: decoded_txs.get(txid)
    return rpc


def test_extract_script_plane_key_path() -> None:
    watcher = _watcher_for_tests()
    decoded = {"vin": [{"txinwitness": ["ab" * 64]}]}
    plane = watcher._extract_script_plane(decoded)
    assert plane is not None
    assert plane.script_type == "p2tr"
    assert plane.taproot_mode == "key_path"
    assert plane.branch_id is None
    assert plane.aggregation.aggregation_mode == "none"


def test_extract_script_plane_script_path() -> None:
    watcher = _watcher_for_tests()
    script_hex = "51"
    decoded = {"vin": [{"txinwitness": ["aa", script_hex, "bb"]}]}
    plane = watcher._extract_script_plane(decoded)
    assert plane is not None
    assert plane.taproot_mode == "script_path"
    expected = hashlib.sha256(bytes.fromhex(script_hex)).digest()[0]
    assert plane.branch_id == expected


# --- Segwit address fallback tests ---


def test_fetch_legacy_address_matches_directly() -> None:
    """Legacy txs with populated address field are picked up without fallback."""
    rpc = _mock_rpc(
        listtx_entries=[
            {"address": "dgb1watch", "txid": "aaa", "amount": 1.0, "time": 1000000},
        ],
        decoded_txs={
            "aaa": {"vout": [], "vin": []},
        },
    )
    w = Watcher(rpc, ["dgb1watch"], EncodingConfig.enigmatic_default())
    txs = w._fetch_address_transactions("dgb1watch")
    assert len(txs) == 1
    assert txs[0].txid == "aaa"


def test_fetch_segwit_null_address_falls_back_to_scriptpubkey() -> None:
    """When address is None (segwit), the watcher falls back to getrawtransaction."""
    rpc = _mock_rpc(
        listtx_entries=[
            {"address": None, "txid": "bbb", "amount": 2.0, "time": 1000000},
        ],
        decoded_txs={
            "bbb": {
                "vout": [
                    {"scriptPubKey": {"address": "dgb1watch"}, "value": 2.0},
                ],
                "vin": [],
            },
        },
    )
    w = Watcher(rpc, ["dgb1watch"], EncodingConfig.enigmatic_default())
    txs = w._fetch_address_transactions("dgb1watch")
    assert len(txs) == 1
    assert txs[0].txid == "bbb"


def test_fetch_segwit_null_address_no_match_skipped() -> None:
    """When address is None and scriptPubKey doesn't match, tx is skipped."""
    rpc = _mock_rpc(
        listtx_entries=[
            {"address": None, "txid": "ccc", "amount": 3.0, "time": 1000000},
        ],
        decoded_txs={
            "ccc": {
                "vout": [
                    {"scriptPubKey": {"address": "dgb1other"}, "value": 3.0},
                ],
                "vin": [],
            },
        },
    )
    w = Watcher(rpc, ["dgb1watch"], EncodingConfig.enigmatic_default())
    txs = w._fetch_address_transactions("dgb1watch")
    assert len(txs) == 0


def test_fetch_segwit_uses_addresses_array_fallback() -> None:
    """Older DigiByte Core versions use 'addresses' array instead of 'address'."""
    rpc = _mock_rpc(
        listtx_entries=[
            {"address": None, "txid": "ddd", "amount": 4.0, "time": 1000000},
        ],
        decoded_txs={
            "ddd": {
                "vout": [
                    {"scriptPubKey": {"addresses": ["dgb1watch"]}, "value": 4.0},
                ],
                "vin": [],
            },
        },
    )
    w = Watcher(rpc, ["dgb1watch"], EncodingConfig.enigmatic_default())
    txs = w._fetch_address_transactions("dgb1watch")
    assert len(txs) == 1
    assert txs[0].txid == "ddd"


def test_fetch_different_address_not_picked_up() -> None:
    """Transactions with a populated address that doesn't match are still skipped."""
    rpc = _mock_rpc(
        listtx_entries=[
            {"address": "dgb1other", "txid": "eee", "amount": 5.0, "time": 1000000},
        ],
    )
    w = Watcher(rpc, ["dgb1watch"], EncodingConfig.enigmatic_default())
    txs = w._fetch_address_transactions("dgb1watch")
    assert len(txs) == 0
    # getrawtransaction should NOT be called — address was present but wrong.
    rpc.getrawtransaction.assert_not_called()
