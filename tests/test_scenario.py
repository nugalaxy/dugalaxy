"""Tests for the deterministic scenario engine — Milestone 1 acceptance."""

import re
from pathlib import Path
from typing import Any

import pytest

from dugalaxy.scenario import FAKER_KINDS, derive_seed, generate_scenario, resolve_order
from dugalaxy.scenario.faker_registry import render_faker
from dugalaxy.template.errors import (
    CyclicDependencyError,
    MissingReferenceError,
    UnknownFakerKindError,
)
from dugalaxy.template.loader import load_template
from dugalaxy.template.spec import FakerVar, ScenarioSpec

FLAGSHIP = Path(__file__).parent.parent / "templates" / "security-incident-triage.yaml"


def _scenario(variables: dict[str, Any]) -> ScenarioSpec:
    return ScenarioSpec.model_validate({"variables": variables})


# ── seed derivation ───────────────────────────────────────────────────────────


def test_derive_seed_is_deterministic() -> None:
    assert derive_seed(42, 0) == derive_seed(42, 0)
    assert derive_seed(42, "process_name") == derive_seed(42, "process_name")


def test_derive_seed_is_order_sensitive() -> None:
    assert derive_seed(1, 2) != derive_seed(2, 1)


def test_derive_seed_varies_by_input() -> None:
    assert derive_seed(42, 0) != derive_seed(42, 1)


# ── primitives ────────────────────────────────────────────────────────────────


def test_choice_picks_from_values() -> None:
    spec = _scenario({"x": {"type": "choice", "values": ["a", "b", "c"]}})
    for i in range(20):
        facts = generate_scenario(spec, seed=7, index=i)
        assert facts["x"] in {"a", "b", "c"}


def test_weighted_choice_picks_from_keys() -> None:
    spec = _scenario({"x": {"type": "weighted_choice", "values": {"lo": 0.1, "hi": 0.9}}})
    for i in range(20):
        facts = generate_scenario(spec, seed=7, index=i)
        assert facts["x"] in {"lo", "hi"}


def test_weighted_choice_respects_skew() -> None:
    spec = _scenario({"x": {"type": "weighted_choice", "values": {"lo": 0.05, "hi": 0.95}}})
    counts = {"lo": 0, "hi": 0}
    for i in range(400):
        counts[generate_scenario(spec, seed=1, index=i)["x"]] += 1
    assert counts["hi"] > counts["lo"]


def test_range_is_inclusive_and_in_bounds() -> None:
    spec = _scenario({"x": {"type": "range", "min": 1, "max": 3}})
    seen = set()
    for i in range(60):
        val = generate_scenario(spec, seed=99, index=i)["x"]
        assert 1 <= val <= 3
        seen.add(val)
    assert seen == {1, 2, 3}  # endpoints reachable


def test_sequence_increments_with_index() -> None:
    spec = _scenario({"x": {"type": "sequence", "start": 100, "step": 5}})
    assert generate_scenario(spec, seed=0, index=0)["x"] == 100
    assert generate_scenario(spec, seed=0, index=1)["x"] == 105
    assert generate_scenario(spec, seed=0, index=3)["x"] == 115


def test_sequence_independent_of_seed() -> None:
    spec = _scenario({"x": {"type": "sequence"}})
    assert generate_scenario(spec, seed=1, index=4)["x"] == 5
    assert generate_scenario(spec, seed=999, index=4)["x"] == 5


# ── faker ─────────────────────────────────────────────────────────────────────


def test_faker_kinds_whitelist() -> None:
    assert {
        "datetime_recent",
        "ipv4",
        "name",
        "email",
        "uuid4",
        "domain_name",
        "mac_address",
        "sha256",
        "file_path",
        "hostname",
    } == FAKER_KINDS


def test_faker_reproducible_same_seed() -> None:
    var = FakerVar(type="faker", kind="ipv4")
    assert render_faker(var, 12345) == render_faker(var, 12345)


def test_faker_differs_by_seed() -> None:
    var = FakerVar(type="faker", kind="uuid4")
    assert render_faker(var, 1) != render_faker(var, 2)


def test_faker_datetime_recent_format() -> None:
    var = FakerVar.model_validate({"type": "faker", "kind": "datetime_recent", "days_back": 90})
    value = render_faker(var, 42)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value)


def test_faker_in_engine_reproducible() -> None:
    spec = _scenario({"ts": {"type": "faker", "kind": "datetime_recent", "days_back": 30}})
    a = generate_scenario(spec, seed=5, index=2)
    b = generate_scenario(spec, seed=5, index=2)
    assert a["ts"] == b["ts"]


def test_unknown_faker_kind_raises() -> None:
    var = FakerVar(type="faker", kind="not_a_real_provider")
    with pytest.raises(UnknownFakerKindError, match="not_a_real_provider"):
        render_faker(var, 1)


@pytest.mark.parametrize(
    ("kind", "pattern"),
    [
        ("sha256", r"[0-9a-f]{64}"),
        ("file_path", r"/.+"),
        ("hostname", r"\S+"),
    ],
)
def test_security_faker_kinds(kind: str, pattern: str) -> None:
    var = FakerVar(type="faker", kind=kind)
    value = render_faker(var, 7)
    assert re.fullmatch(pattern, value)
    assert render_faker(var, 7) == value  # reproducible


def test_datetime_anchor_overridable() -> None:
    var = FakerVar.model_validate(
        {
            "type": "faker",
            "kind": "datetime_recent",
            "days_back": 10,
            "anchor": "2030-01-01T00:00:00",
        }
    )
    value = render_faker(var, 1)
    # Within [anchor - 10 days, anchor]: the year/month is pinned by the anchor.
    assert value.startswith("2029-12-") or value.startswith("2030-01-01")


# ── composites ────────────────────────────────────────────────────────────────


def test_computed_interpolates_siblings() -> None:
    spec = _scenario(
        {
            "dept": {"type": "choice", "values": ["finance"]},
            "idx": {"type": "range", "min": 7, "max": 7},
            "user": {"type": "computed", "value": "{{ scenario.dept }}_user{{ scenario.idx }}"},
        }
    )
    facts = generate_scenario(spec, seed=3, index=0)
    assert facts["user"] == "finance_user7"


def test_object_renders_to_dict_with_interpolated_leaves() -> None:
    spec = _scenario(
        {
            "name": {"type": "choice", "values": ["alice"]},
            "payload": {
                "type": "object",
                "value": {"user": "{{ scenario.name }}", "event": "login"},
            },
        }
    )
    facts = generate_scenario(spec, seed=8, index=0)
    assert facts["payload"] == {"user": "alice", "event": "login"}
    assert isinstance(facts["payload"], dict)


def test_object_nested_structure_interpolates() -> None:
    spec = _scenario(
        {
            "host": {"type": "choice", "values": ["h1"]},
            "obj": {
                "type": "object",
                "value": {"meta": {"host": "{{ scenario.host }}"}, "tags": ["{{ scenario.host }}"]},
            },
        }
    )
    facts = generate_scenario(spec, seed=2, index=0)
    assert facts["obj"] == {"meta": {"host": "h1"}, "tags": ["h1"]}


# ── topological resolution ────────────────────────────────────────────────────


def test_resolve_order_dependencies_first() -> None:
    variables = _scenario(
        {
            "a": {"type": "computed", "value": "{{ scenario.b }}"},
            "b": {"type": "choice", "values": ["x"]},
        }
    ).variables
    order = resolve_order(variables)
    assert order.index("b") < order.index("a")


def test_resolve_order_diamond() -> None:
    variables = _scenario(
        {
            "d": {"type": "choice", "values": ["x"]},
            "b": {"type": "computed", "value": "{{ scenario.d }}-b"},
            "c": {"type": "computed", "value": "{{ scenario.d }}-c"},
            "a": {"type": "computed", "value": "{{ scenario.b }}{{ scenario.c }}"},
        }
    ).variables
    order = resolve_order(variables)
    assert order.index("d") < order.index("b")
    assert order.index("d") < order.index("c")
    assert order.index("b") < order.index("a")
    assert order.index("c") < order.index("a")


def test_resolve_order_is_deterministic() -> None:
    variables = _scenario(
        {
            "z": {"type": "choice", "values": ["x"]},
            "y": {"type": "choice", "values": ["x"]},
            "x": {"type": "choice", "values": ["x"]},
        }
    ).variables
    assert resolve_order(variables) == resolve_order(variables)


def test_resolve_order_cycle_raises() -> None:
    variables = _scenario(
        {
            "a": {"type": "computed", "value": "{{ scenario.b }}"},
            "b": {"type": "computed", "value": "{{ scenario.a }}"},
        }
    ).variables
    with pytest.raises(CyclicDependencyError):
        resolve_order(variables)


def test_resolve_order_missing_ref_raises() -> None:
    variables = _scenario({"a": {"type": "computed", "value": "{{ scenario.ghost }}"}}).variables
    with pytest.raises(MissingReferenceError, match="ghost"):
        resolve_order(variables)


# ── determinism contract (§3.3) ───────────────────────────────────────────────


def test_same_seed_same_facts() -> None:
    spec = load_template(FLAGSHIP).scenario
    a = generate_scenario(spec, seed=42, index=5)
    b = generate_scenario(spec, seed=42, index=5)
    assert a == b


def test_different_index_independent() -> None:
    spec = load_template(FLAGSHIP).scenario
    facts = [generate_scenario(spec, seed=42, index=i) for i in range(10)]
    # The variation axes should not collapse to a single repeated sample.
    distinct = {tuple(sorted((k, str(v)) for k, v in f.items())) for f in facts}
    assert len(distinct) > 1


def test_sample_n_independent_of_predecessor() -> None:
    """Generating sample 5 alone equals generating it after others (no carry-over state)."""
    spec = load_template(FLAGSHIP).scenario
    alone = generate_scenario(spec, seed=42, index=5)
    for i in range(5):
        generate_scenario(spec, seed=42, index=i)
    after = generate_scenario(spec, seed=42, index=5)
    assert alone == after


# ── flagship integration ──────────────────────────────────────────────────────


def test_flagship_facts_are_consistent() -> None:
    spec = load_template(FLAGSHIP).scenario
    facts = generate_scenario(spec, seed=42, index=0)

    # username is computed from dept + user_index
    assert facts["username"] == f"{facts['dept']}_user{facts['user_index']}"

    # edr_payload is a serializable dict whose leaves match the scenario facts
    payload = facts["edr_payload"]
    assert isinstance(payload, dict)
    assert payload["process_name"] == facts["process_name"]
    assert payload["parent_process"] == facts["parent_process"]
    assert payload["user"] == facts["username"]
    assert payload["severity"] == facts["severity"]
    assert payload["command_line"].startswith(facts["process_name"])


# ── golden values (cross-version reproducibility guard) ───────────────────────
#
# These hardcode the exact output of a known seed. The "same seed -> same facts
# within one run" tests above pass trivially; these are what break loudly if
# anyone changes the seed-derivation scheme or a generator and silently shifts
# reproducibility across versions. If you intend such a change, update these
# values deliberately — never to "make the test pass".


def test_golden_derive_seed() -> None:
    assert derive_seed(42, 0) == 4955858400891216965
    assert derive_seed(42, "x") == 4466663962935946245


def test_golden_datetime_recent_is_time_stable() -> None:
    """A fixed seed yields a fixed timestamp, regardless of when the test runs."""
    var = FakerVar.model_validate({"type": "faker", "kind": "datetime_recent", "days_back": 90})
    assert render_faker(var, 42) == "2024-10-30T22:01:40Z"


def test_golden_flagship_facts() -> None:
    spec = load_template(FLAGSHIP).scenario
    facts = generate_scenario(spec, seed=42, index=0)
    assert facts == {
        "command_flags": "-exec bypass -W Hidden -enc <REDACTED>",
        "dept": "engineering",
        "parent_process": "explorer.exe",
        "process_name": "wscript.exe",
        "severity": "high",
        "timestamp": "2024-11-01T05:39:24Z",
        "user_index": 53,
        "username": "engineering_user53",
        "verdict": "needs_investigation",
        "edr_payload": {
            "event_type": "process_creation",
            "process_name": "wscript.exe",
            "command_line": "wscript.exe -exec bypass -W Hidden -enc <REDACTED>",
            "parent_process": "explorer.exe",
            "user": "engineering_user53",
            "timestamp": "2024-11-01T05:39:24Z",
            "severity": "high",
        },
    }
