from decimal import Decimal

import pytest

from enigmatic_dgb import cli
from enigmatic_dgb.planner import plan_explicit_pattern


class SequenceRPC:
    def __init__(self) -> None:
        self._change_index = 0

    def listunspent(self, minconf: int) -> list[dict[str, object]]:  # pragma: no cover - deterministic data
        return [
            {"txid": "funding-a", "vout": 0, "amount": "250.0", "spendable": True},
            {"txid": "funding-b", "vout": 1, "amount": "125.0", "spendable": True},
        ]

    def getrawchangeaddress(self) -> str:  # pragma: no cover - deterministic data
        addr = f"change-{self._change_index}"
        self._change_index += 1
        return addr


class RecordingBuilder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def send_payment_tx(self, outputs, fee, op_return_data=None, inputs=None):
        self.calls.append(
            {
                "outputs": outputs,
                "fee": fee,
                "op_return": op_return_data,
                "inputs": inputs,
            }
        )
        return f"txid-{len(self.calls)}"


@pytest.mark.parametrize(
    "ascii_values, expected",
    [
        ("A,B", ["41", "42"]),
        (None, [None, None]),
    ],
)
def test_parse_op_return_args_handles_ascii(ascii_values, expected):
    result = cli._parse_op_return_args(None, ascii_values, len(expected))
    assert result == expected


def test_execute_sequence_plan_attaches_op_return_and_change_chains():
    rpc = SequenceRPC()
    plan = plan_explicit_pattern(
        rpc,
        to_address="DTdest",
        amounts=[Decimal("10"), Decimal("5")],
        fee=Decimal("0.21"),
    )
    builder = RecordingBuilder()
    op_returns = cli._parse_op_return_args("aa,bb", None, len(plan.steps))
    txids = cli._execute_sequence_plan(builder, plan, op_returns)

    assert txids == ["txid-1", "txid-2"]
    assert len(builder.calls) == 2
    first_call = builder.calls[0]
    assert first_call["op_return"] == ["aa"]
    assert len(first_call["inputs"]) == len(plan.steps[0].inputs)
    second_call = builder.calls[1]
    assert second_call["op_return"] == ["bb"]
    assert second_call["inputs"][0]["txid"] == "txid-1"
    assert second_call["inputs"][0]["vout"] == 1
