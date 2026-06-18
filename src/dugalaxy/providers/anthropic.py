"""Anthropic Messages API adapter."""

import httpx

from .base import (
    Completion,
    CompletionRequest,
    ProviderError,
    TextProvider,
    Usage,
    post_json,
)

# Anthropic requires max_tokens; used when the request does not specify one.
_DEFAULT_MAX_TOKENS = 1024


class AnthropicProvider(TextProvider):
    """Calls the ``/v1/messages`` endpoint with the system prompt as a top-level field."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
        api_version: str = "2023-06-01",
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/v1/messages"
        self.fingerprint = f"anthropic|{self._url}|{model}"
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": api_version,
            "content-type": "application/json",
        }
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, request: CompletionRequest) -> Completion:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_tokens or _DEFAULT_MAX_TOKENS,
        }
        if request.system:
            payload["system"] = request.system

        data = post_json(
            self._client,
            self._url,
            headers=self._headers,
            payload=payload,
            provider_name="anthropic",
        )
        try:
            text = data["content"][0]["text"]
            usage = data.get("usage") or {}
            return Completion(
                text=str(text),
                usage=Usage(
                    input_tokens=int(usage.get("input_tokens", 0)),
                    output_tokens=int(usage.get("output_tokens", 0)),
                ),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"anthropic: unexpected response shape: {exc}") from exc
