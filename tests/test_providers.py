"""Tests for the provider layer — Milestone 3. Calls are mocked; no network."""

import json
from typing import Any

import httpx
import pytest

from dugalaxy.config.schema import Config
from dugalaxy.providers import (
    AnthropicProvider,
    CompletionRequest,
    Message,
    OllamaProvider,
    OpenAICompatibleProvider,
    ProviderError,
    build_provider,
    resolve_api_key,
)

REQUEST = CompletionRequest(
    system="You are a SOC analyst.",
    messages=(Message(role="user", content="Triage this alert."),),
    max_tokens=200,
)


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# ── openai-compatible ─────────────────────────────────────────────────────────


def test_openai_compatible_builds_request_and_parses_response() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Looks malicious."}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )

    provider = OpenAICompatibleProvider(
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        client=_client(handler),
    )
    result = provider.complete(REQUEST)

    assert result.text == "Looks malicious."
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 5
    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer sk-test"
    assert captured["body"]["model"] == "gpt-4o-mini"
    assert captured["body"]["messages"][0] == {
        "role": "system",
        "content": "You are a SOC analyst.",
    }
    assert captured["body"]["max_tokens"] == 200


def test_openai_compatible_http_error_raises_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    provider = OpenAICompatibleProvider(
        model="m", base_url="https://x/v1", api_key="bad", client=_client(handler)
    )
    with pytest.raises(ProviderError, match="401"):
        provider.complete(REQUEST)


def test_openai_compatible_unexpected_shape_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nope": True})

    provider = OpenAICompatibleProvider(
        model="m", base_url="https://x/v1", api_key="k", client=_client(handler)
    )
    with pytest.raises(ProviderError, match="unexpected response shape"):
        provider.complete(REQUEST)


# ── anthropic ─────────────────────────────────────────────────────────────────


def test_anthropic_uses_top_level_system_and_parses_content() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("x-api-key")
        captured["version"] = request.headers.get("anthropic-version")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Escalate to tier 2."}],
                "usage": {"input_tokens": 30, "output_tokens": 8},
            },
        )

    provider = AnthropicProvider(
        model="claude-3-5-haiku-latest",
        base_url="https://api.anthropic.com",
        api_key="sk-ant",
        client=_client(handler),
    )
    result = provider.complete(REQUEST)

    assert result.text == "Escalate to tier 2."
    assert result.usage.input_tokens == 30
    assert result.usage.output_tokens == 8
    assert captured["url"].endswith("/v1/messages")
    assert captured["key"] == "sk-ant"
    assert captured["version"]
    assert captured["body"]["system"] == "You are a SOC analyst."
    assert captured["body"]["max_tokens"] == 200


def test_anthropic_defaults_max_tokens_when_absent() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"text": "ok"}], "usage": {}})

    provider = AnthropicProvider(
        model="m", base_url="https://x", api_key="k", client=_client(handler)
    )
    provider.complete(CompletionRequest(system=None, messages=(Message("user", "hi"),)))
    assert captured["body"]["max_tokens"] > 0
    assert "system" not in captured["body"]


# ── ollama ────────────────────────────────────────────────────────────────────


def test_ollama_no_auth_and_parses_message() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Benign."},
                "prompt_eval_count": 40,
                "eval_count": 3,
            },
        )

    provider = OllamaProvider(
        model="llama3.2", base_url="http://localhost:11434", client=_client(handler)
    )
    result = provider.complete(REQUEST)

    assert result.text == "Benign."
    assert result.usage.input_tokens == 40
    assert result.usage.output_tokens == 3
    assert captured["url"].endswith("/api/chat")
    assert captured["auth"] is None
    assert captured["body"]["stream"] is False
    assert captured["body"]["options"]["num_predict"] == 200


def test_ollama_connection_error_is_friendly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = OllamaProvider(
        model="llama3.2", base_url="http://localhost:11434", client=_client(handler)
    )
    with pytest.raises(ProviderError, match="Ollama doesn't appear to be running"):
        provider.complete(REQUEST)


# ── api key resolution ────────────────────────────────────────────────────────


def test_resolve_api_key_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUGALAXY_TEST_KEY", "secret-value")
    assert resolve_api_key("DUGALAXY_TEST_KEY") == "secret-value"


def test_resolve_api_key_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUGALAXY_TEST_KEY", raising=False)
    with pytest.raises(ProviderError, match="not set"):
        resolve_api_key("DUGALAXY_TEST_KEY")


# ── factory ───────────────────────────────────────────────────────────────────


def test_build_provider_ollama_needs_no_key() -> None:
    provider = build_provider(Config(provider="ollama", model="llama3.2"))
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "llama3.2"


def test_build_provider_openai_resolves_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    config = Config(provider="openai_compatible", model="gpt-4o-mini", api_key_env="OPENAI_API_KEY")
    provider = build_provider(config)
    assert isinstance(provider, OpenAICompatibleProvider)


def test_build_provider_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    config = Config(
        provider="anthropic", model="claude-3-5-haiku-latest", api_key_env="ANTHROPIC_API_KEY"
    )
    assert isinstance(build_provider(config), AnthropicProvider)


def test_build_provider_paid_without_api_key_env_raises() -> None:
    config = Config(provider="openai_compatible", model="gpt-4o-mini", api_key_env=None)
    with pytest.raises(ProviderError, match="api_key_env"):
        build_provider(config)
