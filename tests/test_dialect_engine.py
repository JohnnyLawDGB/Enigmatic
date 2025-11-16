"""Tests for the dialect loader and symbol send path."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from enigmatic_dgb.dialect import Dialect, DialectSymbol, load_dialect
from enigmatic_dgb.encoder import EnigmaticEncoder
from enigmatic_dgb.model import EncodingConfig
from enigmatic_dgb.symbol_sender import send_symbol


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "dialect.yaml"
    path.write_text(content)
    return path


def test_load_dialect_parses_yaml(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
name: intel
description: Intel dialect
fee_punctuation: 0.42
symbols:
  INTEL_HELLO:
    description: hello
    intent: identity
    anchors: [217, 352]
    micros: [0.152, 0.303]
    metadata:
      presence: normal
        """.strip(),
    )

    dialect = load_dialect(path)

    assert dialect.name == "intel"
    assert dialect.fee_punctuation == pytest.approx(0.42)
    assert "INTEL_HELLO" in dialect.symbols
    symbol = dialect.symbols["INTEL_HELLO"]
    assert symbol.intent == "identity"
    assert symbol.metadata["presence"] == "normal"


def test_encode_symbol_builds_instructions() -> None:
    symbol = DialectSymbol(
        name="TEST",
        description="test symbol",
        anchors=[217.0],
        micros=[0.111, 0.222],
        intent="presence",
        metadata={"level": "hi"},
        dialect_name="intel",
    )
    config = EncodingConfig.enigmatic_default()
    config.fee_punctuation = 0.33
    encoder = EnigmaticEncoder(config, target_address="DTexample")

    message, instructions, fee = encoder.encode_symbol(
        symbol, channel="family", extra_payload={"extra": True}
    )

    assert message.channel == "family"
    assert message.payload["symbol"] == "TEST"
    assert message.payload["dialect"] == "intel"
    assert message.payload["extra"] is True
    assert len(instructions) == 3
    assert instructions[0].amount == pytest.approx(217.0)
    assert instructions[1].amount == pytest.approx(0.111)
    assert fee == pytest.approx(0.33)


def test_send_symbol_uses_transaction_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    symbol = DialectSymbol(
        name="PING",
        description="ping",
        anchors=[100.0, 200.0],
        micros=[0.1],
        dialect_name="custom",
    )
    dialect = Dialect(
        name="custom",
        description="Custom",
        symbols={"PING": symbol},
        fee_punctuation=0.5,
    )

    captured: dict[str, Any] = {}

    class DummyBuilder:
        def __init__(self, rpc: Any) -> None:
            captured["rpc"] = rpc

        def send_payment_tx(self, outputs: dict[str, float], fee: float) -> str:
            captured["outputs"] = outputs
            captured["fee"] = fee
            return "txid123"

    monkeypatch.setattr("enigmatic_dgb.symbol_sender.TransactionBuilder", DummyBuilder)

    class DummyRPC:  # pragma: no cover - simple stub
        pass

    txids = send_symbol(
        DummyRPC(),
        dialect=dialect,
        symbol_name="PING",
        to_address="DTdest",
        channel="ops",
    )

    assert txids == ["txid123"]
    assert captured["outputs"]["DTdest"] == pytest.approx(300.1)
    assert captured["fee"] == pytest.approx(0.5)
