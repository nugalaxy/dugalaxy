"""Tests for cost estimation, cap enforcement, and the response cache — Milestone 3."""

from pathlib import Path

import pytest

from dugalaxy.config.schema import Config
from dugalaxy.cost.cache import ResponseCache
from dugalaxy.cost.estimator import (
    CostCapExceededError,
    enforce_cap,
    estimate_run_cost,
    estimate_tokens,
    resolve_pricing,
)
from dugalaxy.providers.base import Completion, CompletionRequest, Message, Usage

# ── token + pricing ───────────────────────────────────────────────────────────


def test_estimate_tokens_roughly_chars_over_four() -> None:
    assert estimate_tokens("a" * 40) == 10
    assert estimate_tokens("") == 1  # never zero


def test_resolve_pricing_ollama_is_free() -> None:
    price_in, price_out, priced = resolve_pricing("ollama", "llama3.2", Config(provider="ollama"))
    assert (price_in, price_out, priced) == (0.0, 0.0, True)


def test_resolve_pricing_config_override_wins() -> None:
    config = Config(
        provider="openai_compatible",
        model="gpt-4o-mini",
        price_per_1k_input=0.001,
        price_per_1k_output=0.002,
    )
    assert resolve_pricing("openai_compatible", "gpt-4o-mini", config) == (0.001, 0.002, True)


def test_resolve_pricing_known_model_from_table() -> None:
    price_in, price_out, priced = resolve_pricing(
        "openai_compatible", "gpt-4o-mini", Config(provider="openai_compatible")
    )
    assert priced is True
    assert price_in > 0 and price_out > 0


def test_resolve_pricing_unknown_model_flagged_not_priced() -> None:
    price_in, price_out, priced = resolve_pricing(
        "openai_compatible", "some-new-model", Config(provider="openai_compatible")
    )
    assert (price_in, price_out, priced) == (0.0, 0.0, False)


# ── run-cost math + cap ───────────────────────────────────────────────────────


def test_estimate_run_cost_math() -> None:
    estimate = estimate_run_cost(
        n=100,
        input_tokens_per_sample=1000,
        output_tokens_per_sample=500,
        price_per_1k_input=0.001,
        price_per_1k_output=0.002,
        priced=True,
        free=False,
    )
    assert estimate.total_input_tokens == 100_000
    assert estimate.total_output_tokens == 50_000
    # 100 input units * 0.001 + 50 output units * 0.002 = 0.1 + 0.1 = 0.2
    assert estimate.estimated_cost_usd == pytest.approx(0.2)


def test_enforce_cap_raises_when_over() -> None:
    estimate = estimate_run_cost(
        n=1000,
        input_tokens_per_sample=1000,
        output_tokens_per_sample=1000,
        price_per_1k_input=0.01,
        price_per_1k_output=0.01,
        priced=True,
        free=False,
    )
    with pytest.raises(CostCapExceededError):
        enforce_cap(estimate, cap_usd=2.0)


def test_enforce_cap_passes_when_under() -> None:
    estimate = estimate_run_cost(
        n=10,
        input_tokens_per_sample=100,
        output_tokens_per_sample=100,
        price_per_1k_input=0.001,
        price_per_1k_output=0.001,
        priced=True,
        free=False,
    )
    enforce_cap(estimate, cap_usd=2.0)  # no raise


def test_enforce_cap_skips_free_runs() -> None:
    estimate = estimate_run_cost(
        n=1_000_000,
        input_tokens_per_sample=1000,
        output_tokens_per_sample=1000,
        price_per_1k_input=0.0,
        price_per_1k_output=0.0,
        priced=True,
        free=True,
    )
    enforce_cap(estimate, cap_usd=0.0)  # free => always passes


def test_enforce_cap_skips_unpriced_runs() -> None:
    estimate = estimate_run_cost(
        n=1000,
        input_tokens_per_sample=1000,
        output_tokens_per_sample=1000,
        price_per_1k_input=0.0,
        price_per_1k_output=0.0,
        priced=False,
        free=False,
    )
    enforce_cap(estimate, cap_usd=0.0)  # unknown pricing => cannot meaningfully check


# ── response cache ────────────────────────────────────────────────────────────

REQUEST = CompletionRequest(
    system="sys",
    messages=(Message("user", "hello"),),
    max_tokens=100,
)


FINGERPRINT = "openai_compatible|https://api.openai.com/v1/chat/completions|gpt-4o-mini"


def test_cache_key_is_stable_and_input_sensitive() -> None:
    key = ResponseCache.make_key(REQUEST, FINGERPRINT)
    assert key == ResponseCache.make_key(REQUEST, FINGERPRINT)
    other = CompletionRequest(
        system="sys", messages=(Message("user", "different"),), max_tokens=100
    )
    assert key != ResponseCache.make_key(other, FINGERPRINT)


def test_cache_key_distinguishes_backends_with_same_model() -> None:
    """Same model string, different endpoints => different keys (no collision)."""
    fp_a = "openai_compatible|https://api.openai.com/v1/chat/completions|llama3.2"
    fp_b = "openai_compatible|https://my-proxy.local/v1/chat/completions|llama3.2"
    assert ResponseCache.make_key(REQUEST, fp_a) != ResponseCache.make_key(REQUEST, fp_b)


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "cache")
    assert cache.get(ResponseCache.make_key(REQUEST, FINGERPRINT)) is None


def test_cache_hit_roundtrips_completion(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "cache")
    key = ResponseCache.make_key(REQUEST, FINGERPRINT)
    completion = Completion(text="cached reply", usage=Usage(input_tokens=11, output_tokens=4))
    cache.put(key, completion)

    hit = cache.get(key)
    assert hit is not None
    assert hit.text == "cached reply"
    assert hit.usage.input_tokens == 11
    assert hit.usage.output_tokens == 4


def test_cache_persists_across_instances(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    key = ResponseCache.make_key(REQUEST, FINGERPRINT)
    ResponseCache(directory).put(key, Completion(text="persisted"))
    # A fresh cache pointed at the same dir still sees it (survives across runs).
    assert ResponseCache(directory).get(key) is not None


def test_cache_corrupted_entry_is_treated_as_miss(tmp_path: Path) -> None:
    """A partial write (e.g. a crash mid-run) must degrade to a miss, not crash."""
    cache = ResponseCache(tmp_path / "cache")
    key = ResponseCache.make_key(REQUEST, FINGERPRINT)
    (tmp_path / "cache" / f"{key}.json").write_text('{"text": "half', encoding="utf-8")
    assert cache.get(key) is None
    # And the entry can be rewritten cleanly afterwards.
    cache.put(key, Completion(text="recovered"))
    hit = cache.get(key)
    assert hit is not None and hit.text == "recovered"


def test_cache_put_leaves_no_temp_files(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    cache = ResponseCache(directory)
    cache.put(ResponseCache.make_key(REQUEST, FINGERPRINT), Completion(text="x"))
    assert list(directory.glob("*.tmp")) == []
