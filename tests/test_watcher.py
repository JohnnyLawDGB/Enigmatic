import hashlib
from types import SimpleNamespace

from enigmatic_dgb.model import EncodingConfig
from enigmatic_dgb.watcher import Watcher


def _watcher_for_tests() -> Watcher:
    rpc = SimpleNamespace()
    return Watcher(rpc, ["dgb1watch"], EncodingConfig.enigmatic_default())


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
