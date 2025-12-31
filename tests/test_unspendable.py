import pytest

from enigmatic_dgb.unspendable import decode_address, generate_address


def test_generate_address_matches_reference_vector():
    # Example taken from the upstream unspendable tool.
    address = generate_address("DCx", 'a,b,c.')
    assert address == "DCxAhBhCvzzzzzzzzzzzzzzzzzzzYsQKEw"


def test_generate_address_rejects_invalid_prefix():
    with pytest.raises(ValueError):
        generate_address("$", "abc")


def test_generate_address_rejects_invalid_body_characters():
    with pytest.raises(ValueError):
        generate_address("DCx", "abc#")


def test_decode_address_round_trip_payload():
    address = generate_address("DCx", "Hello.")
    payload = decode_address(address, "DCx")
    assert isinstance(payload, bytes)
    assert len(payload) > 0
