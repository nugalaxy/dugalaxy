"""End-to-end generator pipeline tests — Milestone 4. Providers are fakes; no network."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from dugalaxy.cost.cache import ResponseCache
from dugalaxy.generator.core import GeneratorError, generate_dataset
from dugalaxy.providers.base import Completion, CompletionRequest, ProviderError, TextProvider
from dugalaxy.template.loader import load_template
from dugalaxy.template.spec import TemplateSpec

FLAGSHIP = Path(__file__).parent.parent / "src" / "dugalaxy" / "templates" / "customer-support.yaml"


class FakeProvider(TextProvider):
    """A scripted provider: ``responder(request, call_number)`` returns the reply text."""

    def __init__(self, responder: Callable[[CompletionRequest, int], str]) -> None:
        self.model = "fake-model"
        self.fingerprint = "fake|local|fake-model"
        self._responder = responder
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.calls.append(request)
        return Completion(text=self._responder(request, len(self.calls)))


def _echo(request: CompletionRequest, _call: int) -> str:
    """Return the trailing user message — it contains the grounded facts, and is long."""
    return request.messages[-1].content


def _document_template() -> TemplateSpec:
    return TemplateSpec.model_validate(
        {
            "meta": {
                "name": "det-doc",
                "description": "deterministic log records",
                "version": "1.0",
            },
            "scenario": {"variables": {"host": {"type": "choice", "values": ["h1", "h2"]}}},
            "output": {
                "type": "document",
                "content": {
                    "type": "fixed",
                    "value": {"host": "{{ scenario.host }}", "event": "login"},
                },
            },
            "generation": {"n": 4, "seed": 1, "output_formats": ["jsonl"]},
        }
    )


def test_provider_failure_stops_gracefully_and_keeps_output(tmp_path: Path) -> None:
    # A mid-run provider failure (e.g. an exhausted quota) must stop the run cleanly:
    # samples already written stay on disk, and the run reports what it produced and why
    # it stopped — it does not abort and discard the summary.
    template = load_template(FLAGSHIP)

    def flaky(request: CompletionRequest, call: int) -> str:
        if call >= 3:  # third model call fails, after two samples have completed
            raise ProviderError("openai_compatible: HTTP 429 quota exceeded")
        return request.messages[-1].content

    result = generate_dataset(
        template,
        provider=FakeProvider(flaky),
        n=10,
        seed=42,
        output_dir=tmp_path,
        output_formats=["jsonl"],
    )

    assert result.stopped_early is not None
    assert "429" in result.stopped_early
    assert result.summary.produced == 2
    lines = (tmp_path / "customer-support.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # the two completed samples survived on disk


def test_dropped_sample_reports_why(tmp_path: Path) -> None:
    # When a generated turn fails validation every attempt, the sample is dropped AND the
    # run reports the reason — an empty/blank model reply must not silently vanish.
    template = load_template(FLAGSHIP)

    result = generate_dataset(
        template,
        provider=FakeProvider(lambda r, call: "   "),  # blank reply, always fails validation
        n=1,
        seed=42,
        max_retries=2,
        output_dir=tmp_path,
        output_formats=["jsonl"],
    )

    assert result.summary.produced == 0
    assert result.summary.dropped == 1
    assert result.drop_reasons == ("output is empty",)


def test_on_progress_called_once_per_sample(tmp_path: Path) -> None:
    # The CLI turns this hook into a progress bar; the engine must call it for every
    # processed sample with a monotonically increasing count and a fixed total.
    template = load_template(FLAGSHIP)
    calls: list[tuple[int, int]] = []

    generate_dataset(
        template,
        provider=FakeProvider(_echo),
        n=3,
        seed=42,
        output_dir=tmp_path,
        output_formats=["jsonl"],
        on_progress=lambda done, total: calls.append((done, total)),
    )

    assert calls == [(1, 3), (2, 3), (3, 3)]


# ── the headline acceptance: a valid Echo YAML from the flagship ───────────────


def test_flagship_run_produces_valid_echo_yaml(tmp_path: Path) -> None:
    template = load_template(FLAGSHIP)
    provider = FakeProvider(_echo)

    result = generate_dataset(
        template,
        provider=provider,
        n=3,
        seed=42,
        output_dir=tmp_path,
        output_formats=["jsonl", "yaml"],
    )

    assert result.summary.produced == 3
    assert result.summary.dropped == 0

    envelope = yaml.safe_load((tmp_path / "customer-support.yaml").read_text(encoding="utf-8"))
    assert envelope["version"] == "1.0"
    assert envelope["dataset_name"] == "customer-support"
    assert len(envelope["conversations"]) == 3

    conv = envelope["conversations"][0]
    assert conv["session_id"] == "customer-support_00"
    roles = [turn["role"] for turn in conv["turns"]]
    assert roles == ["user", "agent"]

    # The customer turn is natural prose grounded in the scenario facts — no JSON blob.
    user_content = conv["turns"][0]["content"]
    assert "Nimbus" in user_content
    assert "```json" not in user_content


def test_flagship_run_writes_jsonl_and_index(tmp_path: Path) -> None:
    template = load_template(FLAGSHIP)
    generate_dataset(
        template,
        provider=FakeProvider(_echo),
        n=3,
        seed=42,
        output_dir=tmp_path,
        output_formats=["jsonl", "yaml"],
    )

    jsonl_lines = (tmp_path / "customer-support.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(jsonl_lines) == 3
    assert json.loads(jsonl_lines[0])["session_id"] == "customer-support_00"

    index_lines = (tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(index_lines) == 3


# ── determinism ───────────────────────────────────────────────────────────────


def test_run_is_reproducible(tmp_path: Path) -> None:
    template = load_template(FLAGSHIP)
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    generate_dataset(
        template,
        provider=FakeProvider(_echo),
        n=4,
        seed=7,
        output_dir=out_a,
        output_formats=["jsonl"],
    )
    generate_dataset(
        template,
        provider=FakeProvider(_echo),
        n=4,
        seed=7,
        output_dir=out_b,
        output_formats=["jsonl"],
    )
    assert (out_a / "customer-support.jsonl").read_text() == (
        out_b / "customer-support.jsonl"
    ).read_text()


# ── retries and drops ─────────────────────────────────────────────────────────


def test_retry_then_succeed(tmp_path: Path) -> None:
    """Fail validation on the first attempt (empty), then succeed."""

    def responder(request: CompletionRequest, call: int) -> str:
        return "" if call == 1 else request.messages[-1].content

    result = generate_dataset(
        load_template(FLAGSHIP),
        provider=FakeProvider(responder),
        n=1,
        seed=42,
        output_dir=tmp_path,
        output_formats=["jsonl"],
        max_retries=3,
    )
    assert result.summary.produced == 1
    assert result.summary.total_retries >= 1


def test_drops_after_max_retries(tmp_path: Path) -> None:
    """A response that always fails validation is dropped after max_retries."""
    result = generate_dataset(
        load_template(FLAGSHIP),
        provider=FakeProvider(lambda r, c: ""),
        n=2,
        seed=42,
        output_dir=tmp_path,
        output_formats=["jsonl"],
        max_retries=2,
    )
    assert result.summary.produced == 0
    assert result.summary.dropped == 2
    assert (tmp_path / "customer-support.jsonl").read_text() == ""


# ── deterministic-only (no provider) ──────────────────────────────────────────


def test_deterministic_only_needs_no_provider(tmp_path: Path) -> None:
    result = generate_dataset(_document_template(), provider=None, output_dir=tmp_path)
    assert result.summary.produced == 4
    lines = (tmp_path / "det-doc.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"host": "h1", "event": "login"} or json.loads(lines[0]) == {
        "host": "h2",
        "event": "login",
    }
    assert all(json.loads(line)["event"] == "login" for line in lines)


def test_generated_template_without_provider_raises(tmp_path: Path) -> None:
    with pytest.raises(GeneratorError, match="no provider"):
        generate_dataset(load_template(FLAGSHIP), provider=None, n=1, output_dir=tmp_path)


# ── caching ───────────────────────────────────────────────────────────────────


def test_cache_hit_avoids_second_provider_call(tmp_path: Path) -> None:
    template = load_template(FLAGSHIP)
    cache = ResponseCache(tmp_path / "cache")

    first = FakeProvider(_echo)
    generate_dataset(
        template,
        provider=first,
        cache=cache,
        n=3,
        seed=42,
        output_dir=tmp_path / "1",
        output_formats=["jsonl"],
    )
    assert len(first.calls) == 3  # one per sample on the cold run

    second = FakeProvider(_echo)
    generate_dataset(
        template,
        provider=second,
        cache=cache,
        n=3,
        seed=42,
        output_dir=tmp_path / "2",
        output_formats=["jsonl"],
    )
    assert len(second.calls) == 0  # identical prompts => all cache hits

    assert (tmp_path / "1" / "customer-support.jsonl").read_text() == (
        tmp_path / "2" / "customer-support.jsonl"
    ).read_text()


# ── misc ──────────────────────────────────────────────────────────────────────


def test_unknown_output_format_raises(tmp_path: Path) -> None:
    with pytest.raises(GeneratorError, match="Unknown output format"):
        generate_dataset(
            _document_template(), provider=None, output_dir=tmp_path, output_formats=["parquet"]
        )


def test_diversity_reflects_categorical_axes_not_faker(tmp_path: Path) -> None:
    """End-to-end: a fixed categorical axis + a varying faker reads as low-diversity."""
    template = TemplateSpec.model_validate(
        {
            "meta": {"name": "div", "description": "", "version": "1.0"},
            "scenario": {
                "variables": {
                    "region": {"type": "choice", "values": ["us"]},  # never varies
                    "ip": {"type": "faker", "kind": "ipv4"},  # unique every sample
                }
            },
            "output": {
                "type": "document",
                "content": {
                    "type": "fixed",
                    "value": {"region": "{{ scenario.region }}", "ip": "{{ scenario.ip }}"},
                },
            },
            "generation": {"n": 5, "seed": 1, "output_formats": ["jsonl"]},
        }
    )
    result = generate_dataset(template, provider=None, output_dir=tmp_path)
    assert result.summary.produced == 5
    # Only the categorical axis counts: one combo, despite five distinct IPs.
    assert result.summary.unique_scenarios == 1
    assert result.summary.diversity_ratio == 0.2
    assert result.summary.per_variable_spread["ip"] == 5


def test_pre_run_duplicate_warning_surfaced(tmp_path: Path) -> None:
    template = TemplateSpec.model_validate(
        {
            "meta": {"name": "tiny", "description": "", "version": "1.0"},
            "scenario": {"variables": {"a": {"type": "choice", "values": ["x", "y"]}}},
            "output": {
                "type": "document",
                "content": {"type": "fixed", "value": {"a": "{{ scenario.a }}"}},
            },
            "generation": {"n": 50, "seed": 1, "output_formats": ["jsonl"]},
        }
    )
    result = generate_dataset(template, provider=None, output_dir=tmp_path)
    assert result.pre_run_warning is not None
    assert "expect duplicate" in result.pre_run_warning
