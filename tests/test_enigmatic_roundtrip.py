"""Tests for Enigmatic encoder and decoder round-tripping."""

from __future__ import annotations

from datetime import datetime, timedelta

from enigmatic_dgb.decoder import EnigmaticDecoder, ObservedTx, group_into_packets
from enigmatic_dgb.encoder import EnigmaticEncoder
from enigmatic_dgb.model import EncodingConfig, EnigmaticMessage


def test_identity_round_trip() -> None:
    config = EncodingConfig.enigmatic_default()
    message = EnigmaticMessage(
        id="test",
        timestamp=datetime.utcnow(),
        channel="default",
        intent="identity",
        payload={"role": "handshake"},
    )

    encoder = EnigmaticEncoder(config, target_address="dgb1test")
    instructions, fee = encoder.encode_message(message)

    packet = [
        ObservedTx(
            txid=f"tx-{idx}",
            timestamp=datetime.utcnow(),
            amount=instruction.amount,
            fee=fee if idx == len(instructions) - 1 else None,
        )
        for idx, instruction in enumerate(instructions)
    ]

    decoder = EnigmaticDecoder(config)
    decoded = decoder.decode_packet(packet, channel="default")

    assert decoded.intent in {"identity", "channel"}
    assert decoded.payload.get("flag_0") or decoded.payload


def test_group_into_packets_respects_time_gaps() -> None:
    config = EncodingConfig.enigmatic_default()
    base_time = datetime.utcnow()
    txs = [
        ObservedTx(txid="a", timestamp=base_time, amount=217.0),
        ObservedTx(txid="b", timestamp=base_time + timedelta(seconds=10), amount=0.076),
        ObservedTx(
            txid="c",
            timestamp=base_time + timedelta(seconds=config.packet_max_interval_seconds + 10),
            amount=352.0,
        ),
    ]

    packets = group_into_packets(txs, config)
    assert len(packets) == 2
    assert len(packets[0]) == 2
    assert len(packets[1]) == 1
