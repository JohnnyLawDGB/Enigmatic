"""Simple substitution cipher for the DigiByte Transaction Signaling Protocol (DTSP)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class DTSPSymbol:
    """Represents a single DTSP substitution mapping."""

    symbol: str
    amount: Decimal


class DTSPEncodingError(ValueError):
    """Raised when DTSP encoding or decoding fails."""


_ALPHABET_MAPPING: Dict[str, str] = {
    **{chr(ord("A") + i): f"0.000226{59 + i:02d}" for i in range(26)},
    **{str(i): f"0.000226{48 + i:02d}" for i in range(10)},
    " ": "0.00022688",
    ".": "0.00022689",
    ",": "0.00022690",
    "!": "0.00022691",
    "?": "0.00022692",
    ":": "0.00022693",
    "=": "0.00022694",
    "+": "0.00022695",
    "-": "0.00022696",
    "*": "0.00022697",
    "/": "0.00022698",
    "_": "0.00022699",
}

_HANDSHAKE_MAPPING: Dict[str, str] = {
    "start": "0.00022611",
    "accept": "0.00022631",
    "end": "0.00022621",
}

QUANTIZER = Decimal("0.00000001")

SYMBOL_TABLE: Dict[str, DTSPSymbol] = {
    key: DTSPSymbol(symbol=key, amount=Decimal(value))
    for key, value in {**_ALPHABET_MAPPING, **_HANDSHAKE_MAPPING}.items()
}

REVERSE_SYMBOL_TABLE: Dict[Decimal, str] = {
    entry.amount.quantize(QUANTIZER, rounding=ROUND_DOWN): entry.symbol
    for entry in SYMBOL_TABLE.values()
}

HANDSHAKE_SYMBOLS = set(_HANDSHAKE_MAPPING)


def encode_dtsp_message(
    message: str, *, include_handshake: bool = False, include_accept: bool = False
) -> List[Decimal]:
    """Encode a message using the DTSP substitution table.

    Lowercase letters are normalized to uppercase. When ``include_handshake`` is
    ``True``, the encoded sequence is wrapped with ``start`` and ``end`` codes.
    ``include_accept`` can be set alongside ``include_handshake`` to insert the
    ``accept`` code after ``start`` for interactive exchanges.
    """

    encoded: List[Decimal] = []

    if include_handshake:
        encoded.append(SYMBOL_TABLE["start"].amount)
        if include_accept:
            encoded.append(SYMBOL_TABLE["accept"].amount)

    for char in message:
        normalized = char.upper() if char.isalpha() else char
        symbol = SYMBOL_TABLE.get(normalized)
        if symbol is None:
            raise DTSPEncodingError(f"unsupported character for DTSP: {char!r}")
        encoded.append(symbol.amount)

    if include_handshake:
        encoded.append(SYMBOL_TABLE["end"].amount)

    return encoded


def decode_dtsp_amounts(
    amounts: Sequence[Decimal], *, strip_handshake: bool = True
) -> str:
    """Decode DTSP amounts back into a message string.

    Handshake codes are skipped when ``strip_handshake`` is enabled (default).
    Unknown values result in :class:`DTSPEncodingError`.
    """

    decoded: List[str] = []

    for raw_amount in amounts:
        amount = raw_amount.quantize(QUANTIZER, rounding=ROUND_DOWN)
        symbol = REVERSE_SYMBOL_TABLE.get(amount)
        if symbol is None:
            raise DTSPEncodingError(f"unrecognized DTSP amount: {raw_amount}")
        if strip_handshake and symbol in HANDSHAKE_SYMBOLS:
            continue
        decoded.append(symbol)

    return "".join(decoded)


def format_dtsp_table() -> str:
    """Return a human-readable table of DTSP symbol mappings."""

    lines = ["symbol | amount"]
    for key in sorted(SYMBOL_TABLE):
        lines.append(f"{key} | {SYMBOL_TABLE[key].amount}")
    return "\n".join(lines)
