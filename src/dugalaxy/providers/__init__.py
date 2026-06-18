"""Provider layer. A single internal TextProvider interface with thin adapters.

'LLM vs SLM' and 'bring your own key' are configuration (provider/model/api_key/base_url),
never separate code paths.
"""

import httpx

from dugalaxy.config.schema import Config

from .anthropic import AnthropicProvider
from .base import (
    Completion,
    CompletionRequest,
    Message,
    ProviderError,
    TextProvider,
    Usage,
    resolve_api_key,
)
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider

# Default endpoints, used when config.base_url is not set.
DEFAULT_BASE_URLS: dict[str, str] = {
    "openai_compatible": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "ollama": "http://localhost:11434",
}

__all__ = [
    "AnthropicProvider",
    "Completion",
    "CompletionRequest",
    "Message",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "ProviderError",
    "TextProvider",
    "Usage",
    "build_provider",
    "resolve_api_key",
]


def build_provider(config: Config, *, client: httpx.Client | None = None) -> TextProvider:
    """Construct the configured provider, resolving its API key from the environment.

    Ollama needs no key. The other providers require ``api_key_env`` to name the
    environment variable holding the key. Raises :class:`ProviderError` otherwise.
    """
    base_url = config.base_url or DEFAULT_BASE_URLS[config.provider]

    if config.provider == "ollama":
        return OllamaProvider(model=config.model, base_url=base_url, client=client)

    if not config.api_key_env:
        raise ProviderError(
            f"Provider '{config.provider}' requires 'api_key_env' "
            f"(the name of the environment variable holding the API key)."
        )
    api_key = resolve_api_key(config.api_key_env)

    if config.provider == "openai_compatible":
        return OpenAICompatibleProvider(
            model=config.model, base_url=base_url, api_key=api_key, client=client
        )
    if config.provider == "anthropic":
        return AnthropicProvider(
            model=config.model, base_url=base_url, api_key=api_key, client=client
        )

    raise ProviderError(f"Unknown provider: {config.provider}")  # pragma: no cover
