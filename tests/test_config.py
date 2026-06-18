"""Tests for config loading and precedence — Milestone 3."""

from pathlib import Path

import pytest
import yaml

from dugalaxy.config.loader import load_config
from dugalaxy.config.schema import Config, ConfigError


def _write(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "dugalaxy.config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def test_defaults_when_no_file_or_overrides() -> None:
    config = load_config()
    assert config.provider == "ollama"
    assert config.cost_cap_usd == 2.0


def test_loads_from_file(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"provider": "openai_compatible", "model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"},
    )
    config = load_config(path)
    assert config.provider == "openai_compatible"
    assert config.model == "gpt-4o-mini"
    assert config.api_key_env == "OPENAI_API_KEY"


def test_cli_override_beats_file(tmp_path: Path) -> None:
    path = _write(tmp_path, {"provider": "openai_compatible", "model": "gpt-4o-mini"})
    config = load_config(path, overrides={"model": "gpt-4o"})
    assert config.model == "gpt-4o"  # CLI wins
    assert config.provider == "openai_compatible"  # file value retained


def test_none_override_falls_through_to_file(tmp_path: Path) -> None:
    path = _write(tmp_path, {"model": "deepseek-chat"})
    config = load_config(path, overrides={"model": None, "provider": "anthropic"})
    assert config.model == "deepseek-chat"  # None ignored, file value kept
    assert config.provider == "anthropic"  # supplied override applied


def test_override_beats_default_without_file() -> None:
    config = load_config(overrides={"provider": "anthropic", "model": "claude-3-5-haiku-latest"})
    assert config.provider == "anthropic"
    assert config.model == "claude-3-5-haiku-latest"


def test_missing_file_raises() -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(Path("/no/such/config.yaml"))


def test_bad_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("provider: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(path)


def test_unknown_field_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"provider": "ollama", "modle": "typo"})
    with pytest.raises(ConfigError):
        load_config(path)


def test_invalid_provider_value_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"provider": "not-a-provider"})
    with pytest.raises(ConfigError):
        load_config(path)


def test_negative_cost_cap_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"cost_cap_usd": -1.0})
    with pytest.raises(ConfigError):
        load_config(path)


def test_empty_file_uses_defaults(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert load_config(path) == Config()
