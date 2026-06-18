"""The TextProvider interface that every adapter implements.

The generator depends ONLY on this interface, never on a concrete provider.
'LLM vs SLM' and 'bring your own key' are configuration, not separate code paths,
so every adapter speaks the same small request/response vocabulary defined here.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from dugalaxy.template.errors import DugalaxyError


class ProviderError(DugalaxyError):
    """A provider call failed, returned an error, or sent an unexpected response."""


@dataclass(frozen=True)
class Message:
    """One chat message handed to the model."""

    role: str
    content: str


@dataclass(frozen=True)
class CompletionRequest:
    """A request for one completion: an optional system prompt + the messages."""

    system: str | None
    messages: tuple[Message, ...]
    max_tokens: int | None = None


@dataclass(frozen=True)
class Usage:
    """Token accounting reported by the provider (0 when unknown)."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Completion:
    """The model's reply plus its token usage."""

    text: str
    usage: Usage = field(default_factory=Usage)


class TextProvider(ABC):
    """The one interface the generator talks to. Concrete adapters set ``model``."""

    model: str

    @abstractmethod
    def complete(self, request: CompletionRequest) -> Completion:
        """Produce one completion for *request* (raises :class:`ProviderError` on failure)."""


def resolve_api_key(env_var: str) -> str:
    """Read an API key from the named environment variable.

    Keys are resolved from the environment only — never read from or written to
    disk, never logged. Raises :class:`ProviderError` with a legible message if the
    variable is unset or empty.
    """
    key = os.environ.get(env_var)
    if not key:
        raise ProviderError(
            f"API key environment variable '{env_var}' is not set. "
            f"Export it before running; Dugalaxy never reads keys from disk."
        )
    return key


def post_json(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    provider_name: str,
) -> dict[str, Any]:
    """POST *payload* as JSON and return the decoded object, mapping failures to ProviderError."""
    try:
        response = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise ProviderError(f"{provider_name}: request to {url} failed: {exc}") from exc

    if response.status_code >= 400:
        raise ProviderError(
            f"{provider_name}: HTTP {response.status_code} from {url}: {response.text[:500]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError(f"{provider_name}: response was not valid JSON") from exc

    if not isinstance(data, dict):
        raise ProviderError(f"{provider_name}: expected a JSON object, got {type(data).__name__}")
    return data
