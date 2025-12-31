from pathlib import Path

from enigmatic_dgb import cli


def test_lint_dialect_warns_on_reserved_marker_reuse(tmp_path: Path) -> None:
    dialect = {
        "name": "test",
        "symbols": [
            {
                "name": "CUSTOM_FRAME",
                "match": {
                    "value": "21.21",
                    "fee": "0.21",
                    "m": 21,
                    "n": 21,
                    "delta": 3,
                },
            }
        ],
    }
    path = tmp_path / "dialect.yaml"
    path.write_text(cli.yaml.safe_dump(dialect))

    report = cli._lint_dialect_file(path)

    assert not report["errors"]
    assert "FRAME_SYNC" in report["reserved"]
    assert any("reserved marker" in warning for warning in report["warnings"])


def test_discover_dialect_paths_merges_user_dirs(tmp_path: Path) -> None:
    custom = tmp_path / "dialects"
    custom.mkdir()
    (custom / "dialect-custom.yaml").write_text("name: sample\nsymbols: {}")

    results = cli._discover_dialect_paths([str(custom)])

    assert any(path.name == "dialect-custom.yaml" for path in results)
