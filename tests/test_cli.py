"""Tests for the CLI surface — Milestone 5. No network: the model path is monkeypatched."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

import dugalaxy.cli.main as cli
from dugalaxy.cli.main import app
from dugalaxy.providers.base import Completion, CompletionRequest, TextProvider
from dugalaxy.template.loader import load_template

runner = CliRunner()


class _FakeProvider(TextProvider):
    def __init__(self, responder: Callable[[CompletionRequest], str]) -> None:
        self.model = "fake-model"
        self.fingerprint = "fake|local|fake-model"
        self._responder = responder

    def complete(self, request: CompletionRequest) -> Completion:
        return Completion(text=self._responder(request))


_DETERMINISTIC_TEMPLATE = """\
meta:
  name: det
  description: deterministic doc
  version: "1.0"
scenario:
  variables:
    host:
      type: choice
      values: ["h1", "h2"]
output:
  type: document
  content:
    type: fixed
    value:
      host: "{{ scenario.host }}"
      event: "login"
generation:
  n: 4
  seed: 1
  output_formats: [jsonl]
"""


# ── version ───────────────────────────────────────────────────────────────────


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "dugalaxy" in result.stdout


# ── init ──────────────────────────────────────────────────────────────────────


def test_init_scaffolds_a_loadable_template(tmp_path: Path) -> None:
    target = tmp_path / "support.yaml"
    result = runner.invoke(app, ["init", "support", "--output", str(target)])
    assert result.exit_code == 0
    assert target.exists()
    # The scaffolded template must actually load and validate.
    spec = load_template(target)
    assert spec.meta.name == "support"


def test_init_refuses_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "x.yaml"
    target.write_text("existing", encoding="utf-8")
    result = runner.invoke(app, ["init", "x", "--output", str(target)])
    assert result.exit_code == 1
    assert target.read_text(encoding="utf-8") == "existing"


# ── gen: deterministic-only (no provider, runs offline) ────────────────────────


def test_gen_deterministic_only(tmp_path: Path) -> None:
    template = tmp_path / "det.yaml"
    template.write_text(_DETERMINISTIC_TEMPLATE, encoding="utf-8")
    out = tmp_path / "out"
    result = runner.invoke(app, ["gen", str(template), "--output-dir", str(out)])

    assert result.exit_code == 0, result.stdout
    assert "produced 4/4" in result.stdout
    lines = (out / "det.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert all(json.loads(line)["event"] == "login" for line in lines)


def test_gen_missing_template_errors() -> None:
    result = runner.invoke(app, ["gen", "does-not-exist"])
    assert result.exit_code == 1
    assert "not found" in result.stderr


def test_gen_unknown_format_errors(tmp_path: Path) -> None:
    template = tmp_path / "det.yaml"
    template.write_text(_DETERMINISTIC_TEMPLATE, encoding="utf-8")
    result = runner.invoke(
        app, ["gen", str(template), "--output-dir", str(tmp_path / "o"), "-f", "parquet"]
    )
    assert result.exit_code == 1
    assert "Unknown output format" in result.stderr


# ── gen: model path (monkeypatched provider) ───────────────────────────────────


def test_gen_with_model_uses_ollama_free_no_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli, "build_provider", lambda config: _FakeProvider(lambda r: r.messages[-1].content)
    )
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "gen",
            "src/dugalaxy/templates/customer-support.yaml",
            "--n",
            "2",
            "--seed",
            "42",
            "--output-dir",
            str(out),
            "-f",
            "yaml",
            "--provider",
            "ollama",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "free" in result.stdout  # Ollama => free => no confirmation prompt
    assert "produced 2/2" in result.stdout
    assert (out / "customer-support.yaml").exists()


def test_gen_paid_provider_prompts_and_can_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli, "build_provider", lambda config: _FakeProvider(lambda r: r.messages[-1].content)
    )
    out = tmp_path / "out"
    # Decline the confirmation prompt -> abort, nothing written.
    result = runner.invoke(
        app,
        [
            "gen",
            "src/dugalaxy/templates/customer-support.yaml",
            "--n",
            "1",
            "--provider",
            "openai_compatible",
            "--model",
            "gpt-4o-mini",
            "--api-key-env",
            "OPENAI_API_KEY",
            "--output-dir",
            str(out),
        ],
        input="n\n",
    )
    assert result.exit_code == 1
    assert "Aborted" in result.stdout


def test_gen_unknown_price_warns_and_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A model with no known price must say so explicitly and still block on confirm."""
    monkeypatch.setattr(
        cli, "build_provider", lambda config: _FakeProvider(lambda r: r.messages[-1].content)
    )
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "gen",
            "src/dugalaxy/templates/customer-support.yaml",
            "--n",
            "1",
            "--provider",
            "openai_compatible",
            "--model",
            "mystery-model-v9",  # absent from the pricing table => priced=False
            "--api-key-env",
            "OPENAI_API_KEY",
            "--output-dir",
            str(out),
        ],
        input="n\n",
    )
    assert result.exit_code == 1
    assert "cost unknown for this model" in result.stdout
    assert "Aborted" in result.stdout


def test_gen_cost_cap_blocks_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli, "build_provider", lambda config: _FakeProvider(lambda r: r.messages[-1].content)
    )
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "gen",
            "src/dugalaxy/templates/customer-support.yaml",
            "--n",
            "100000",
            "--provider",
            "openai_compatible",
            "--model",
            "gpt-4o-mini",
            "--api-key-env",
            "OPENAI_API_KEY",
            "--cost-cap",
            "0.01",
            "--output-dir",
            str(out),
            "--yes",
        ],
    )
    assert result.exit_code == 1
    assert "exceeds the cap" in result.stderr
