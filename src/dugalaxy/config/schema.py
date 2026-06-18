"""Pydantic models for dugalaxy.config.yaml. Validates provider/model/cap fields.

Config is the *how* (which provider, which model, the cost cap). It is kept
separate from templates (the *what*) so templates stay portable and a non-coding
author never has to touch an API key. Keys are never stored here — only the NAME
of the environment variable that holds one.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dugalaxy.template.errors import DugalaxyError

ProviderName = Literal["openai_compatible", "anthropic", "ollama"]


class ConfigError(DugalaxyError):
    """The runtime config file is missing, unreadable, or invalid."""


class Config(BaseModel):
    """Runtime configuration, merged from defaults, the config file, and CLI flags."""

    model_config = ConfigDict(extra="forbid")  # typos in the config file fail loudly

    provider: ProviderName = "ollama"
    model: str = "llama3.2"
    base_url: str | None = None
    api_key_env: str | None = None
    cost_cap_usd: float = Field(default=2.0, ge=0.0)
    # Optional honest pricing override (USD per 1k tokens); the engine ships a
    # best-effort table, but providers change prices, so this always wins.
    price_per_1k_input: float | None = Field(default=None, ge=0.0)
    price_per_1k_output: float | None = Field(default=None, ge=0.0)
