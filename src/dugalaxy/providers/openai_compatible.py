"""OpenAI-compatible adapter (OpenAI, DeepSeek, Together, Groq) via configurable base_url.

Gemini is reached through this adapter too — point ``base_url`` at Google's
OpenAI-compatible endpoint and use a ``gemini-*`` model. No separate adapter needed.
"""

import httpx

from .base import (
    Completion,
    CompletionRequest,
    ProviderError,
    TextProvider,
    Usage,
    post_json,
)


class OpenAICompatibleProvider(TextProvider):
    """Calls a ``/chat/completions`` endpoint with Bearer auth."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self.fingerprint = f"openai_compatible|{self._url}|{model}"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, request: CompletionRequest) -> Completion:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        payload: dict[str, object] = {"model": self.model, "messages": messages}
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        data = post_json(
            self._client,
            self._url,
            headers=self._headers,
            payload=payload,
            provider_name="openai_compatible",
        )
        try:
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            return Completion(
                text=str(text),
                usage=Usage(
                    input_tokens=int(usage.get("prompt_tokens", 0)),
                    output_tokens=int(usage.get("completion_tokens", 0)),
                ),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"openai_compatible: unexpected response shape: {exc}") from exc
