from __future__ import annotations

from dataclasses import dataclass

from enigmatic_dgb.ordinals.indexer import OrdinalIndexer
from enigmatic_dgb.ordinals.inscriptions import (
    ENIG_TAPROOT_PROTOCOL,
    InscriptionPayload,
    OrdinalInscriptionDecoder,
    encode_enig_taproot_payload,
)


MESSAGE_TEXT = "hello-enig-taproot"
CONTENT_TYPE = "text/plain"


@dataclass
class MockRPC:
    block: dict
    verbose_tx: dict

    def get_best_height(self) -> int:
        return int(self.block.get("height", 0))

    def getblock_by_height(self, height: int) -> dict:
        assert height == self.block.get("height")
        return self.block

    def getrawtransaction(self, txid: str, verbose: bool = False) -> dict:
        assert txid == self.verbose_tx.get("txid")
        return self.verbose_tx


def _build_taproot_mock_data() -> tuple[MockRPC, str, bytes]:
    envelope = encode_enig_taproot_payload(CONTENT_TYPE, MESSAGE_TEXT.encode())

    # Assemble OP_FALSE OP_IF <envelope> OP_ENDIF leaf script
    leaf_script = b"\x00\x63" + bytes([len(envelope)]) + envelope + b"\x68"
    leaf_script_hex = leaf_script.hex()

    control_block_hex = "c0" + ("11" * 64)  # simple heuristic-matching control block

    internal_key_hex = "aa" * 32
    script_pubkey_hex = "5120" + internal_key_hex
    vout = {
        "n": 0,
        "value": 1,
        "scriptPubKey": {
            "asm": f"OP_1 {internal_key_hex}",
            "hex": script_pubkey_hex,
            "type": "witness_v1_taproot",
        },
    }

    txid = "taproot-dialect-v1"
    verbose_tx = {
        "txid": txid,
        "vin": [{"txinwitness": [control_block_hex, leaf_script_hex]}],
        "vout": [vout],
        "height": 777,
    }
    block = {"height": 777, "tx": [{"txid": txid, "vout": [vout]}]}

    return MockRPC(block=block, verbose_tx=verbose_tx), txid, envelope


def test_scan_tx_detects_enig_taproot_inscription() -> None:
    rpc, txid, _ = _build_taproot_mock_data()

    indexer = OrdinalIndexer(rpc)
    locations = indexer.scan_tx(txid)

    assert len(locations) == 1
    location = locations[0]
    assert location.txid == txid
    assert location.vout == 0
    assert location.ordinal_hint == "enig_taproot"
    assert "enigmatic_inscription" in location.tags
    assert "taproot_v1" in location.tags


def test_decode_taproot_dialect_payload() -> None:
    rpc, txid, envelope = _build_taproot_mock_data()

    decoder = OrdinalInscriptionDecoder(rpc)
    payloads = decoder.decode_from_tx(txid)

    assert len(payloads) == 1
    payload = payloads[0]
    assert isinstance(payload, InscriptionPayload)
    assert MESSAGE_TEXT.encode() in payload.raw_payload
    assert payload.decoded_text is not None
    assert MESSAGE_TEXT in payload.decoded_text

    metadata = payload.metadata
    assert metadata.protocol == ENIG_TAPROOT_PROTOCOL
    assert metadata.content_type == CONTENT_TYPE
    assert metadata.version == 1
    assert metadata.location.txid == txid
    assert metadata.location.ordinal_hint == "enig_taproot"
