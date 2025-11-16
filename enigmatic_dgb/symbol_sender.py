"""High-level helper for sending symbolic Enigmatic patterns."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from .dialect import Dialect, DialectError, load_dialect
from .encoder import EnigmaticEncoder, SpendInstruction
from .model import EncodingConfig
from .rpc_client import DigiByteRPC
from .tx_builder import TransactionBuilder

logger = logging.getLogger(__name__)


def send_symbol(
    rpc: DigiByteRPC,
    dialect: Dialect,
    symbol_name: str,
    to_address: str,
    channel: str = "default",
    extra_payload: dict[str, Any] | None = None,
) -> List[str]:
    """Encode and broadcast a dialect symbol.

    Returns the transaction ids emitted while enforcing simple, legitimate
    experimental signaling patterns.  This helper does not attempt any hidden
    behavior; it simply bridges symbolic definitions to spend patterns so that
    external systems (like REAL) can remain offline.
    """

    symbol = dialect.symbols.get(symbol_name)
    if symbol is None:
        raise DialectError(f"Symbol {symbol_name} not found in dialect {dialect.name}")

    config = EncodingConfig.enigmatic_default()
    config.fee_punctuation = dialect.fee_punctuation
    encoder = EnigmaticEncoder(config, target_address=to_address)
    message, instructions, fee = encoder.encode_symbol(
        symbol, channel=channel, extra_payload=extra_payload
    )

    if not instructions:
        raise RuntimeError("Symbol encoding produced no spend instructions")

    outputs = _aggregate_outputs(instructions)
    builder = TransactionBuilder(rpc)
    txid = builder.send_payment_tx(outputs, fee)
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
) -> List[str]:
    """Convenience wrapper that loads a dialect from disk then sends the symbol."""

    dialect = load_dialect(dialect_path)
    return send_symbol(
        rpc,
        dialect=dialect,
        symbol_name=symbol_name,
        to_address=to_address,
        channel=channel,
        extra_payload=extra_payload,
    )


def _aggregate_outputs(instructions: List[SpendInstruction]) -> Dict[str, float]:
    outputs: Dict[str, float] = {}
    for instruction in instructions:
        outputs.setdefault(instruction.to_address, 0.0)
        outputs[instruction.to_address] += instruction.amount
    return outputs


def parse_extra_payload(extra_payload_json: str | None) -> dict[str, Any]:
    """Parse optional extra payload JSON for CLI wiring."""

    if not extra_payload_json:
        return {}
    data = json.loads(extra_payload_json)
    if not isinstance(data, dict):
        raise ValueError("Extra payload JSON must decode to an object")
    return data

