import pytest

from enigmatic_dgb.unspendable import (
    _normalize_body,
    _prefix_to_version,
    base58_decode,
    decode_address,
    generate_address,
)


def test_generate_address_matches_readme_example():
    address = generate_address("DCx", "THiSxiSxTHExSTUFF")
    assert address == "DCxTHiSxiSxTHExSTUFFzzzzzzzzbSG1oo"


def test_generate_address_supports_alternate_prefixes():
    name_address = generate_address("DAx", "DAViDxBoWiE")
    transport_address = generate_address("DBx", "YoUTUBEvCoM")

    assert name_address == "DAxDAViDxBoWiEzzzzzzzzzzzzzzZuzmZS"
    assert transport_address == "DBxYoUTUBEvCoMzzzzzzzzzzzzzzZ31xMU"


@pytest.mark.parametrize("prefix", ["DC", "DCxx", "DFx"])
def test_generate_address_rejects_invalid_prefix_shapes(prefix: str):
    with pytest.raises(ValueError):
        generate_address(prefix, "abc")


def test_generate_address_pads_long_messages_to_base_length():
    long_message = "x" * 26
    address = generate_address("DCx", long_message)

    expected_body = (f"DCx{_normalize_body(long_message)}").ljust(28, "z").ljust(34, "X")
    expected_payload = base58_decode(expected_body, _prefix_to_version("DCx"))

    assert decode_address(address, "DCx") == expected_payload
