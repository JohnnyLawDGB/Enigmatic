import pytest

from enigmatic_dgb import ordinals
from enigmatic_dgb.ordinals import workflows
from enigmatic_dgb.rpc_client import RPCError


class StubRPC:
    def __init__(self, send_error: bool = False) -> None:
        self.send_error = send_error

    def getmempoolinfo(self):
        return {"mempoolminfee": 0.00001}

    def getnetworkinfo(self):
        return {"relayfee": 0.00001, "incrementalfee": 0.00001}

    def estimatesmartfee(self, *_args, **_kwargs):
        return {"feerate": 0.00005}

    def sendrawtransaction(self, _raw: str):
        if self.send_error:
            raise RPCError(-26, "min relay fee not met")
        return "txid123"

    def decoderawtransaction(self, _raw: str):
        return {"vsize": 400}

    def getnewaddress(self, **_kwargs):
        return "dgb1address"


class StubBuilder:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def build_payment_tx(self, *_args, **_kwargs) -> str:
        return "rawtx"


class StubPlanner:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def plan_op_return_inscription(self, _payload, *, metadata):
        return {"metadata": {"estimated_fee": metadata.get("estimated_fee", 0.0001)}}


@pytest.fixture(autouse=True)
def patch_workflow_dependencies(monkeypatch):
    monkeypatch.setattr(workflows, "TransactionBuilder", StubBuilder)
    monkeypatch.setattr(workflows, "OrdinalInscriptionPlanner", StubPlanner)
    yield


def test_prepare_inscription_respects_max_fee_cap():
    rpc = StubRPC()

    with pytest.raises(ordinals.workflows.InscriptionFlowError) as excinfo:
        workflows.prepare_inscription_transaction(
            rpc,
            b"payload",
            "text/plain",
            scheme="op-return",
            max_fee_sats=10,
            broadcast=True,
        )

    assert "exceeds max-fee-sats" in str(excinfo.value)


def test_prepare_inscription_surfaces_rpc_hint(monkeypatch):
    rpc = StubRPC(send_error=True)

    with pytest.raises(ordinals.workflows.InscriptionFlowError) as excinfo:
        workflows.prepare_inscription_transaction(
            rpc,
            b"payload",
            "text/plain",
            scheme="op-return",
            max_fee_sats=5_000_000,
            broadcast=True,
        )

    message = str(excinfo.value)
    assert "Broadcast failed" in message
    assert "Hint: The node rejected the transaction because the fee is below its minrelaytxfee policy." in message
