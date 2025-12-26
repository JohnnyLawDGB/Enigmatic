"""RPC client for interacting with a DigiByte Core style node."""

from __future__ import annotations

"""Typed JSON-RPC client for DigiByte Core nodes.

The helpers in this module back both the core Enigmatic encoding/decoding flows
and the experimental ordinal/inscription explorers. Configuration is shared via
environment variables so CLI commands and library callers reuse a consistent
connection surface. No consensus logic is implemented here; the client simply
forwards well-typed requests and surfaces errors clearly.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from requests import RequestException, Response

logger = logging.getLogger(__name__)


class RPCError(RuntimeError):
    """Raised when the DigiByte node responds with an RPC error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"RPC error {code}: {message}")
        self.code = code
        self.message = message


def format_rpc_hint(error_obj: dict[str, Any] | RPCError | None) -> str | None:
    """Return a human-friendly hint for common DigiByte JSON-RPC errors.

    This helper is intentionally conservative: it inspects the error code and
    message for well-known failure modes we see during inscription flows and
    emits a concise remediation hint when possible. Callers should still log
    the structured RPC error body; this function complements those diagnostics
    with actionable guidance for CLI users.
    """

    if error_obj is None:
        return None

    code = None
    message = ""
    if isinstance(error_obj, RPCError):
        code = error_obj.code
        message = error_obj.message
    elif isinstance(error_obj, dict):
        code = error_obj.get("code")
        message = str(error_obj.get("message", ""))

    if code == -26 and "min relay fee not met" in message:
        return (
            "The node rejected the transaction because the fee is below its minrelaytxfee policy. "
            "Try one of:\n"
            "  - Increase --max-fee-sats for this inscription\n"
            "  - Increase your wallet's paytxfee (settxfee) for the lab wallet\n"
            "  - Lower minrelaytxfee in digibyte.conf for a local test node"
        )
    if code == -8 and "key-value pair must contain exactly one key" in message:
        return (
            "createrawtransaction outputs are malformed. Each outputs entry must be an object with "
            "exactly one key, e.g. {\"address\": amount} or {\"data\": \"hex\"}."
        )
    if code == -5 and "Invalid DigiByte address" in message:
        return (
            "One of the outputs passed to createrawtransaction is not a valid address. If you see "
            "'script' in the error, you probably used {\"script\": ...} as a key, which DigiByte Core does "
            "not accept in this context."
        )
    return None


class ConfigurationError(RuntimeError):
    """Raised when configuration is invalid."""


class RPCTransportError(RuntimeError):
    """Raised when the RPC endpoint is unreachable or returns malformed data."""


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

    @classmethod
    def from_env(cls) -> "RPCConfig":
        """Create configuration from standard DigiByte RPC environment variables."""

        return cls.from_sources()

    @classmethod
    def from_sources(
        cls,
        *,
        user: str | None = None,
        password: str | None = None,
        host: str | None = None,
        port: int | None = None,
        use_https: bool | None = None,
        wallet: str | None = None,
        endpoint: str | None = None,
    ) -> "RPCConfig":
        """Assemble a config from CLI overrides, environment, and dialect defaults."""

        env = os.environ
        resolved_user = user or env.get("ENIGMATIC_DGB_RPC_USER") or env.get("DGB_RPC_USER")
        resolved_password = password or env.get("ENIGMATIC_DGB_RPC_PASSWORD") or env.get(
            "DGB_RPC_PASSWORD"
        )
        if not resolved_user or not resolved_password:
            raise ConfigurationError(
                "RPC credentials must be provided via arguments or ENIGMATIC_DGB_RPC_*/DGB_RPC_* environment variables"
            )

        endpoint_host: str | None = None
        endpoint_port: int | None = None
        endpoint_https: bool | None = None
        if endpoint:
            parsed = urlparse(endpoint)
            endpoint_host = parsed.hostname or None
            endpoint_port = parsed.port or None
            if parsed.scheme:
                endpoint_https = parsed.scheme.lower() == "https"

        env_host = env.get("ENIGMATIC_DGB_RPC_HOST") or env.get("DGB_RPC_HOST")
        env_port_str = env.get("ENIGMATIC_DGB_RPC_PORT") or env.get("DGB_RPC_PORT")
        env_port = None
        if env_port_str:
            try:
                env_port = int(env_port_str)
            except ValueError as exc:
                raise ConfigurationError("DGB_RPC_PORT must be an integer") from exc
        env_wallet = env.get("ENIGMATIC_DGB_RPC_WALLET") or env.get("DGB_RPC_WALLET")
        env_https_raw = env.get("ENIGMATIC_DGB_RPC_USE_HTTPS") or env.get(
            "DGB_RPC_USE_HTTPS"
        )
        env_https: bool | None = None
        if env_https_raw is not None:
            env_https = env_https_raw.lower() in {"1", "true", "yes"}

        resolved_host = host or endpoint_host or env_host or "127.0.0.1"
        resolved_port = port or endpoint_port or env_port or 14022
        resolved_https = (
            use_https
            if use_https is not None
            else (
                endpoint_https
                if endpoint_https is not None
                else env_https if env_https is not None else False
            )
        )
        resolved_wallet = wallet or env_wallet
        return cls(
            user=resolved_user,
            password=resolved_password,
            host=resolved_host,
            port=resolved_port,
            use_https=resolved_https,
            wallet=resolved_wallet,
        )


class DigiByteRPCClient:
    """Typed JSON-RPC client for DigiByte Core compatible nodes.

    The client is intentionally thin: each helper maps directly to an RPC
    method exposed by the node and returns the parsed JSON response. The
    methods below cover the common read paths used throughout Enigmatic,
    including convenience helpers for verbose transaction decoding and block
    retrieval by height.

    Connection defaults can be overridden via the environment variables
    ``ENIGMATIC_DGB_RPC_USER``, ``ENIGMATIC_DGB_RPC_PASSWORD``,
    ``ENIGMATIC_DGB_RPC_HOST``, and ``ENIGMATIC_DGB_RPC_PORT``. These mirror
    the values typically placed in ``~/.digibyte/digibyte.conf`` and take
    precedence over any baked-in defaults.
    """

    def __init__(self, config: RPCConfig) -> None:
        self.config = config
        self._session = requests.Session()
        self._base_url = config.base_url
        self._wallet = config.wallet

    @classmethod
    def from_env(cls) -> "DigiByteRPCClient":
        """Instantiate a client using environment variables."""

        return cls(RPCConfig.from_env())

    def call(self, method: str, params: Optional[list[Any]] = None) -> Any:
        """Perform a JSON-RPC request."""

        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or [],
        }
        logger.debug("RPC call %s params=%s", method, params)
        try:
            response = self._session.post(
                self._url,
                data=json.dumps(payload),
                headers={"content-type": "application/json"},
                auth=(self.config.user, self.config.password),
                timeout=30,
            )
        except RequestException as exc:
            logger.debug("RPC connection failed: %s", exc, exc_info=True)
            raise RPCTransportError(
                "RPC connection failed. Verify the node is reachable and credentials are correct."
            ) from exc
        try:
            self._raise_for_status(response)
        except requests.HTTPError as exc:
            logger.debug("RPC HTTP error: %s", exc, exc_info=True)
            raise RPCTransportError(
                "RPC server returned an HTTP error; check the URL, wallet path, and authentication."
            ) from exc
        try:
            result = response.json()
        except ValueError as exc:
            logger.debug("RPC JSON parse error: %s", response.text, exc_info=True)
            raise RPCTransportError("RPC server returned malformed JSON") from exc
        if result.get("error"):
            error = result["error"]
            raise RPCError(error.get("code", -1), error.get("message", "unknown"))
        return result.get("result")

    def _raise_for_status(self, response: Response) -> None:
        # DigiByte Core surfaces JSON-RPC errors as HTTP 500; logging the
        # structured error body here makes debugging far more actionable.
        if not response.ok:
            try:
                err_body = response.json()
            except Exception:
                err_body = response.text

            logger.error("RPC HTTP error %s from %s", response.status_code, response.url)
            logger.error("RPC error body: %s", err_body)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("HTTP error from RPC server: %s", exc)
            raise

    @property
    def _url(self) -> str:
        if self._wallet:
            return f"{self._base_url}/wallet/{self._wallet}"
        return self._base_url

    def set_wallet(self, wallet: str | None) -> None:
        """Switch the RPC client to a different loaded wallet."""

        self._wallet = wallet

    # Convenience wrappers -------------------------------------------------

    def getblockchaininfo(self) -> Dict[str, Any]:
        return self.call("getblockchaininfo")

    def getblockcount(self) -> int:
        return int(self.call("getblockcount"))

    def getblockhash(self, height: int) -> str:
        return self.call("getblockhash", [height])

    def getblock(self, block_hash: str, verbosity: int = 1) -> Dict[str, Any]:
        return self.call("getblock", [block_hash, verbosity])

    def getrawtransaction(self, txid: str, verbose: bool = False) -> Any:
        return self.call("getrawtransaction", [txid, int(verbose)])

    def getrawtransaction_verbose(self, txid: str) -> Dict[str, Any]:
        """Fetch and decode a transaction in a single RPC call."""

        return self.getrawtransaction(txid, verbose=True)

    def decoderawtransaction(self, raw_tx: str) -> Dict[str, Any]:
        return self.call("decoderawtransaction", [raw_tx])

    def getblock_by_height(self, height: int) -> Dict[str, Any]:
        """Retrieve a block JSON payload by height using verbosity=2."""

        block_hash = self.getblockhash(height)
        return self.getblock(block_hash, verbosity=2)

    def get_best_height(self) -> int:
        """Return the current best chain height."""

        return int(self.getblockcount())

    def listunspent(
        self,
        minconf: int = 1,
        maxconf: int = 9999999,
        addresses: Optional[list[str]] = None,
    ) -> list[Dict[str, Any]]:
        params: list[Any] = [minconf, maxconf]
        if addresses is not None:
            params.append(addresses)
        return self.call("listunspent", params)

    def getnewaddress(
        self, label: str | None = None, address_type: str | None = None
    ) -> str:
        params: list[Any] = []
        if label is not None:
            params.append(label)
        elif address_type is not None:
            params.append("")
        if address_type is not None:
            params.append(address_type)
        return self.call("getnewaddress", params)

    def getrawchangeaddress(self) -> str:
        return self.call("getrawchangeaddress")

    def getbalance(self) -> float:
        return self.call("getbalance")

    def getnetworkinfo(self) -> Dict[str, Any]:
        return self.call("getnetworkinfo")

    def getmempoolinfo(self) -> Dict[str, Any]:
        return self.call("getmempoolinfo")

    def estimatesmartfee(
        self, conf_target: int, estimate_mode: str | None = None
    ) -> Dict[str, Any]:
        params: list[Any] = [conf_target]
        if estimate_mode is not None:
            params.append(estimate_mode)
        return self.call("estimatesmartfee", params)

    def gettransaction(
        self, txid: str, include_watchonly: bool = True
    ) -> Dict[str, Any]:
        return self.call("gettransaction", [txid, include_watchonly])

    def createrawtransaction(
        self,
        inputs: list[Dict[str, Any]],
        outputs: Dict[str, float] | list[Dict[str, float]],
    ) -> str:
        return self.call("createrawtransaction", [inputs, outputs])

    def fundrawtransaction(
        self, raw_tx: str, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        params: list[Any] = [raw_tx]
        if options is not None:
            params.append(options)
        return self.call("fundrawtransaction", params)

    def signrawtransactionwithwallet(self, raw_tx: str) -> Dict[str, Any]:
        return self.call("signrawtransactionwithwallet", [raw_tx])

    def sendrawtransaction(self, raw_tx: str) -> str:
        return self.call("sendrawtransaction", [raw_tx])


# Backward compatibility alias until downstream code is updated.
DigiByteRPC = DigiByteRPCClient
