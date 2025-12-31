"""Helpers for generating intentionally unspendable addresses.

The helpers in this module are derived from the upstream
`JohnnyLawDGB/unspendable` project and preserve its Base58 and DiMECASH
mapping conventions. The main entry point, :func:`generate_address`, embeds a
message inside an address-like string. These addresses are *intentionally
unspendable* and must never be used to store actual funds.
"""

from __future__ import annotations

import binascii
import hashlib
from typing import List

# DiMECASH/Base58 mapping from the upstream tool.
b58_digits = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
b58_dcmap = '123456789abcdefghjklmnpqrstuvwxyz!)0(=/\\,i;?"_o}{@+|*.: -~'

# Seed values used to derive the version byte from the first prefix character.
seeds = [
    0,
    3,
    5,
    7,
    10,
    12,
    15,
    17,
    20,
    22,
    25,
    27,
    30,
    32,
    35,
    37,
    40,
    42,
    45,
    48,
    50,
    53,
    55,
    58,
    60,
    63,
    65,
    68,
    70,
    73,
    76,
    78,
    80,
    83,
    85,
    88,
    91,
    93,
    96,
    98,
    101,
    103,
    106,
    108,
    111,
    113,
    116,
    118,
    121,
    123,
    126,
    128,
    131,
    134,
    136,
    139,
    141,
    144,
]

# Special-case prefixes used by the upstream Dogecoin flow.
_DOGE_FAVORITE_PREFIXES = {f"9{char}" for char in "stuvwxyz"}


def _double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def base58_check_encode(payload: bytes, version: bytes) -> str:
    """Encode bytes into a Base58Check string with the provided version byte."""
    data = version + payload
    checksum = _double_sha256(data)[:4]
    address_bytes = data + checksum

    value = int("0x0" + binascii.hexlify(address_bytes).decode("utf8"), 16)

    output: List[str] = []
    while value > 0:
        value, remainder = divmod(value, 58)
        output.append(b58_digits[remainder])
    encoded = "".join(output[::-1])

    leading_zero_count = 0
    for byte in data:
        if byte == 0:
            leading_zero_count += 1
        else:
            break

    return b58_digits[0] * leading_zero_count + encoded


def base58_decode(value: str, version: bytes) -> bytes:
    """Decode a Base58Check string and return the payload bytes.

    The checksum is stripped during decoding to mirror the behavior of the
    upstream implementation.
    """
    number = 0
    for character in value:
        number *= 58
        if character not in b58_digits:
            raise ValueError(f"Invalid Base58 character: {character}")
        number += b58_digits.index(character)

    hex_value = f"{number:x}"
    if len(hex_value) % 2:
        hex_value = "0" + hex_value
    decoded = binascii.unhexlify(hex_value.encode("utf8"))

    padding = 0
    for character in value[:-1]:
        if character == b58_digits[0]:
            padding += 1
        else:
            break
    k = version * padding + decoded

    _, payload, _ = k[0:1], k[1:-4], k[-4:]
    return payload


def _normalize_body(body: str) -> str:
    """Normalize the message body using the DiMECASH mapping."""
    normalized: List[str] = []
    for character in body:
        mapping_index = b58_dcmap.find(character)
        if mapping_index != -1:
            normalized.append(b58_digits[mapping_index])
            continue

        if character == "I":
            normalized.append("i")
            continue
        if character == "O":
            normalized.append("o")
            continue
        if character == "'":
            normalized.append("y")
            continue

        if character in b58_digits:
            normalized.append(character)
            continue

        raise ValueError(f"Unsupported body character: {character}")

    if not normalized:
        raise ValueError("Body must not be empty.")

    return "".join(normalized)


def _prefix_to_version(prefix: str) -> bytes:
    if not prefix:
        raise ValueError("Prefix must not be empty.")
    if any(character not in b58_digits for character in prefix):
        raise ValueError("Prefix must contain only Base58 characters.")

    first_char = prefix[0]
    try:
        prefix_char_seed = seeds[b58_digits.index(first_char)]
    except IndexError as exc:
        raise ValueError(f"No seed available for prefix character '{first_char}'.") from exc

    prefix_bytes = prefix_char_seed.to_bytes(1, "big")
    if prefix in _DOGE_FAVORITE_PREFIXES:
        prefix_bytes = b"\x16"

    return prefix_bytes


def generate_address(prefix: str, body: str) -> str:
    """Generate an unspendable address using the DiMECASH/Base58 mapping.

    The prefix selects the currency/category and determines the version byte
    through the ``seeds`` lookup, while the body is encoded using the
    ``b58_digits`` alphabet with additional DiMECASH characters from
    ``b58_dcmap``. The resulting string is padded and encoded with a Base58Check
    checksum. Addresses produced by this function are intentionally
    unspendable; do not use them to store funds.
    """
    prefix_bytes = _prefix_to_version(prefix)
    normalized_body = _normalize_body(body)

    prefixed_body = prefix + normalized_body
    padded_prefixed_body = prefixed_body.ljust(28, "z").ljust(34, "X")

    decoded_address = base58_decode(padded_prefixed_body, prefix_bytes)
    address = base58_check_encode(decoded_address, prefix_bytes)

    if base58_decode(address, prefix_bytes) != decoded_address:
        raise ValueError("Generated address failed checksum validation.")

    return address


def decode_address(address: str, prefix: str) -> bytes:
    """Decode an address generated by :func:`generate_address`.

    This helper mirrors the upstream behavior and returns the payload bytes
    without verifying or returning the checksum.
    """
    prefix_bytes = _prefix_to_version(prefix)
    return base58_decode(address, prefix_bytes)
