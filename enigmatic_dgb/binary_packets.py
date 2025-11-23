"""Utilities for encoding text as binary decimal UTXO packet amounts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Iterable, List, Sequence


@dataclass
class BinaryUTXOPacket:
    """Represents a single binary-encoded character carried by a UTXO output."""

    letter: str
    bits: str
    amount: Decimal


class BinaryEncodingError(ValueError):
    """Raised when binary encoding or decoding fails."""


def _build_quantizer(bits_per_char: int) -> Decimal:
    if bits_per_char <= 0:
        raise BinaryEncodingError("bits_per_char must be positive")
    return Decimal(f"1e-{bits_per_char}")


def encode_text_to_binary_packets(
    text: str, *, base_amount: Decimal = Decimal("0.0001"), bits_per_char: int = 8
) -> List[BinaryUTXOPacket]:
    """Convert text into binary UTXO packets with decimal-place bitstrings.

    Each character is encoded as its ASCII integer value represented by a binary
    string of ``bits_per_char`` length. The binary digits are placed directly
    after the decimal point of the output amount, offset by ``base_amount``.
    """

    quantizer = _build_quantizer(bits_per_char)
    packets: List[BinaryUTXOPacket] = []

    for letter in text:
        codepoint = ord(letter)
        if codepoint >= 2 ** bits_per_char:
            raise BinaryEncodingError(
                f"letter '{letter}' cannot be represented with {bits_per_char} bits"
            )
        bits = format(codepoint, f"0{bits_per_char}b")
        fractional = Decimal(f"0.{bits}")
        amount = (base_amount + fractional).quantize(quantizer, rounding=ROUND_DOWN)
        packets.append(BinaryUTXOPacket(letter=letter, bits=bits, amount=amount))

    return packets


def decode_binary_packets_to_text(
    amounts: Sequence[Decimal], *, base_amount: Decimal = Decimal("0.0001"), bits_per_char: int = 8
) -> str:
    """Decode binary UTXO packet amounts back into text.

    The decoder strips ``base_amount`` before reading the binary fraction. It
    expects exactly ``bits_per_char`` decimal digits and ensures all digits are
    binary (``0`` or ``1``)."""

    quantizer = _build_quantizer(bits_per_char)
    letters: List[str] = []

    for amount in amounts:
        normalized = (amount - base_amount).quantize(quantizer, rounding=ROUND_DOWN)
        digits = f"{normalized:.{bits_per_char}f}".split(".")[1][:bits_per_char]
        if len(digits) != bits_per_char:
            raise BinaryEncodingError(
                f"amount {amount} does not contain {bits_per_char} decimal digits"
            )
        if any(d not in {"0", "1"} for d in digits):
            raise BinaryEncodingError(
                f"amount {amount} contains non-binary decimal digits: {digits}"
            )
        codepoint = int(digits, 2)
        letters.append(chr(codepoint))

    return "".join(letters)


def format_packets_human_readable(packets: Iterable[BinaryUTXOPacket]) -> str:
    """Render a summary of packets showing letter, bits, and amount."""

    lines = ["letter | bits | amount"]
    for packet in packets:
        lines.append(f"{packet.letter} | {packet.bits} | {packet.amount}")
    return "\n".join(lines)
