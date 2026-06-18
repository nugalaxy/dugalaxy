"""Tests for run summary, diversity, and the pre-run duplicate warning — Milestone 4."""

from typing import Any

from dugalaxy.reporting.summary import (
    DiversityTracker,
    categorical_variable_names,
    duplicate_warning,
    scenario_space_size,
)
from dugalaxy.template.spec import ScenarioSpec


def _scenario(variables: dict[str, Any]) -> ScenarioSpec:
    return ScenarioSpec.model_validate({"variables": variables})


# ── scenario space + duplicate warning ────────────────────────────────────────


def test_scenario_space_is_product_of_categorical_cardinalities() -> None:
    scenario = _scenario(
        {
            "a": {"type": "choice", "values": ["x", "y", "z"]},
            "b": {"type": "weighted_choice", "values": {"p": 0.5, "q": 0.5}},
        }
    )
    assert scenario_space_size(scenario) == 6


def test_scenario_space_ignores_range_and_faker() -> None:
    scenario = _scenario(
        {
            "a": {"type": "choice", "values": ["x", "y"]},
            "idx": {"type": "range", "min": 1, "max": 1000},
            "ts": {"type": "faker", "kind": "ipv4"},
        }
    )
    assert scenario_space_size(scenario) == 2  # only the choice counts


def test_scenario_space_none_when_no_categoricals() -> None:
    scenario = _scenario({"idx": {"type": "range", "min": 1, "max": 9}})
    assert scenario_space_size(scenario) is None


def test_duplicate_warning_fires_when_space_below_n() -> None:
    scenario = _scenario({"a": {"type": "choice", "values": ["x", "y", "z"]}})
    warning = duplicate_warning(scenario, n=100)
    assert warning is not None
    assert "3" in warning and "100" in warning


def test_no_duplicate_warning_when_space_large() -> None:
    scenario = _scenario({"a": {"type": "choice", "values": ["x", "y", "z"]}})
    assert duplicate_warning(scenario, n=2) is None


def test_no_duplicate_warning_without_categoricals() -> None:
    scenario = _scenario({"ts": {"type": "faker", "kind": "ipv4"}})
    assert duplicate_warning(scenario, n=10_000) is None


# ── categorical axes ──────────────────────────────────────────────────────────


def test_categorical_variable_names() -> None:
    scenario = _scenario(
        {
            "a": {"type": "choice", "values": ["x"]},
            "b": {"type": "weighted_choice", "values": {"p": 1.0}},
            "idx": {"type": "range", "min": 1, "max": 9},
            "ts": {"type": "faker", "kind": "ipv4"},
        }
    )
    assert categorical_variable_names(scenario) == {"a", "b"}


# ── diversity tracker ─────────────────────────────────────────────────────────


def test_diversity_ignores_high_cardinality_variables() -> None:
    """The headline fix: timestamps/UUIDs must NOT inflate diversity.

    Here the only categorical axis ('proc') never varies, so the run is genuinely
    low-diversity even though every sample has a unique timestamp/index.
    """
    tracker = DiversityTracker(categorical={"proc"})
    for i in range(5):
        tracker.record({"proc": "powershell.exe", "idx": i, "ts": f"2024-01-0{i}T00:00:00Z"})
    summary = tracker.summary(requested=5, dropped=0, total_retries=0)
    assert summary.unique_scenarios == 1
    assert summary.diversity_ratio == 0.2  # 1 unique categorical combo / 5 produced
    # the high-cardinality variables still show up in the per-variable spread
    assert summary.per_variable_spread == {"proc": 1, "idx": 5, "ts": 5}


def test_diversity_counts_categorical_combinations() -> None:
    tracker = DiversityTracker(categorical={"proc", "verdict"})
    rows = [
        {"proc": "a", "verdict": "tp", "ts": "t0"},
        {"proc": "a", "verdict": "tp", "ts": "t1"},  # same categorical combo as row 0
        {"proc": "b", "verdict": "fp", "ts": "t2"},
    ]
    for row in rows:
        tracker.record(row)
    summary = tracker.summary(requested=3, dropped=0, total_retries=0)
    assert summary.unique_scenarios == 2  # {a,tp} and {b,fp}


def test_diversity_falls_back_to_all_vars_without_categoricals() -> None:
    """A template with no categorical axes (all faker) is not misreported as flat."""
    tracker = DiversityTracker(categorical=set())
    for i in range(4):
        tracker.record({"ts": f"t{i}"})
    summary = tracker.summary(requested=4, dropped=0, total_retries=0)
    assert summary.unique_scenarios == 4
    assert summary.diversity_ratio == 1.0


def test_diversity_all_unique() -> None:
    tracker = DiversityTracker(categorical={"proc", "idx"})
    for i in range(5):
        tracker.record({"proc": "powershell.exe", "idx": i})
    summary = tracker.summary(requested=5, dropped=0, total_retries=0)
    assert summary.produced == 5
    assert summary.unique_scenarios == 5
    assert summary.diversity_ratio == 1.0
    assert summary.per_variable_spread == {"proc": 1, "idx": 5}


def test_diversity_with_repeats() -> None:
    tracker = DiversityTracker()
    for combo in [{"a": "x"}, {"a": "x"}, {"a": "y"}, {"a": "y"}]:
        tracker.record(combo)
    summary = tracker.summary(requested=4, dropped=0, total_retries=0)
    assert summary.produced == 4
    assert summary.unique_scenarios == 2
    assert summary.diversity_ratio == 0.5


def test_diversity_handles_dict_valued_facts() -> None:
    tracker = DiversityTracker()
    tracker.record({"payload": {"a": 1}})
    tracker.record({"payload": {"a": 2}})
    tracker.record({"payload": {"a": 1}})
    summary = tracker.summary(requested=3, dropped=0, total_retries=0)
    assert summary.unique_scenarios == 2
    assert summary.per_variable_spread == {"payload": 2}


def test_summary_carries_counts() -> None:
    tracker = DiversityTracker()
    tracker.record({"a": "x"})
    summary = tracker.summary(requested=10, dropped=3, total_retries=7)
    assert summary.requested == 10
    assert summary.dropped == 3
    assert summary.total_retries == 7


def test_diversity_ratio_zero_when_nothing_produced() -> None:
    summary = DiversityTracker().summary(requested=5, dropped=5, total_retries=2)
    assert summary.produced == 0
    assert summary.diversity_ratio == 0.0
