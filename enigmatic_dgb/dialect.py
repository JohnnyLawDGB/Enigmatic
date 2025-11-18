"""Dialect loader for symbolic Enigmatic patterns.

Session-aware dialects allow legitimate systems to declare which signals must be
protected by an established cryptographic session.  This file keeps the schema
simple and declarative while deferring the actual security to the handshake and
AEAD helpers elsewhere in the package.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .script_plane import ScriptPlane, parse_script_plane_block

logger = logging.getLogger(__name__)


class DialectError(RuntimeError):
    """Raised when a dialect file is missing required information."""


@dataclass
class DialectSymbol:
    """Symbol definition mapping to anchors, micros, and metadata."""

    name: str
    description: str
    anchors: list[float]
    micros: list[float]
    intent: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    script_plane: ScriptPlane | None = None
    dialect_name: str | None = None
    requires_session: bool = False
    session_scope: str | None = None


@dataclass
class Dialect:
    """Collection of symbolic patterns for Enigmatic messaging."""

    name: str
    description: str
    symbols: dict[str, DialectSymbol]
    fee_punctuation: float


def load_dialect(path: str | Path) -> Dialect:
    """Load a dialect definition from ``path``.

    Dialects are intentionally simple YAML files so that legitimate
    experimental systems can define symbolic patterns without touching the
    encoder internals.  This function validates the basic structure and
    raises :class:`DialectError` when required attributes are missing.
    """

    path = Path(path)
    if not path.exists():
        raise DialectError(f"Dialect file does not exist: {path}")

    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - PyYAML handles details
        raise DialectError(f"Failed to parse dialect YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise DialectError("Dialect file must contain a mapping at the top level")

    name = _require_str(data, "name", "Dialect must define a name")
    description = _require_str(
        data, "description", f"Dialect {name} must include a description"
    )
    fee_punctuation = _require_float(
        data, "fee_punctuation", f"Dialect {name} must define fee_punctuation"
    )

    raw_symbols = data.get("symbols")
    if not isinstance(raw_symbols, dict) or not raw_symbols:
        raise DialectError(f"Dialect {name} must define at least one symbol")

    symbols: dict[str, DialectSymbol] = {}
    for symbol_name, payload in raw_symbols.items():
        if not isinstance(payload, dict):
            raise DialectError(f"Symbol {symbol_name} must be a mapping")
        desc = _require_str(
            payload, "description", f"Symbol {symbol_name} must include a description"
        )
        anchors = _require_float_list(
            payload, "anchors", f"Symbol {symbol_name} must define anchors"
        )
        micros = _require_float_list(
            payload, "micros", f"Symbol {symbol_name} must define micros"
        )
        intent = payload.get("intent")
        if intent is not None and not isinstance(intent, str):
            raise DialectError(f"Symbol {symbol_name} intent must be a string if present")
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise DialectError(f"Symbol {symbol_name} metadata must be a mapping")
        script_plane_block = payload.get("script_plane")
        script_plane: ScriptPlane | None = None
        if script_plane_block is not None:
            script_plane = parse_script_plane_block(
                script_plane_block,
                lambda msg: DialectError(f"Symbol {symbol_name}: {msg}"),
            )
        requires_session = bool(payload.get("requires_session", False))
        session_scope = payload.get("session_scope")
        if session_scope is not None and not isinstance(session_scope, str):
            raise DialectError(
                f"Symbol {symbol_name} session_scope must be a string or null"
            )
        if requires_session and not session_scope:
            session_scope = "channel"
        symbols[symbol_name] = DialectSymbol(
            name=symbol_name,
            description=desc,
            anchors=anchors,
            micros=micros,
            intent=intent,
            metadata=dict(metadata),
            script_plane=script_plane,
            dialect_name=name,
            requires_session=requires_session,
            session_scope=session_scope,
        )

    dialect = Dialect(
        name=name,
        description=description,
        symbols=symbols,
        fee_punctuation=fee_punctuation,
    )
    logger.debug("Loaded dialect %s with %d symbols", name, len(symbols))
    return dialect


def _require_str(data: dict[str, Any], key: str, error: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DialectError(error)
    return value


def _require_float(data: dict[str, Any], key: str, error: str) -> float:
    value = data.get(key)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DialectError(error) from exc


def _require_float_list(data: dict[str, Any], key: str, error: str) -> list[float]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise DialectError(error)
    floats: list[float] = []
    for item in value:
        try:
            floats.append(float(item))
        except (TypeError, ValueError) as exc:
            raise DialectError(f"{error}: non-numeric value {item}") from exc
    return floats

