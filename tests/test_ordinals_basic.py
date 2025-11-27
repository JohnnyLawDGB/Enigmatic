from __future__ import annotations

from dataclasses import dataclass

from enigmatic_dgb.ordinals.indexer import OrdinalIndexer, OrdinalLocation, OrdinalScanConfig
from enigmatic_dgb.ordinals.inscriptions import InscriptionPayload, OrdinalInscriptionDecoder


@dataclass
class MockRPC:
    block: dict
    verbose_tx: dict

    def get_best_height(self) -> int:
        return int(self.block.get("height", 0))

    def getblock_by_height(self, height: int) -> dict:
        assert height == self.block.get("height")
        return self.block

    def get_raw_transaction(self, txid: str, verbose: bool = False) -> dict:
        assert txid == self.verbose_tx.get("txid")
        return self.verbose_tx


def _build_mock_data(message: str = "hello-enigmatic") -> tuple[MockRPC, str, str]:
    data_hex = message.encode().hex()
    txid = "tx-ordinal-op-return"
    vout = {
        "n": 0,
        "value": 0,
        "scriptPubKey": {
            "asm": f"OP_RETURN {data_hex}",
            "hex": f"6a{data_hex}",
            "type": "nulldata",
        },
    }
    tx = {"txid": txid, "vout": [vout]}
    block = {"height": 42, "tx": [tx]}
    verbose_tx = {"txid": txid, "vin": [], "vout": [vout], "height": block["height"]}

    return MockRPC(block=block, verbose_tx=verbose_tx), txid, data_hex


def test_scan_range_identifies_op_return_inscription() -> None:
    rpc, txid, _ = _build_mock_data()
    indexer = OrdinalIndexer(rpc)
    config = OrdinalScanConfig(start_height=rpc.get_best_height(), end_height=rpc.get_best_height(), limit=None)

    locations = indexer.scan_range(config)

    assert len(locations) == 1
    location = locations[0]
    assert isinstance(location, OrdinalLocation)
    assert location.txid == txid
    assert location.vout == 0
    assert location.ordinal_hint == "op_return"
    assert "op_return" in location.tags
    assert "inscription_candidate" in location.tags


def test_decode_from_tx_extracts_op_return_payload() -> None:
    rpc, txid, data_hex = _build_mock_data()
    decoder = OrdinalInscriptionDecoder(rpc)

    payloads = decoder.decode_from_tx(txid)

    assert len(payloads) == 1
    payload = payloads[0]
    assert isinstance(payload, InscriptionPayload)
    assert payload.raw_payload == bytes.fromhex(data_hex)
    assert payload.decoded_text is not None
    assert "hello-enigmatic" in payload.decoded_text
    assert payload.metadata.location.txid == txid
    assert "op_return" in payload.metadata.location.tags
