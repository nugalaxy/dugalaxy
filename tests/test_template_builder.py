"""Tests for the AI template builder — Milestone 3.

No network: a fake provider returns canned text. The validate-loop is exercised with a
valid draft, an invalid-then-valid sequence, and an always-invalid sequence (fallback).
"""

from importlib.resources import files
from pathlib import Path

from dugalaxy.authoring import build_template, slugify
from dugalaxy.authoring.template_builder import _strip_code_fences, _unique_path
from dugalaxy.providers.base import (
    Completion,
    CompletionRequest,
    ProviderError,
    TextProvider,
)
from dugalaxy.template.loader import load_template

_VALID = (files("dugalaxy") / "templates" / "customer-support.yaml").read_text(encoding="utf-8")
_INVALID = "meta:\n  name: broken\noutput:\n  type: dataset\n"  # unknown output type


class _ScriptedProvider(TextProvider):
    """Returns a fixed sequence of texts, one per ``complete`` call."""

    def __init__(self, texts: list[str]) -> None:
        self.model = "fake"
        self.fingerprint = "fake|local|fake"
        self._texts = texts
        self.calls = 0

    def complete(self, request: CompletionRequest) -> Completion:
        text = self._texts[min(self.calls, len(self._texts) - 1)]
        self.calls += 1
        return Completion(text=text)


class _FailingProvider(TextProvider):
    def __init__(self) -> None:
        self.model = "fake"
        self.fingerprint = "fake|local|fake"

    def complete(self, request: CompletionRequest) -> Completion:
        raise ProviderError("ollama not running")


def test_valid_draft_is_saved_and_loads(tmp_path: Path) -> None:
    provider = _ScriptedProvider([_VALID])
    result = build_template("support chats", provider=provider, output_dir=tmp_path)
    assert not result.from_fallback
    assert result.attempts == 1
    assert result.output_shape == "conversation"
    assert result.path.parent == tmp_path
    load_template(result.path)  # the written file is a valid template


def test_strips_code_fences_before_validating(tmp_path: Path) -> None:
    fenced = f"```yaml\n{_VALID}```"
    provider = _ScriptedProvider([fenced])
    result = build_template("support chats", provider=provider, output_dir=tmp_path)
    assert not result.from_fallback
    load_template(result.path)


def test_invalid_then_valid_retries_then_saves(tmp_path: Path) -> None:
    provider = _ScriptedProvider([_INVALID, _VALID])
    result = build_template("support chats", provider=provider, output_dir=tmp_path)
    assert not result.from_fallback
    assert result.attempts == 2
    assert provider.calls == 2
    load_template(result.path)


def test_always_invalid_falls_back_to_example_never_a_broken_file(tmp_path: Path) -> None:
    provider = _ScriptedProvider([_INVALID])
    result = build_template("support chats", provider=provider, output_dir=tmp_path)
    assert result.from_fallback
    assert result.fallback_source is not None
    assert result.last_error is not None
    load_template(result.path)  # fallback file is still valid — never a broken file


def test_provider_failure_falls_back_immediately(tmp_path: Path) -> None:
    provider = _FailingProvider()
    result = build_template("support chats", provider=provider, output_dir=tmp_path)
    assert result.from_fallback
    assert result.last_error is not None and "failed" in result.last_error
    load_template(result.path)


def test_no_provider_falls_back_without_calling_a_model(tmp_path: Path) -> None:
    result = build_template("support chats", provider=None, output_dir=tmp_path)
    assert result.from_fallback
    assert result.attempts == 0
    load_template(result.path)


def test_document_description_falls_back_to_a_document_example(tmp_path: Path) -> None:
    # "invoice" hints at a single artifact → the document example, not the conversation one.
    result = build_template("an invoice document", provider=None, output_dir=tmp_path)
    assert result.from_fallback
    assert result.output_shape == "document"


def test_name_overrides_slug(tmp_path: Path) -> None:
    result = build_template(
        "some long messy description here", provider=None, name="My Set!", output_dir=tmp_path
    )
    assert result.path.name == "my-set.yaml"


def test_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    (tmp_path / "support.yaml").write_text("existing", encoding="utf-8")
    result = build_template("x", provider=None, name="support", output_dir=tmp_path)
    assert result.path.name == "support-2.yaml"
    assert (tmp_path / "support.yaml").read_text(encoding="utf-8") == "existing"


def test_slugify_examples() -> None:
    assert slugify("Short Angry Emails!") == "short-angry-emails"
    assert slugify("   ") == "dataset"
    assert slugify("a/b\\c") == "a-b-c"


def test_unique_path_increments(tmp_path: Path) -> None:
    base = tmp_path / "t.yaml"
    assert _unique_path(base) == base
    base.write_text("x", encoding="utf-8")
    assert _unique_path(base) == tmp_path / "t-2.yaml"


def test_strip_code_fences_handles_plain_and_fenced() -> None:
    assert _strip_code_fences("meta: x") == "meta: x"
    assert _strip_code_fences("```\nmeta: x\n```") == "meta: x"
    assert _strip_code_fences("```yaml\nmeta: x\n```") == "meta: x"
