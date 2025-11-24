"""Prime ladder utilities for building and recognizing prime-ratio steps."""

from __future__ import annotations

from typing import Iterator, Sequence

# A short, extendable sequence of primes observed in prime ladder patterns.
# The list can be extended in future releases as additional ratios are used on-chain.
PRIME_SEQUENCE: list[int] = [41, 47, 53, 59, 61, 67, 71, 73, 79, 83]


def prime_ratio(p: int, q: int, decimals: int = 8) -> float:
    """Return the rounded prime ratio ``p / q`` with the requested precision."""

    if q == 0:
        raise ValueError("Denominator must be non-zero for prime ratios")
    return round(p / q, decimals)


def ladder_step_ratio(index: int, decimals: int = 8) -> float:
    """Return the prime ladder ratio at ``index`` (prime_n / prime_{n+1})."""

    if index < 0 or index + 1 >= len(PRIME_SEQUENCE):
        raise IndexError("Prime ladder index is out of range for the configured sequence")
    return prime_ratio(PRIME_SEQUENCE[index], PRIME_SEQUENCE[index + 1], decimals)


def iter_prime_pairs(decimals: int = 8) -> Iterator[tuple[int, int, int, float]]:
    """Iterate over consecutive prime pairs and their ratios.

    Yields tuples of ``(index, p, q, ratio)`` for each step in ``PRIME_SEQUENCE``.
    """

    for index in range(len(PRIME_SEQUENCE) - 1):
        numerator = PRIME_SEQUENCE[index]
        denominator = PRIME_SEQUENCE[index + 1]
        yield index, numerator, denominator, prime_ratio(numerator, denominator, decimals)


def match_prime_ratio(
    value: float, tolerance: float = 1e-8, decimals: int = 8, primes: Sequence[int] | None = None
) -> tuple[int, int, int, float] | None:
    """Return the matching prime pair for ``value`` if it is a ladder ratio.

    Args:
        value: Observed amount to compare against known prime ratios.
        tolerance: Allowed absolute deviation when comparing floating point values.
        decimals: Precision used when generating prime ratios for comparison.
        primes: Optional override prime list; defaults to :data:`PRIME_SEQUENCE`.

    Returns:
        Tuple of ``(index, p, q, ratio)`` when a match is within ``tolerance``, otherwise
        ``None``.
    """

    prime_list = list(primes) if primes is not None else PRIME_SEQUENCE
    for index in range(len(prime_list) - 1):
        numerator = prime_list[index]
        denominator = prime_list[index + 1]
        ratio = prime_ratio(numerator, denominator, decimals)
        if abs(value - ratio) <= tolerance:
            return index, numerator, denominator, ratio
    return None
