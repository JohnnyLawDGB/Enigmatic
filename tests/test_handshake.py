"""Unit tests for the X25519-based handshake helper module."""

from datetime import datetime, timezone

import pytest

from enigmatic_dgb.handshake import (
    HandshakeParameters,
    HandshakePhase,
    build_handshake_payload,
    create_initiator_state,
    create_responder_state,
    initiator_process_resp,
    parse_handshake_payload,
    responder_process_init_and_build_resp,
)


def test_handshake_round_trip_session_keys_match() -> None:
    initiator_state = create_initiator_state(channel="alpha", dialect="intel")
    init_payload = build_handshake_payload(initiator_state)

    params = HandshakeParameters(
        session_id=initiator_state.params.session_id,
        channel=initiator_state.params.channel,
        dialect=initiator_state.params.dialect,
        created_at=initiator_state.params.created_at,
    )
    responder_state = create_responder_state(params)
    resp_payload = responder_process_init_and_build_resp(responder_state, init_payload)

    initiator_process_resp(initiator_state, resp_payload)

    assert initiator_state.phase is HandshakePhase.COMPLETE
    assert responder_state.phase is HandshakePhase.COMPLETE
    assert initiator_state.shared_secret is not None
    assert responder_state.shared_secret is not None
    assert initiator_state.session_key is not None
    assert responder_state.session_key is not None
    assert initiator_state.session_key == responder_state.session_key


def test_parse_handshake_payload_validation() -> None:
    initiator_state = create_initiator_state(channel="beta", dialect="real")
    payload = build_handshake_payload(initiator_state)

    parsed = parse_handshake_payload(payload)
    assert parsed["phase"] is HandshakePhase.INIT

    malformed = {
        "type": "handshake",
        "version": 999,
        "session_id": payload["session_id"],
        "phase": "INIT",
        "dialect": "real",
        "channel": "beta",
        "public_key": payload["public_key"],
    }

    with pytest.raises(ValueError):
        parse_handshake_payload(malformed)


def test_responder_rejects_mismatched_session() -> None:
    initiator_state = create_initiator_state(channel="gamma", dialect="intel")
    init_payload = build_handshake_payload(initiator_state)
    params = HandshakeParameters(
        session_id="different-session",
        channel=initiator_state.params.channel,
        dialect=initiator_state.params.dialect,
        created_at=datetime.now(timezone.utc),
    )
    responder_state = create_responder_state(params)

    with pytest.raises(ValueError):
        responder_process_init_and_build_resp(responder_state, init_payload)

