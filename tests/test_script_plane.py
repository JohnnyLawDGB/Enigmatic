import pytest

from enigmatic_dgb.script_plane import ScriptPlane, parse_script_plane_block


def test_script_plane_roundtrip() -> None:
    plane = ScriptPlane(script_type="p2tr", taproot_mode="script_path", branch_id=2)
    assert plane.to_dict() == {
        "script_type": "p2tr",
        "taproot_mode": "script_path",
        "branch_id": 2,
    }


def test_parse_script_plane_block_validates_fields() -> None:
    mapping = {"script_type": "p2tr", "taproot_mode": "script_path", "branch_id": "5"}
    parsed = parse_script_plane_block(mapping, lambda msg: ValueError(msg))
    assert parsed.script_type == "p2tr"
    assert parsed.taproot_mode == "script_path"
    assert parsed.branch_id == 5


def test_parse_script_plane_block_rejects_missing_script_type() -> None:
    with pytest.raises(ValueError):
        parse_script_plane_block({}, lambda msg: ValueError(msg))
