from __future__ import annotations

import pytest

from enigmatic_dgb.ordinals.inscriptions import _push_data


def test_push_data_small_literal() -> None:
    data = b"x" * 10

    assert _push_data(data) == b"\x0a" + data


def test_push_data_op_pushdata1() -> None:
    data = b"x" * 100

    encoded = _push_data(data)

    assert encoded.startswith(b"\x4c\x64")
    assert len(encoded) == 2 + len(data)


def test_push_data_op_pushdata2() -> None:
    data = b"x" * 300

    encoded = _push_data(data)

    assert encoded.startswith(b"\x4d")
    assert encoded[1:3] == len(data).to_bytes(2, "little")
    assert len(encoded) == 1 + 2 + len(data)


def test_push_data_too_large() -> None:
    data = b"x" * 521

    with pytest.raises(ValueError):
        _push_data(data)
