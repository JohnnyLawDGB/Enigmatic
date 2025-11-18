import pytest

from enigmatic_dgb.script_plane import ScriptPlane, ScriptPlaneAggregation, parse_script_plane_block


def test_script_plane_roundtrip() -> None:
    plane = ScriptPlane(script_type="p2tr", taproot_mode="script_path", branch_id=2)
    assert plane.to_dict() == {
        "script_type": "p2tr",
        "taproot_mode": "script_path",
        "branch_id": 2,
        "aggregation": {"aggregation_mode": "none"},
    }


def test_parse_script_plane_block_validates_fields() -> None:
    mapping = {"script_type": "p2tr", "taproot_mode": "script_path", "branch_id": "5"}
    parsed = parse_script_plane_block(mapping, lambda msg: ValueError(msg))
    assert parsed.script_type == "p2tr"
    assert parsed.taproot_mode == "script_path"
    assert parsed.branch_id == 5
    assert parsed.aggregation.aggregation_mode == "none"


def test_parse_script_plane_block_rejects_missing_script_type() -> None:
    with pytest.raises(ValueError):
        parse_script_plane_block({}, lambda msg: ValueError(msg))


def test_parse_script_plane_with_aggregation() -> None:
    mapping = {
        "script_type": "p2tr",
        "aggregation": {
            "aggregation_mode": "musig2",
            "signer_set_id": "OPS",
            "threshold": 2,
            "total_signers": 3,
        },
    }
    plane = parse_script_plane_block(mapping, lambda msg: ValueError(msg))
    assert isinstance(plane.aggregation, ScriptPlaneAggregation)
    assert plane.aggregation.signer_set_id == "OPS"
    assert plane.aggregation.threshold == 2
    assert plane.aggregation.total_signers == 3
