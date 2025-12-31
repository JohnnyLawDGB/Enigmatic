from typing import Any

from enigmatic_dgb import cli
from enigmatic_dgb.config import RPCConfig


def test_quickstart_menu_runs_dry_run_command(monkeypatch) -> None:
    inputs = ["1", "b"]
    prompt_values = ["dgb1address", "presence", "default", "{}"]
    recorded: list[list[str]] = []

    def fake_input(_: str = "") -> str:
        return inputs.pop(0) if inputs else "b"

    def fake_prompt_str(*_: Any, default: str | None = None) -> str:
        return prompt_values.pop(0) if prompt_values else (default or "")

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(cli, "_prompt_str", fake_prompt_str)
    monkeypatch.setattr(cli, "_prompt_bool", lambda *_, **__: False)
    monkeypatch.setattr(cli, "_run_cli_command", recorded.append)

    rpc_config = RPCConfig(user="u", password="p")

    cli._quickstart_menu(rpc_config)

    assert recorded, "expected quickstart to invoke CLI commands"
    dry_run_args = recorded[0]
    assert dry_run_args[0] == "send-message"
    assert "--dry-run" in dry_run_args
