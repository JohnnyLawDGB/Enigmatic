import hashlib

import pytest

from enigmatic_dgb.descriptors import (
    DeterministicAggregationBackend,
    PubKey,
    SignerSet,
    musig2_descriptor,
    taproot_key_descriptor,
    threshold_leaf,
    threshold_script_descriptor,
)


@pytest.fixture
def sample_signer_set() -> SignerSet:
    return SignerSet(
        id="OPS_TEAM",
        base_keys=[
            PubKey("c" * 64),
            PubKey("a" * 64),
            PubKey("b" * 64),
        ],
        threshold=2,
    )


def test_taproot_key_descriptor_normalizes_hex() -> None:
    descriptor = taproot_key_descriptor("0x" + "ab" * 32)
    assert descriptor == "tr(" + "ab" * 32 + ")"


def test_musig2_descriptor_uses_backend(sample_signer_set: SignerSet) -> None:
    backend = DeterministicAggregationBackend()
    descriptor = musig2_descriptor(sample_signer_set, backend=backend)
    material = "".join(sorted(pk.normalized() for pk in sample_signer_set.base_keys))
    expected_key = hashlib.sha256(material.encode("ascii")).hexdigest()[:64]
    assert descriptor == f"tr({expected_key})"


def test_threshold_leaf_serializes_signer_set(sample_signer_set: SignerSet) -> None:
    leaf = threshold_leaf(sample_signer_set)
    assert leaf.startswith("thresh(2,")
    assert "pk(" in leaf


def test_threshold_descriptor_adds_delay(sample_signer_set: SignerSet) -> None:
    descriptor = threshold_script_descriptor("f" * 64, sample_signer_set, csv_delay=288)
    assert descriptor.startswith("tr(")
    assert "older(288)" in descriptor


def test_threshold_leaf_rejects_invalid_threshold(sample_signer_set: SignerSet) -> None:
    with pytest.raises(ValueError):
        threshold_leaf(SignerSet(id="oops", base_keys=sample_signer_set.base_keys, threshold=0))
