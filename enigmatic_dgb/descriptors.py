"""Taproot Miniscript descriptor helpers for signer aggregation policies."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class PubKey:
    """Represents an x-only public key used in Taproot descriptors."""

    x_only_hex: str

    def normalized(self) -> str:
        key = self.x_only_hex.lower().removeprefix("0x")
        if len(key) != 64:
            raise ValueError("Taproot x-only keys must be 32 bytes (64 hex chars)")
        int(key, 16)
        return key


@dataclass(frozen=True)
class SignerSet:
    """Collection of base keys participating in an aggregate signature."""

    id: str
    base_keys: Sequence[PubKey]
    threshold: int | None = None

    @property
    def total_signers(self) -> int:
        return len(self.base_keys)


class AggregationBackend(Protocol):
    """Protocol describing how aggregate Taproot keys are produced."""

    def aggregate_key(self, signer_set: SignerSet) -> str:
        """Return an x-only aggregated key for ``signer_set``."""


class DeterministicAggregationBackend:
    """Single-node helper producing deterministic aggregate keys for tests."""

    def aggregate_key(self, signer_set: SignerSet) -> str:
        if not signer_set.base_keys:
            raise ValueError("Signer sets require at least one key")
        material = "".join(sorted(pk.normalized() for pk in signer_set.base_keys))
        digest = hashlib.sha256(material.encode("ascii")).hexdigest()
        return digest[:64]


def taproot_key_descriptor(internal_key: str) -> str:
    """Return a basic ``tr(KEY)`` descriptor for *internal_key*."""

    key = PubKey(internal_key).normalized()
    return f"tr({key})"


def musig2_descriptor(
    signer_set: SignerSet, backend: AggregationBackend | None = None
) -> str:
    """Return ``tr(AGG_KEY)`` for an aggregated signer set."""

    if backend is None:
        backend = DeterministicAggregationBackend()
    agg_key = backend.aggregate_key(signer_set)
    return taproot_key_descriptor(agg_key)


def threshold_leaf(signer_set: SignerSet) -> str:
    """Return a ``thresh(N, pk(...))`` Miniscript fragment for ``signer_set``."""

    if signer_set.threshold is None:
        raise ValueError("threshold_leaf requires signer_set.threshold")
    if signer_set.threshold <= 0:
        raise ValueError("threshold must be positive")
    if signer_set.threshold > signer_set.total_signers:
        raise ValueError("threshold cannot exceed total signers")
    pk_expr = ",".join(f"pk({key.normalized()})" for key in signer_set.base_keys)
    return f"thresh({signer_set.threshold},{pk_expr})"


def threshold_script_descriptor(
    internal_key: str,
    signer_set: SignerSet,
    csv_delay: int = 144,
) -> str:
    """Return a Taproot descriptor with a delayed threshold script path."""

    if csv_delay <= 0:
        raise ValueError("csv_delay must be positive")
    leaf = threshold_leaf(signer_set)
    key = PubKey(internal_key).normalized()
    return f"tr({key},{{and_v(v:older({csv_delay}),{leaf})}})"
