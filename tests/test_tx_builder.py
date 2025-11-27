from __future__ import annotations

from enigmatic_dgb.tx_builder import TransactionBuilder


class StubRPC:
    def __init__(self) -> None:
        self.last_outputs = None

    def createrawtransaction(self, inputs, outputs):
        self.last_outputs = outputs
        return "raw"

    def signrawtransactionwithwallet(self, raw_hex):
        assert raw_hex == "raw"
        return {"hex": "signed", "complete": True}


def test_custom_tx_outputs_are_single_key_objects() -> None:
    rpc = StubRPC()
    builder = TransactionBuilder(rpc)  # type: ignore[arg-type]

    outputs_payload = [{"script": "51", "amount": 0.0001}]
    tx_hex = builder.build_custom_tx(
        outputs_payload,
        fee=0.00001,
        inputs=[{"txid": "00" * 32, "vout": 0}],
    )

    assert tx_hex == "signed"
    assert isinstance(rpc.last_outputs, list)
    assert all(len(item) == 1 for item in rpc.last_outputs)
    assert rpc.last_outputs == [{"script": {"hex": "51", "amount": 0.0001}}]
