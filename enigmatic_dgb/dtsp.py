"""DigiByte Transaction Signaling Protocol (DTSP) helpers.

This module hardcodes the DTSP alphabet documented in the repository's
"DigiByte Transaction Signaling Protocol (DTSP)" specification. DTSP encodes
upper-case letters, digits, punctuation, and handshake control codes as precise
transaction values. The design is intentionally static: mappings are constants,
with a small comparison tolerance used when reading values back from the chain.

By default Enigmatic assumes DTSP symbols are carried on the fee plane, but the
helpers are pure and can be reused for amount-plane encodings as well.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

# Core tolerance for floating-point comparisons when matching DTSP codes.
DTSP_TOLERANCE: float = 1e-10

# Alphabet (A–Z) uses 0.00022659–0.00022684
DTSP_LETTERS: Dict[str, float] = {
    chr(ord("A") + i): 0.00022659 + (i * 0.00000001) for i in range(26)
}

# Digits (0–9) use 0.00022648–0.00022657
DTSP_DIGITS: Dict[str, float] = {
    str(i): 0.00022648 + (i * 0.00000001) for i in range(10)
}

# Punctuation and spacing symbols.
DTSP_SPECIALS: Dict[str, float] = {
    " ": 0.00022688,
    ".": 0.00022689,
    ",": 0.00022690,
    "!": 0.00022691,
    "?": 0.00022692,
    ":": 0.00022693,
    "=": 0.00022694,
    "+": 0.00022695,
    "-": 0.00022696,
    "*": 0.00022697,
    "/": 0.00022698,
    "_": 0.00022699,
}

# Handshake control codes for coordinating DTSP exchanges.
DTSP_CONTROL: Dict[str, float] = {
    "START": 0.00022611,
    "ACCEPT": 0.00022631,
    "END": 0.00022621,
}

# Convenience mapping covering every DTSP symbol.
DTSP_ALPHABET: Dict[str, float] = {
    **DTSP_LETTERS,
    **DTSP_DIGITS,
    **DTSP_SPECIALS,
    **DTSP_CONTROL,
}


class DTSPEncodingError(ValueError):
    """Raised when DTSP encoding or decoding fails."""


def closest_dtsp_symbol(value: float, tolerance: float = DTSP_TOLERANCE) -> Tuple[str | None, float]:
    """Return the closest DTSP symbol for ``value``.

    Parameters
    ----------
    value:
        The observed floating-point value to classify.
    tolerance:
        Maximum absolute error allowed to treat ``value`` as a DTSP symbol.

    Returns
    -------
    tuple
        ``(symbol, error)`` where ``symbol`` is the DTSP key (or ``None`` if no
        symbol matches within ``tolerance``) and ``error`` is the absolute
        difference to the closest known code.
    """

    closest_symbol: str | None = None
    min_error = float("inf")
    for symbol, target in DTSP_ALPHABET.items():
        error = abs(value - target)
        if error < min_error:
            min_error = error
            closest_symbol = symbol
    if min_error <= tolerance:
        return closest_symbol, min_error
    return None, min_error


def encode_handshake_start() -> float:
    """Return the DTSP START control code."""

    return DTSP_CONTROL["START"]


def encode_handshake_accept() -> float:
    """Return the DTSP ACCEPT control code."""

    return DTSP_CONTROL["ACCEPT"]


def encode_handshake_end() -> float:
    """Return the DTSP END control code."""

    return DTSP_CONTROL["END"]


def encode_message_to_dtsp_sequence(message: str, include_start_end: bool = True) -> List[float]:
    """Encode ``message`` into an ordered list of DTSP floats.

    Lowercase letters are normalized to uppercase. Unknown characters raise a
    :class:`DTSPEncodingError`.
    """

    if include_start_end:
        encoded: List[float] = [encode_handshake_start()]
    else:
        encoded = []

    for char in message:
        normalized = char.upper() if char.isalpha() else char
        if normalized not in DTSP_ALPHABET:
            raise DTSPEncodingError(f"Unsupported character for DTSP: {char!r}")
        encoded.append(DTSP_ALPHABET[normalized])

    if include_start_end:
        encoded.append(encode_handshake_end())

    return encoded


def _strip_handshake(values: List[float]) -> List[float]:
    if values and abs(values[0] - DTSP_CONTROL["START"]) <= DTSP_TOLERANCE:
        values = values[1:]
    if values and abs(values[-1] - DTSP_CONTROL["END"]) <= DTSP_TOLERANCE:
        values = values[:-1]
    return values


def decode_dtsp_sequence_to_message(
    values: Iterable[float],
    require_start_end: bool = True,
    tolerance: float = DTSP_TOLERANCE,
) -> str:
    """Decode a list of DTSP floats back into plaintext.

    Unknown values are replaced with ``"?"``. When ``require_start_end`` is
    enabled, the function expects START as the first element and END as the last
    and raises :class:`DTSPEncodingError` if those markers are missing.
    """

    sequence = list(values)
    if require_start_end:
        if not sequence:
            raise DTSPEncodingError("DTSP sequence is empty; START/END missing")
        start_symbol, _ = closest_dtsp_symbol(sequence[0], tolerance)
        end_symbol, _ = closest_dtsp_symbol(sequence[-1], tolerance)
        if start_symbol != "START" or end_symbol != "END":
            raise DTSPEncodingError("START/END handshake markers not found")
        sequence = _strip_handshake(sequence)

    decoded: List[str] = []
    for value in sequence:
        symbol, error = closest_dtsp_symbol(value, tolerance)
        if symbol is None:
            decoded.append("?")
            continue
        if symbol in DTSP_CONTROL:
            # Control codes within the body are retained to help operators spot
            # malformed or multi-part conversations.
            decoded.append(symbol.lower())
            continue
        decoded.append(symbol)
    return "".join(decoded)


def format_dtsp_table() -> str:
    """Return a human-readable table of DTSP symbol mappings."""

    lines = ["symbol | amount"]
    for key, value in sorted(DTSP_ALPHABET.items()):
        lines.append(f"{key} | {value:.8f}")
    return "\n".join(lines)
