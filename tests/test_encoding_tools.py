from decimal import Decimal

import pytest

from enigmatic_dgb.binary_packets import (
    BinaryEncodingError,
    decode_binary_packets_to_text,
    encode_text_to_binary_packets,
)
from enigmatic_dgb.dtsp import (
    DTSPEncodingError,
    decode_dtsp_sequence_to_message,
    encode_handshake_accept,
    encode_handshake_end,
    encode_handshake_start,
    encode_message_to_dtsp_sequence,
)


def test_dtsp_roundtrip_with_handshake():
    message = "Hello World"
    encoded = encode_message_to_dtsp_sequence(message)
    assert decode_dtsp_sequence_to_message(encoded) == message.upper()


def test_dtsp_accept_sequence_preserved_when_not_stripping_handshake():
    message = "HI"
    encoded = [
        encode_handshake_start(),
        encode_handshake_accept(),
        *encode_message_to_dtsp_sequence(message, include_start_end=False),
        encode_handshake_end(),
    ]
    decoded = decode_dtsp_sequence_to_message(encoded, require_start_end=False)
    assert decoded.startswith("startaccept")
    assert decoded.endswith("end")


def test_dtsp_rejects_unknown_characters():
    with pytest.raises(DTSPEncodingError):
        encode_message_to_dtsp_sequence("€")


def test_binary_packet_roundtrip():
    packets = encode_text_to_binary_packets("Hi", base_amount=Decimal("0"), bits_per_char=8)
    assert packets[0].bits == "01001000"
    assert packets[1].bits == "01101001"
    amounts = [packet.amount for packet in packets]
    assert amounts == [Decimal("0.01001000"), Decimal("0.01101001")]
    decoded = decode_binary_packets_to_text(amounts, base_amount=Decimal("0"), bits_per_char=8)
    assert decoded == "Hi"


def test_binary_packet_rejects_invalid_digit_sequences():
    with pytest.raises(BinaryEncodingError):
        decode_binary_packets_to_text([Decimal("0.12340000")], base_amount=Decimal("0"))
