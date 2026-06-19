"""Ollama / local adapter. The fully offline SLM path; the cheap/bulk and on-prem default.

No API key: it talks to a local Ollama server, so nothing leaves the machine.
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


class OllamaProvider(TextProvider):
    """Calls a local Ollama server's ``/api/chat`` endpoint (no auth)."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        client: httpx.Client | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/api/chat"
        self.fingerprint = f"ollama|{self._url}|{model}"
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, request: CompletionRequest) -> Completion:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        payload: dict[str, object] = {"model": self.model, "messages": messages, "stream": False}
        if request.max_tokens is not None:
            payload["options"] = {"num_predict": request.max_tokens}

        data = post_json(
            self._client,
            self._url,
            headers={"Content-Type": "application/json"},
            payload=payload,
            provider_name="ollama",
            connect_hint=(
                "Ollama doesn't appear to be running. Start it (and `ollama pull "
                f"{self.model}`), pick another provider with --provider/--model, or run "
                "`dugalaxy gen quickstart` (no model needed)."
            ),
        )
        try:
            text = data["message"]["content"]
            return Completion(
                text=str(text),
                usage=Usage(
                    input_tokens=int(data.get("prompt_eval_count", 0)),
                    output_tokens=int(data.get("eval_count", 0)),
                ),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"ollama: unexpected response shape: {exc}") from exc
