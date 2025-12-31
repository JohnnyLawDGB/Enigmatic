"""Shared configuration loader for Enigmatic."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml


class ConfigurationError(RuntimeError):
    """Raised when configuration is invalid."""


DEFAULT_CONFIG_PATH = Path.home() / ".enigmatic.yaml"
_CONFIG_PATH_OVERRIDE: Path | None = None


@dataclass
class RPCConfig:
    """Configuration container for DigiByte RPC connection details."""

    user: str
    password: str
    host: str = "127.0.0.1"
    port: int = 14022
    use_https: bool = False
    wallet: str | None = None

    @property
    def base_url(self) -> str:
        scheme = "https" if self.use_https else "http"
        return f"{scheme}://{self.host}:{self.port}"


def set_default_config_path(path: str | Path | None) -> None:
    """Remember a user-supplied config path for future loads."""

    global _CONFIG_PATH_OVERRIDE
    _CONFIG_PATH_OVERRIDE = Path(path).expanduser() if path else None


def _load_config_file(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise ConfigurationError(f"Config file not found: {path}")
        return {}

    try:
        loaded = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - delegated to PyYAML
        raise ConfigurationError(f"Invalid YAML in config file {path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ConfigurationError(f"Expected {path} to contain a YAML object with an 'rpc' section")
    return loaded


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return None


def _coerce_port(raw: Any, *, source: str) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid port in {source}: {raw}") from exc


def _first_value(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None:
            return value
    return default


def _parse_endpoint(raw: str | None) -> tuple[str | None, int | None, bool | None]:
    if not raw:
        return None, None, None
    parsed = urlparse(raw)
    if not parsed.scheme and not parsed.hostname:
        raise ConfigurationError(f"Invalid RPC endpoint URL: {raw}")
    host = parsed.hostname or None
    port = parsed.port
    use_https = parsed.scheme.lower() == "https" if parsed.scheme else None
    return host, port, use_https


def load_rpc_config(
    *,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> RPCConfig:
    """Load RPC configuration from environment variables and optional YAML."""

    env_map = os.environ if env is None else env
    explicit_path = config_path is not None or _CONFIG_PATH_OVERRIDE is not None
    path = (
        Path(config_path).expanduser()
        if config_path is not None
        else _CONFIG_PATH_OVERRIDE or DEFAULT_CONFIG_PATH
    )

    file_config = _load_config_file(path, required=explicit_path)
    rpc_section = file_config.get("rpc", {}) if isinstance(file_config, dict) else {}
    if rpc_section and not isinstance(rpc_section, dict):
        raise ConfigurationError(f"Expected 'rpc' to be a mapping in {path}")

    override_map = dict(overrides or {})

    env_user = env_map.get("DGB_RPC_USER") or env_map.get("ENIGMATIC_DGB_RPC_USER")
    env_password = env_map.get("DGB_RPC_PASSWORD") or env_map.get("ENIGMATIC_DGB_RPC_PASSWORD")
    env_host = env_map.get("DGB_RPC_HOST") or env_map.get("ENIGMATIC_DGB_RPC_HOST")
    env_port = _coerce_port(
        env_map.get("DGB_RPC_PORT") or env_map.get("ENIGMATIC_DGB_RPC_PORT"),
        source="environment",
    )
    env_wallet = env_map.get("DGB_RPC_WALLET") or env_map.get("ENIGMATIC_DGB_RPC_WALLET")
    env_use_https = _coerce_bool(
        env_map.get("DGB_RPC_USE_HTTPS") or env_map.get("ENIGMATIC_DGB_RPC_USE_HTTPS")
    )
    env_endpoint = env_map.get("DGB_RPC_ENDPOINT") or env_map.get("DGB_RPC_URL")
    if not env_endpoint:
        env_endpoint = env_map.get("ENIGMATIC_DGB_RPC_ENDPOINT") or env_map.get("ENIGMATIC_DGB_RPC_URL")

    endpoint_host, endpoint_port, endpoint_use_https = _parse_endpoint(
        _first_value(override_map.get("endpoint"), env_endpoint, rpc_section.get("endpoint"))
    )

    resolved_user = _first_value(override_map.get("user"), env_user, rpc_section.get("user"))
    resolved_password = _first_value(
        override_map.get("password"), env_password, rpc_section.get("password")
    )
    if not resolved_user or not resolved_password:
        raise ConfigurationError(
            "RPC credentials must be provided via DGB_RPC_* environment variables or a config file"
        )

    resolved_host = _first_value(
        override_map.get("host"), endpoint_host, env_host, rpc_section.get("host"), "127.0.0.1"
    )
    resolved_port = _first_value(
        _coerce_port(override_map.get("port"), source="overrides"),
        _coerce_port(endpoint_port, source="endpoint"),
        env_port,
        _coerce_port(rpc_section.get("port"), source=f"{path} rpc.port")
        if rpc_section.get("port") is not None
        else None,
        14022,
    )
    resolved_use_https = _first_value(
        _coerce_bool(override_map.get("use_https")),
        endpoint_use_https,
        env_use_https,
        _coerce_bool(rpc_section.get("use_https")),
        False,
    )
    resolved_wallet = _first_value(
        override_map.get("wallet"), env_wallet, rpc_section.get("wallet")
    )

    return RPCConfig(
        user=resolved_user,
        password=resolved_password,
        host=resolved_host,
        port=resolved_port,
        use_https=bool(resolved_use_https),
        wallet=resolved_wallet,
    )

