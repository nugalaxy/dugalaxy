"""Tests for the interpolation engine and the | json filter — Milestone 2 acceptance.

The validity-trap tests (quotes, backslashes, newlines) are the core of this
milestone: serialized payloads must stay valid JSON no matter what the data holds.
"""

import json

import pytest

from dugalaxy.generator.interpolation import interpolate, interpolate_structure, to_json

# Values engineered to break naive string-pasted JSON.
NASTY_VALUES = [
    'has "double quotes"',
    "back\\slash",
    "line one\nline two",
    "tab\tseparated",
    'all three: "q" \\ and\nnewline',
    "unicode: café ☕ 日本語",
]


# ── basic interpolation ───────────────────────────────────────────────────────


def test_interpolate_simple() -> None:
    assert interpolate("Hello {{ scenario.name }}", {"name": "world"}) == "Hello world"


def test_interpolate_multiple_refs() -> None:
    facts = {"a": "x", "b": "y"}
    assert interpolate("{{ scenario.a }}-{{ scenario.b }}", facts) == "x-y"


def test_interpolate_is_deterministic() -> None:
    facts = {"name": "alice", "n": 7}
    template = "{{ scenario.name }}#{{ scenario.n }}"
    assert interpolate(template, facts) == interpolate(template, facts) == "alice#7"


def test_interpolate_undefined_ref_raises() -> None:
    from jinja2 import UndefinedError

    with pytest.raises(UndefinedError):
        interpolate("{{ scenario.missing }}", {"present": "x"})


# ── the | json filter / to_json ───────────────────────────────────────────────


def test_json_filter_produces_valid_json() -> None:
    facts = {"payload": {"event": "login", "user": "alice"}}
    rendered = interpolate("{{ scenario.payload | json(indent=2) }}", facts)
    assert json.loads(rendered) == {"event": "login", "user": "alice"}


def test_json_filter_indent() -> None:
    facts = {"payload": {"a": 1}}
    rendered = interpolate("{{ scenario.payload | json(indent=2) }}", facts)
    assert "\n" in rendered  # indented => multi-line
    compact = interpolate("{{ scenario.payload | json }}", facts)
    assert "\n" not in compact


@pytest.mark.parametrize("nasty", NASTY_VALUES)
def test_json_filter_escapes_nasty_values_inside_prose(nasty: str) -> None:
    """A code-fenced JSON block embedded in prose must parse back exactly."""
    facts = {"payload": {"field": nasty}}
    rendered = interpolate(
        "Here is the payload:\n```json\n{{ scenario.payload | json(indent=2) }}\n```\nDone.",
        facts,
    )
    block = rendered.split("```json\n", 1)[1].split("\n```", 1)[0]
    assert json.loads(block) == {"field": nasty}


@pytest.mark.parametrize("nasty", NASTY_VALUES)
def test_to_json_roundtrips_nasty_values(nasty: str) -> None:
    payload = {"k": nasty, "nested": {"also": nasty}, "list": [nasty]}
    assert json.loads(to_json(payload)) == payload


def test_to_json_keys_with_special_chars() -> None:
    payload = {'weird"key\\': "value\nwith newline"}
    assert json.loads(to_json(payload)) == payload


# ── interpolate_structure ─────────────────────────────────────────────────────


def test_interpolate_structure_renders_leaves() -> None:
    facts = {"host": "h1", "port": 8080}
    value = {"target": "{{ scenario.host }}:{{ scenario.port }}", "static": "x"}
    assert interpolate_structure(value, facts) == {"target": "h1:8080", "static": "x"}


def test_interpolate_structure_recurses_nested() -> None:
    facts = {"u": "alice"}
    value = {"meta": {"user": "{{ scenario.u }}"}, "tags": ["{{ scenario.u }}", "lit"]}
    assert interpolate_structure(value, facts) == {
        "meta": {"user": "alice"},
        "tags": ["alice", "lit"],
    }


def test_interpolate_structure_passes_through_non_strings() -> None:
    facts: dict[str, object] = {}
    value = {"n": 5, "flag": True, "none": None, "f": 1.5}
    assert interpolate_structure(value, facts) == value


def test_interpolate_structure_then_to_json_is_valid_with_nasty_leaf() -> None:
    facts = {"bad": 'x"y\\z\nw'}
    value = {"field": "{{ scenario.bad }}"}
    rendered = interpolate_structure(value, facts)
    assert json.loads(to_json(rendered)) == {"field": 'x"y\\z\nw'}
