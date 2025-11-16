"""RPC client for interacting with a DigiByte Core style node."""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from requests import Response

logger = logging.getLogger(__name__)


class RPCError(RuntimeError):
    """Raised when the DigiByte node responds with an RPC error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"RPC error {code}: {message}")
        self.code = code
        self.message = message


class ConfigurationError(RuntimeError):
    """Raised when configuration is invalid."""


@dataclass
class RPCConfig:
    """Simple configuration container for RPC connection details."""

    user: str
    password: str
    host: str = "127.0.0.1"
    port: int = 14022
    use_https: bool = False

    @classmethod
    def from_env(cls) -> "RPCConfig":
        """Create configuration from standard DigiByte RPC environment variables."""

        user = os.getenv("DGB_RPC_USER")
        password = os.getenv("DGB_RPC_PASSWORD")
        if not user or not password:
            raise ConfigurationError(
                "DGB_RPC_USER and DGB_RPC_PASSWORD environment variables must be set"
            )
        host = os.getenv("DGB_RPC_HOST", "127.0.0.1")
        port_str = os.getenv("DGB_RPC_PORT", "14022")
        try:
            port = int(port_str)
        except ValueError as exc:
            raise ConfigurationError("DGB_RPC_PORT must be an integer") from exc
        return cls(user=user, password=password, host=host, port=port)


class DigiByteRPC:
    """Minimal JSON-RPC client for DigiByte Core compatible nodes."""

    def __init__(self, config: RPCConfig) -> None:
        self.config = config
        self._session = requests.Session()
        self._url = (
            f"{'https' if config.use_https else 'http'}://{config.host}:{config.port}"
        )

    @classmethod
    def from_env(cls) -> "DigiByteRPC":
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
        response = self._session.post(
            self._url,
            data=json.dumps(payload),
            headers={"content-type": "application/json"},
            auth=(self.config.user, self.config.password),
            timeout=30,
        )
        self._raise_for_status(response)
        result = response.json()
        if result.get("error"):
            error = result["error"]
            raise RPCError(error.get("code", -1), error.get("message", "unknown"))
        return result.get("result")

    @staticmethod
    def _raise_for_status(response: Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("HTTP error from RPC server: %s", exc)
            raise

    # Convenience wrappers -------------------------------------------------

    def getblockchaininfo(self) -> Dict[str, Any]:
        return self.call("getblockchaininfo")

    def getblockhash(self, height: int) -> str:
        return self.call("getblockhash", [height])

    def getblock(self, block_hash: str, verbosity: int = 1) -> Dict[str, Any]:
        return self.call("getblock", [block_hash, verbosity])

    def getrawtransaction(self, txid: str, verbose: bool = False) -> Any:
        return self.call("getrawtransaction", [txid, int(verbose)])

    def decoderawtransaction(self, raw_tx: str) -> Dict[str, Any]:
        return self.call("decoderawtransaction", [raw_tx])

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

    def getnewaddress(self) -> str:
        return self.call("getnewaddress")

    def getbalance(self) -> float:
        return self.call("getbalance")

    def createrawtransaction(
        self, inputs: list[Dict[str, Any]], outputs: Dict[str, float]
    ) -> str:
        return self.call("createrawtransaction", [inputs, outputs])

    def fundrawtransaction(self, raw_tx: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params: list[Any] = [raw_tx]
        if options is not None:
            params.append(options)
        return self.call("fundrawtransaction", params)

    def signrawtransactionwithwallet(self, raw_tx: str) -> Dict[str, Any]:
        return self.call("signrawtransactionwithwallet", [raw_tx])

    def sendrawtransaction(self, raw_tx: str) -> str:
        return self.call("sendrawtransaction", [raw_tx])
