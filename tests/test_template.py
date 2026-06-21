"""Tests for template spec models and loader — Milestone 0 acceptance."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from dugalaxy.template.errors import (
    CyclicDependencyError,
    MissingReferenceError,
    TemplateLoadError,
)
from dugalaxy.template.loader import load_template
from dugalaxy.template.spec import (
    ChoiceVar,
    ComputedVar,
    ConversationOutput,
    FakerVar,
    FixedContent,
    GeneratedContent,
    ObjectVar,
    RangeVar,
    SequenceVar,
    TemplateSpec,
    WeightedChoiceVar,
)

FLAGSHIP = Path(__file__).parent.parent / "src" / "dugalaxy" / "templates" / "customer-support.yaml"

# ── helpers ──────────────────────────────────────────────────────────────────

_BASE: dict[str, Any] = {
    "meta": {"name": "test", "description": "test template", "version": "1.0"},
    "output": {
        "type": "conversation",
        "turns": [{"role": "user", "content": {"type": "fixed", "value": "hello"}}],
    },
    "generation": {},
}


def _spec(scenario_vars: dict[str, Any]) -> TemplateSpec:
    """Build a minimal TemplateSpec with the given scenario variables."""
    raw = {**_BASE, "scenario": {"variables": scenario_vars}}
    return TemplateSpec.model_validate(raw)


def _write(tmp_path: Path, scenario_vars: dict[str, Any], **overrides: Any) -> Path:
    """Write a minimal template YAML to a temp file and return its path."""
    raw: dict[str, Any] = {**_BASE, "scenario": {"variables": scenario_vars}, **overrides}
    p = tmp_path / "template.yaml"
    p.write_text(yaml.dump(raw), encoding="utf-8")
    return p


# ── flagship ─────────────────────────────────────────────────────────────────


def test_flagship_loads() -> None:
    spec = load_template(FLAGSHIP)
    assert spec.meta.name == "customer-support"
    assert spec.meta.version == "1.0"
    assert spec.generation.n == 100
    assert spec.generation.seed == 42


def test_flagship_scenario_variable_types() -> None:
    spec = load_template(FLAGSHIP)
    v = spec.scenario.variables
    assert isinstance(v["product"], ChoiceVar)
    assert isinstance(v["issue"], WeightedChoiceVar)
    assert isinstance(v["ticket_number"], RangeVar)
    assert isinstance(v["opened_at"], FakerVar)
    assert isinstance(v["ticket_id"], ComputedVar)
    assert isinstance(v["account_record"], ObjectVar)


def test_flagship_output_structure() -> None:
    spec = load_template(FLAGSHIP)
    assert isinstance(spec.output, ConversationOutput)
    assert spec.output.system_prompt is not None
    assert len(spec.output.turns) == 2
    assert spec.output.turns[0].role == "user"
    assert isinstance(spec.output.turns[0].content, FixedContent)
    assert isinstance(spec.output.turns[1].content, GeneratedContent)


def test_flagship_validation_spec() -> None:
    spec = load_template(FLAGSHIP)
    assert isinstance(spec.output, ConversationOutput)
    gen = spec.output.turns[1].content
    assert isinstance(gen, GeneratedContent)
    assert gen.max_tokens == 600
    assert gen.validation is not None
    assert gen.validation.min_length == 80
    assert gen.validation.must_mention != []


# ── primitive variable types ──────────────────────────────────────────────────


def test_choice_var() -> None:
    spec = _spec({"x": {"type": "choice", "values": ["a", "b", "c"]}})
    var = spec.scenario.variables["x"]
    assert isinstance(var, ChoiceVar)
    assert var.values == ["a", "b", "c"]


def test_weighted_choice_var() -> None:
    spec = _spec({"x": {"type": "weighted_choice", "values": {"low": 0.3, "high": 0.7}}})
    var = spec.scenario.variables["x"]
    assert isinstance(var, WeightedChoiceVar)
    assert var.values["low"] == pytest.approx(0.3)


def test_range_var() -> None:
    spec = _spec({"x": {"type": "range", "min": 1, "max": 99}})
    var = spec.scenario.variables["x"]
    assert isinstance(var, RangeVar)
    assert var.min == 1
    assert var.max == 99


def test_sequence_var_defaults() -> None:
    spec = _spec({"x": {"type": "sequence"}})
    var = spec.scenario.variables["x"]
    assert isinstance(var, SequenceVar)
    assert var.start == 1
    assert var.step == 1


def test_sequence_var_custom() -> None:
    spec = _spec({"x": {"type": "sequence", "start": 100, "step": 5}})
    var = spec.scenario.variables["x"]
    assert isinstance(var, SequenceVar)
    assert var.start == 100
    assert var.step == 5


def test_faker_var() -> None:
    spec = _spec({"x": {"type": "faker", "kind": "datetime_recent", "days_back": 90}})
    var = spec.scenario.variables["x"]
    assert isinstance(var, FakerVar)
    assert var.kind == "datetime_recent"
    extra = var.model_extra or {}
    assert extra.get("days_back") == 90


# ── composite variable types ──────────────────────────────────────────────────


def test_computed_var() -> None:
    spec = _spec(
        {
            "dept": {"type": "choice", "values": ["eng"]},
            "idx": {"type": "range", "min": 1, "max": 9},
            "user": {"type": "computed", "value": "{{ scenario.dept }}_{{ scenario.idx }}"},
        }
    )
    var = spec.scenario.variables["user"]
    assert isinstance(var, ComputedVar)
    assert "{{ scenario.dept }}" in var.value


def test_object_var() -> None:
    spec = _spec(
        {
            "name": {"type": "choice", "values": ["alice"]},
            "payload": {
                "type": "object",
                "value": {"user": "{{ scenario.name }}", "event": "login"},
            },
        }
    )
    var = spec.scenario.variables["payload"]
    assert isinstance(var, ObjectVar)
    assert var.value["user"] == "{{ scenario.name }}"
    assert var.value["event"] == "login"


# ── field validators ──────────────────────────────────────────────────────────


def test_weighted_choice_rejects_zero_weight() -> None:
    with pytest.raises(ValidationError, match="positive"):
        _spec({"x": {"type": "weighted_choice", "values": {"a": 0.0, "b": 1.0}}})


def test_weighted_choice_rejects_negative_weight() -> None:
    with pytest.raises(ValidationError, match="positive"):
        _spec({"x": {"type": "weighted_choice", "values": {"a": -0.5, "b": 1.0}}})


def test_range_rejects_min_greater_than_max() -> None:
    with pytest.raises(ValidationError, match="min"):
        _spec({"x": {"type": "range", "min": 10, "max": 5}})


# ── schema errors (unknown types) ────────────────────────────────────────────


def test_unknown_variable_type_raises_load_error(tmp_path: Path) -> None:
    p = _write(tmp_path, {"x": {"type": "nonexistent", "values": ["a"]}})
    with pytest.raises(TemplateLoadError):
        load_template(p)


def test_bad_yaml_raises_load_error(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("meta: [this: is: broken: yaml: }\n", encoding="utf-8")
    with pytest.raises(TemplateLoadError):
        load_template(p)


def test_missing_file_raises_load_error(tmp_path: Path) -> None:
    with pytest.raises(TemplateLoadError):
        load_template(tmp_path / "no_such_file.yaml")


# ── legible schema errors ────────────────────────────────────────────────────


def test_schema_error_is_legible_no_pydantic_noise(tmp_path: Path) -> None:
    # A document output mistakenly given `turns:` instead of `content:`. The message
    # must be human-readable — no Pydantic URL, no `input_type=`, no truncated repr.
    p = _write(
        tmp_path,
        {"x": {"type": "choice", "values": ["a"]}},
        output={
            "type": "document",
            "turns": [{"role": "user", "content": {"type": "generated", "instruction": "hi"}}],
        },
    )
    with pytest.raises(TemplateLoadError) as exc_info:
        load_template(p)
    msg = str(exc_info.value)
    assert "required field is missing" in msg
    assert "Hint:" in msg and "single 'content:' block" in msg
    assert "errors.pydantic.dev" not in msg
    assert "input_type" not in msg


def test_schema_error_invalid_output_type_lists_valid_types(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        {"x": {"type": "choice", "values": ["a"]}},
        output={"type": "dataset", "content": {"type": "fixed", "value": "hi"}},
    )
    with pytest.raises(TemplateLoadError) as exc_info:
        load_template(p)
    msg = str(exc_info.value)
    assert "conversation, document" in msg
    assert "dataset" in msg


# ── missing reference errors ─────────────────────────────────────────────────


def test_missing_ref_in_computed(tmp_path: Path) -> None:
    p = _write(tmp_path, {"x": {"type": "computed", "value": "{{ scenario.ghost }}"}})
    with pytest.raises(MissingReferenceError, match="ghost"):
        load_template(p)


def test_missing_ref_in_object(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        {"obj": {"type": "object", "value": {"key": "{{ scenario.phantom }}"}}},
    )
    with pytest.raises(MissingReferenceError, match="phantom"):
        load_template(p)


def test_missing_ref_in_system_prompt(tmp_path: Path) -> None:
    raw: dict[str, Any] = {
        **_BASE,
        "scenario": {"variables": {"x": {"type": "choice", "values": ["a"]}}},
        "output": {
            "type": "conversation",
            "system_prompt": "Hello {{ scenario.nobody }}",
            "turns": [{"role": "user", "content": {"type": "fixed", "value": "hi"}}],
        },
    }
    p = tmp_path / "t.yaml"
    p.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(MissingReferenceError, match="nobody"):
        load_template(p)


def test_missing_ref_in_turn_fixed_content(tmp_path: Path) -> None:
    raw: dict[str, Any] = {
        **_BASE,
        "scenario": {"variables": {"x": {"type": "choice", "values": ["a"]}}},
        "output": {
            "type": "conversation",
            "turns": [
                {"role": "user", "content": {"type": "fixed", "value": "{{ scenario.missing }}"}}
            ],
        },
    }
    p = tmp_path / "t.yaml"
    p.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(MissingReferenceError, match="missing"):
        load_template(p)


def test_missing_ref_in_generated_instruction(tmp_path: Path) -> None:
    raw: dict[str, Any] = {
        **_BASE,
        "scenario": {"variables": {"x": {"type": "choice", "values": ["a"]}}},
        "output": {
            "type": "conversation",
            "turns": [
                {
                    "role": "agent",
                    "content": {
                        "type": "generated",
                        "instruction": "Use {{ scenario.vanished }} in your answer.",
                    },
                }
            ],
        },
    }
    p = tmp_path / "t.yaml"
    p.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(MissingReferenceError, match="vanished"):
        load_template(p)


def test_missing_ref_in_must_mention(tmp_path: Path) -> None:
    raw: dict[str, Any] = {
        **_BASE,
        "scenario": {"variables": {"x": {"type": "choice", "values": ["a"]}}},
        "output": {
            "type": "conversation",
            "turns": [
                {
                    "role": "agent",
                    "content": {
                        "type": "generated",
                        "instruction": "Reply.",
                        "validation": {"must_mention": ["{{ scenario.nope }}"]},
                    },
                }
            ],
        },
    }
    p = tmp_path / "t.yaml"
    p.write_text(yaml.dump(raw), encoding="utf-8")
    with pytest.raises(MissingReferenceError, match="nope"):
        load_template(p)


# ── cycle detection ───────────────────────────────────────────────────────────


def test_cycle_two_computed_vars(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        {
            "a": {"type": "computed", "value": "{{ scenario.b }}"},
            "b": {"type": "computed", "value": "{{ scenario.a }}"},
        },
    )
    with pytest.raises(CyclicDependencyError):
        load_template(p)


def test_cycle_three_computed_vars(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        {
            "a": {"type": "computed", "value": "{{ scenario.b }}"},
            "b": {"type": "computed", "value": "{{ scenario.c }}"},
            "c": {"type": "computed", "value": "{{ scenario.a }}"},
        },
    )
    with pytest.raises(CyclicDependencyError):
        load_template(p)


def test_cycle_object_references_itself(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        {"obj": {"type": "object", "value": {"key": "{{ scenario.obj }}"}}},
    )
    with pytest.raises(CyclicDependencyError):
        load_template(p)


def test_no_false_cycle_for_primitive_dep(tmp_path: Path) -> None:
    """A computed var depending on a primitive is NOT a cycle."""
    p = _write(
        tmp_path,
        {
            "base": {"type": "choice", "values": ["x"]},
            "derived": {"type": "computed", "value": "{{ scenario.base }}-suffix"},
        },
    )
    spec = load_template(p)
    assert isinstance(spec.scenario.variables["derived"], ComputedVar)


def test_no_false_cycle_for_diamond_deps(tmp_path: Path) -> None:
    """a->b, a->c, b->d, c->d is a valid DAG, not a cycle."""
    p = _write(
        tmp_path,
        {
            "d": {"type": "choice", "values": ["x"]},
            "b": {"type": "computed", "value": "{{ scenario.d }}-b"},
            "c": {"type": "computed", "value": "{{ scenario.d }}-c"},
            "a": {"type": "computed", "value": "{{ scenario.b }}-{{ scenario.c }}"},
        },
    )
    spec = load_template(p)
    assert isinstance(spec.scenario.variables["a"], ComputedVar)
