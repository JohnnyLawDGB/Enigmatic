"""Tests covering session-aware dialect behavior for the symbol sender."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from enigmatic_dgb import symbol_sender as symbol_sender_module
from enigmatic_dgb.dialect import Dialect, DialectSymbol
from enigmatic_dgb.encoder import SpendInstruction
from enigmatic_dgb.model import EnigmaticMessage
from enigmatic_dgb.session import SessionContext, session_key_to_passphrase
from enigmatic_dgb.symbol_sender import SessionRequiredError, send_symbol


@pytest.fixture(autouse=True)
def stub_transaction_builder(monkeypatch):
    class DummyBuilder:
        last_call = None

        def __init__(self, rpc):
            self.rpc = rpc

        def send_payment_tx(self, outputs, fee):
            DummyBuilder.last_call = (outputs, fee)
            return "tx-dummy"

    monkeypatch.setattr(symbol_sender_module, "TransactionBuilder", DummyBuilder)
    return DummyBuilder


@pytest.fixture
def encoder_stub(monkeypatch):
    class DummyEncoder:
        last_passphrase = None

        def __init__(self, config, target_address):
            self.config = config
            self.target_address = target_address

        def encode_symbol(
            self,
            symbol,
            channel,
            extra_payload=None,
            encrypt_with_passphrase=None,
        ):
            DummyEncoder.last_passphrase = encrypt_with_passphrase
            message = EnigmaticMessage(
                id="msg",
                timestamp=datetime.utcnow(),
                channel=channel,
                intent="test",
                payload={},
            )
            instruction = SpendInstruction(
                to_address=self.target_address,
                amount=1.0,
                is_anchor=True,
                is_micro=False,
                role="test",
            )
            return message, [instruction], self.config.fee_punctuation

    monkeypatch.setattr(symbol_sender_module, "EnigmaticEncoder", DummyEncoder)
    return DummyEncoder


@pytest.fixture
def sample_dialect():
    symbol = DialectSymbol(
        name="SECURE",
        description="session protected",
        anchors=[1.0],
        micros=[0.1],
        intent="identity",
        metadata={},
        dialect_name="test",
        requires_session=True,
        session_scope="channel",
    )
    return Dialect(name="test", description="desc", symbols={symbol.name: symbol}, fee_punctuation=0.1)


def test_symbol_requires_session(sample_dialect, encoder_stub):
    rpc = SimpleNamespace()
    with pytest.raises(SessionRequiredError):
        send_symbol(rpc, sample_dialect, "SECURE", "addr")


def test_symbol_with_session(sample_dialect, encoder_stub):
    rpc = SimpleNamespace()
    session_key = b"0" * 32
    session = SessionContext(
        session_id="abc",
        channel="default",
        dialect="test",
        created_at=datetime.utcnow(),
        session_key=session_key,
    )
    txids = send_symbol(rpc, sample_dialect, "SECURE", "addr", session=session)
    assert txids == ["tx-dummy"]
    assert encoder_stub.last_passphrase == session_key_to_passphrase(session_key)


def test_symbol_without_session_requirement(encoder_stub):
    open_symbol = DialectSymbol(
        name="OPEN",
        description="no session",
        anchors=[1.0],
        micros=[0.1],
        intent="identity",
        metadata={},
        dialect_name="test",
        requires_session=False,
    )
    dialect = Dialect(
        name="test",
        description="desc",
        symbols={open_symbol.name: open_symbol},
        fee_punctuation=0.1,
    )
    rpc = SimpleNamespace()
    assert send_symbol(rpc, dialect, "OPEN", "addr") == ["tx-dummy"]
    assert encoder_stub.last_passphrase is None
    session = SessionContext(
        session_id="xyz",
        channel="default",
        dialect="test",
        created_at=datetime.utcnow(),
        session_key=b"1" * 32,
    )
    assert send_symbol(rpc, dialect, "OPEN", "addr", session=session) == ["tx-dummy"]
