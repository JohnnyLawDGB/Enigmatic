"""High-level helper for sending symbolic Enigmatic patterns.

This module wires optional secure layers (handshake, encryption, sessions) into
the numeric encoder without requiring callers to depend on them directly.  It is
designed for legitimate telemetry, coordination, and identity experiments, and
explicitly treats the on-chain numeric patterns as transport rather than as a
replacement for strong, standard cryptography.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .dialect import Dialect, DialectError, load_dialect
from .encoder import EnigmaticEncoder, SpendInstruction, aggregate_spend_instructions
from .model import EncodingConfig
from .rpc_client import DigiByteRPC
from .session import SessionContext, session_key_to_passphrase
from .tx_builder import TransactionBuilder

logger = logging.getLogger(__name__)


class SessionRequiredError(RuntimeError):
    """Raised when a session-bound symbol is sent without an active session."""


def send_symbol(
    rpc: DigiByteRPC,
    dialect: Dialect,
    symbol_name: str,
    to_address: str,
    channel: str = "default",
    extra_payload: dict[str, Any] | None = None,
    encrypt_with_passphrase: str | None = None,
    session: SessionContext | None = None,
) -> list[str]:
    """Encode and broadcast a dialect symbol.

    Returns the transaction ids emitted while enforcing simple, legitimate
    experimental signaling patterns.  This helper does not attempt any hidden
    behavior; it simply bridges symbolic definitions to spend patterns so that
    external systems (like REAL) can remain offline.
    """

    symbol = dialect.symbols.get(symbol_name)
    if symbol is None:
        raise DialectError(f"Symbol {symbol_name} not found in dialect {dialect.name}")

    encrypt_passphrase = encrypt_with_passphrase
    if symbol.requires_session:
        if session is None:
            raise SessionRequiredError(
                f"Symbol {symbol.name} requires an active session for channel {channel}"
            )
        if session.channel != channel or session.dialect != dialect.name:
            logger.warning(
                "Session context mismatch",  # pragma: no cover - log only
                extra={
                    "expected_channel": channel,
                    "session_channel": session.channel,
                    "expected_dialect": dialect.name,
                    "session_dialect": session.dialect,
                },
            )
        encrypt_passphrase = session_key_to_passphrase(session.session_key)

    config = EncodingConfig.enigmatic_default()
    config.fee_punctuation = dialect.fee_punctuation
    encoder = EnigmaticEncoder(config, target_address=to_address)
    message, instructions, fee = encoder.encode_symbol(
        symbol,
        channel=channel,
        extra_payload=extra_payload,
        encrypt_with_passphrase=encrypt_passphrase,
    )

    if not instructions:
        raise RuntimeError("Symbol encoding produced no spend instructions")

    outputs, op_returns = aggregate_spend_instructions(instructions)
    builder = TransactionBuilder(rpc)
    txid = builder.send_payment_tx(outputs, fee, op_return_data=[data.hex() for data in op_returns])
    logger.info(
        "Sent symbol %s for channel %s via txid %s", symbol.name, message.channel, txid
    )
    return [txid]


def load_and_send_symbol(
    rpc: DigiByteRPC,
    dialect_path: str,
    symbol_name: str,
    to_address: str,
    channel: str = "default",
    extra_payload: dict[str, Any] | None = None,
    encrypt_with_passphrase: str | None = None,
    session: SessionContext | None = None,
) -> list[str]:
    """Convenience wrapper that loads a dialect from disk then sends the symbol."""

    dialect = load_dialect(dialect_path)
    return send_symbol(
        rpc,
        dialect=dialect,
        symbol_name=symbol_name,
        to_address=to_address,
        channel=channel,
        extra_payload=extra_payload,
        encrypt_with_passphrase=encrypt_with_passphrase,
        session=session,
    )


def parse_extra_payload(extra_payload_json: str | None) -> dict[str, Any]:
    """Parse optional extra payload JSON for CLI wiring."""

    if not extra_payload_json:
        return {}
    data = json.loads(extra_payload_json)
    if not isinstance(data, dict):
        raise ValueError("Extra payload JSON must decode to an object")
    return data

