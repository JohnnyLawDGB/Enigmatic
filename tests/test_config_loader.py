from pathlib import Path

import pytest

from enigmatic_dgb.config import ConfigurationError, RPCConfig, load_rpc_config


def test_load_rpc_config_prefers_environment_over_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
        rpc:
          user: file_user
          password: file_pass
          host: filehost
          port: 1111
          use_https: true
          wallet: filewallet
          endpoint: http://filehost:2222
        """
    )

    env_map = {
        "DGB_RPC_USER": "env_user",
        "DGB_RPC_PASSWORD": "env_pass",
        "DGB_RPC_ENDPOINT": "https://envhost:3333",
        "DGB_RPC_WALLET": "envwallet",
        "DGB_RPC_USE_HTTPS": "1",
    }

    config = load_rpc_config(config_path=config_path, env=env_map)

    assert isinstance(config, RPCConfig)
    assert config.user == "env_user"
    assert config.password == "env_pass"
    assert config.host == "envhost"
    assert config.port == 3333
    assert config.use_https is True
    assert config.wallet == "envwallet"


def test_load_rpc_config_reads_yaml_when_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / ".enigmatic"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    legacy_path = tmp_path / "legacy.yaml"

    monkeypatch.setattr("enigmatic_dgb.config.DEFAULT_CONFIG_DIR", config_dir)
    monkeypatch.setattr("enigmatic_dgb.config.DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr("enigmatic_dgb.config.LEGACY_CONFIG_PATH", legacy_path)

    config_path.write_text(
        """
        rpc:
          user: yaml_user
          password: yaml_pass
          host: yamlhost
          port: 4545
          use_https: false
          wallet: yamlwallet
        """
    )

    config = load_rpc_config(env={})

    assert config.user == "yaml_user"
    assert config.password == "yaml_pass"
    assert config.host == "yamlhost"
    assert config.port == 4545
    assert config.use_https is False
    assert config.wallet == "yamlwallet"


def test_load_rpc_config_requires_credentials(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("rpc: {}\n")

    with pytest.raises(ConfigurationError):
        load_rpc_config(config_path=config_path, env={})
