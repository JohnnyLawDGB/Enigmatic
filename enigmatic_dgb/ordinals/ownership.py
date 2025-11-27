"""Ownership-focused inscription discovery helpers."""

from __future__ import annotations

import logging
from typing import Iterable, List, Sequence, Set

from enigmatic_dgb.ordinals.indexer import OrdinalIndexer, OrdinalLocation, OrdinalScanConfig
from enigmatic_dgb.ordinals.inscriptions import InscriptionPayload, OrdinalInscriptionDecoder
from enigmatic_dgb.rpc_client import DigiByteRPCClient

logger = logging.getLogger(__name__)


class OrdinalOwnershipView:
    """Locate inscription payloads that pay to specific addresses or wallets."""

    def __init__(self, rpc_client: DigiByteRPCClient) -> None:
        self.rpc_client = rpc_client
        self.indexer = OrdinalIndexer(rpc_client)
        self.decoder = OrdinalInscriptionDecoder(rpc_client)

    def _iter_block_range(self, config: OrdinalScanConfig) -> Iterable[dict]:
        # Delegate to the indexer so future pagination/caching improvements are shared.
        return self.indexer._iter_block_range(config)

    @staticmethod
    def _addresses_from_script(script_pub_key: dict) -> Set[str]:
        addresses: Set[str] = set()
        if not script_pub_key:
            return addresses
        address = script_pub_key.get("address")
        if address:
            addresses.add(address)
        for candidate in script_pub_key.get("addresses", []) or []:
            if candidate:
                addresses.add(candidate)
        return addresses

    def _filter_locations_by_address(
        self, block_json: dict, locations: Sequence[OrdinalLocation], address_set: Set[str]
    ) -> List[OrdinalLocation]:
        if not locations:
            return []
        tx_lookup = {tx.get("txid") or tx.get("hash"): tx for tx in block_json.get("tx", [])}
        matched: List[OrdinalLocation] = []
        for location in locations:
            tx = tx_lookup.get(location.txid)
            if not tx:
                continue
            vouts = tx.get("vout", [])
            matching_vouts = [v for v in vouts if v.get("n") == location.vout]
            if not matching_vouts:
                continue
            script_pub_key = matching_vouts[0].get("scriptPubKey", {})
            if self._addresses_from_script(script_pub_key) & address_set:
                matched.append(location)
        return matched

    def find_inscriptions_for_addresses(
        self, addresses: list[str], scan_config: OrdinalScanConfig | None = None
    ) -> list[InscriptionPayload]:
        """Decode inscriptions paying to any of the supplied addresses."""

        if not addresses:
            return []
        address_set = {addr for addr in addresses if addr}
        if not address_set:
            return []

        config = scan_config or OrdinalScanConfig(
            start_height=None,
            end_height=None,
            limit=50,
            include_op_return=True,
            include_taproot_like=True,
        )

        results: list[InscriptionPayload] = []
        # TODO: accelerate by indexing transactions by address instead of full scans.
        for block_json in self._iter_block_range(config):
            if config.limit is not None and len(results) >= config.limit:
                break
            candidate_locations = self.indexer._scan_block(block_json, config)
            address_filtered = self._filter_locations_by_address(block_json, candidate_locations, address_set)
            for location in address_filtered:
                if config.limit is not None and len(results) >= config.limit:
                    break
                payload = self.decoder.decode_from_location(location)
                if payload:
                    results.append(payload)
        return results

    def find_inscriptions_for_wallet(
        self, wallet_name: str, scan_config: OrdinalScanConfig | None = None
    ) -> list[InscriptionPayload]:
        """Discover inscriptions tied to UTXOs owned by a wallet."""

        if not wallet_name:
            return []

        original_wallet = getattr(self.rpc_client, "_wallet", None)
        self.rpc_client.set_wallet(wallet_name)
        try:
            utxos = self.rpc_client.listunspent()
            wallet_addresses = sorted({u.get("address") for u in utxos if u.get("address")})
        finally:
            # Restore the previous wallet context to avoid surprising callers.
            self.rpc_client.set_wallet(original_wallet)

        return self.find_inscriptions_for_addresses(wallet_addresses, scan_config=scan_config)
