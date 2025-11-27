"""Experimental ordinal-style tooling for DigiByte.

This subpackage provides non-consensus helpers for discovering and decoding
ordinal-style inscriptions on the DigiByte blockchain. APIs are experimental
and subject to change. The Enigmatic Taproot dialect v1 described in
``docs/taproot-dialect-v1.md`` is exposed here for discoverability.
"""

from enigmatic_dgb.ordinals.index_store import OrdinalIndexStore, SQLiteOrdinalIndexStore
from enigmatic_dgb.ordinals.indexer import OrdinalIndexer, OrdinalLocation, OrdinalScanConfig
from enigmatic_dgb.ordinals.inscriptions import (
    ENIG_TAPROOT_MAGIC,
    ENIG_TAPROOT_PROTOCOL,
    ENIG_TAPROOT_VERSION_V1,
    InscriptionMetadata,
    InscriptionPayload,
    OrdinalInscriptionDecoder,
    OrdinalInscriptionPlanner,
    decode_enig_taproot_payload,
    encode_enig_taproot_payload,
)
from enigmatic_dgb.ordinals.ownership import OrdinalOwnershipView
from enigmatic_dgb.ordinals.taproot import TaprootScriptView, inspect_output_for_taproot

__all__ = [
    "OrdinalIndexer",
    "OrdinalLocation",
    "OrdinalScanConfig",
    "OrdinalIndexStore",
    "SQLiteOrdinalIndexStore",
    "OrdinalInscriptionDecoder",
    "OrdinalInscriptionPlanner",
    "OrdinalOwnershipView",
    "InscriptionMetadata",
    "InscriptionPayload",
    "encode_enig_taproot_payload",
    "decode_enig_taproot_payload",
    "ENIG_TAPROOT_MAGIC",
    "ENIG_TAPROOT_VERSION_V1",
    "ENIG_TAPROOT_PROTOCOL",
    "TaprootScriptView",
    "inspect_output_for_taproot",
]
