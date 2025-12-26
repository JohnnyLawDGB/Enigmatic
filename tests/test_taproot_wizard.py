import pytest
from requests import Response

from enigmatic_dgb.ordinals.workflows import (
    compute_taproot_envelope_stats,
    suggest_max_fee_sats,
)
from enigmatic_dgb.rpc_client import DigiByteRPCClient, RPCConfig, RPCTransportError


def test_taproot_payload_size_gate():
    payload = b"a" * 600  # exceeds single-element push once wrapped
    with pytest.raises(ValueError):
        compute_taproot_envelope_stats(payload, "text/plain")


def test_fee_cap_recommendation():
    # 10500 sat/vB * 154 vB ≈ 1,617,000 sats → suggest 2,000,000
    assert suggest_max_fee_sats(1_617_000) == 2_000_000


def test_rpc_auth_error_maps_to_hint():
    config = RPCConfig.from_sources(user="user", password="pass")
    client = DigiByteRPCClient(config)
    resp = Response()
    resp.status_code = 401
    resp._content = b"{}"
    resp.url = "http://127.0.0.1:14022"
    with pytest.raises(RPCTransportError) as excinfo:
        client._raise_for_status(resp)
    assert "Unauthorized" in str(excinfo.value)
    assert excinfo.value.status_code == 401
