"""Load and merge configuration sources, applying the documented precedence order.

Precedence (highest first): CLI flags > config file > built-in defaults. Provider
and model settings live here or on the CLI — never in templates.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .schema import Config, ConfigError


def load_config(
    path: Path | None = None,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> Config:
    """Build a :class:`Config` from an optional file plus CLI *overrides*.

    A ``None`` value in *overrides* means "not supplied on the CLI" and is ignored,
    so it falls through to the file value, then the built-in default.

    Raises:
        ConfigError: the file is missing, not valid YAML, or fails validation.
    """
    data: dict[str, Any] = {}

    if path is not None:
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in '{path}': {exc}") from exc
        if raw is not None:
            if not isinstance(raw, dict):
                raise ConfigError(f"Config '{path}' must be a mapping, got {type(raw).__name__}")
            data.update(raw)

    if overrides:
        data.update({key: value for key, value in overrides.items() if value is not None})

    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration:\n{exc}") from exc
