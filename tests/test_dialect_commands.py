from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from enigmatic_dgb import cli


def test_cmd_dialect_list_prints_paths(tmp_path: Path, capsys) -> None:
    dialect_root = tmp_path / "dialects"
    dialect_root.mkdir()
    dialect_file = dialect_root / "dialect-sample.yaml"
    dialect_file.write_text("name: sample\nsymbols: {}")

    cli.cmd_dialect_list(SimpleNamespace(dialect_dirs=[str(dialect_root)]))

    output = capsys.readouterr().out
    assert "Discovered dialect files:" in output
    assert "dialect-sample.yaml" in output


def test_cmd_dialect_validate_reports_reserved_marker(tmp_path: Path, capsys) -> None:
    dialect_file = tmp_path / "dialect.yaml"
    dialect_file.write_text(
        """
        name: sample
        symbols:
          HEARTBEAT:
            match:
              value: 21.21
              fee: 0.21
              m: 21
              n: 21
              delta: 3
        """
    )

    cli.cmd_dialect_validate(SimpleNamespace(path=str(dialect_file)))

    output = capsys.readouterr().out
    assert "is structurally valid" in output
    assert "Reserved marker alignment" in output


def test_cmd_dialect_generate_writes_template(tmp_path: Path, monkeypatch, capsys) -> None:
    output_path = tmp_path / "generated.yaml"
    values = [
        "custom-name",
        "Custom description",
        "SYMBOL_ONE",
        "Symbol description",
    ]

    monkeypatch.setattr(cli, "_prompt_str", lambda *_args, default=None: values.pop(0) if values else str(default or ""))
    monkeypatch.setattr(cli, "_prompt_decimal_sequence", lambda *_args, **__: [Decimal("1.23")])

    cli.cmd_dialect_generate(SimpleNamespace(output_path=str(output_path), force=True))

    body = output_path.read_text()
    output = capsys.readouterr().out
    assert "custom-name" in body
    assert "SYMBOL_ONE" in body
    assert str(output_path) in output
