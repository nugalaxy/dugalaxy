"""Run summary contract: requested/produced/dropped/retries + provable diversity metric.

Also the pre-run duplicate warning when enumerable scenario space < n.

Diversity is computed incrementally from lightweight per-sample signatures (a set of
scenario-combination hashes and per-variable value sets), never by holding the
produced dataset in memory — that would violate the disk-backed contract.

The headline diversity ratio is measured over the **categorical axes** only
(``choice`` / ``weighted_choice``) — the same axes the duplicate warning uses. This
is deliberate: high-cardinality variables (faker timestamps, UUIDs, wide ranges)
would otherwise make almost every sample "unique" and mask the very low-diversity
risk the metric exists to flag. Those variables still appear in the per-variable
spread, which reports distinct-value counts for every variable.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from dugalaxy.template.spec import ChoiceVar, ScenarioSpec, WeightedChoiceVar


@dataclass(frozen=True)
class RunSummary:
    """The after-run report. Variety is provable, not asserted."""

    requested: int
    produced: int
    dropped: int
    total_retries: int
    unique_scenarios: int  # distinct combinations of the categorical axes
    diversity_ratio: float  # unique_scenarios / produced (0.0 when nothing produced)
    per_variable_spread: dict[str, int]  # variable name -> count of distinct values seen


def _freeze(value: Any) -> str:
    """A stable, hashable string form of a fact value (dicts/lists included)."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return repr(value)


def _categoricals(scenario: ScenarioSpec) -> list[tuple[str, ChoiceVar | WeightedChoiceVar]]:
    """The categorical variables — the deliberate, collision-prone variation axes."""
    return [
        (name, var)
        for name, var in scenario.variables.items()
        if isinstance(var, (ChoiceVar, WeightedChoiceVar))
    ]


def categorical_variable_names(scenario: ScenarioSpec) -> set[str]:
    """Names of the categorical variables (choice / weighted_choice)."""
    return {name for name, _ in _categoricals(scenario)}


class DiversityTracker:
    """Accumulates diversity signatures across produced samples (not their content).

    *categorical* is the set of variable names that form the headline uniqueness
    signature. When it is empty (a template with no categorical axes), every variable
    is used as a fallback so genuinely faker-driven templates do not misreport as
    low-diversity.
    """

    def __init__(self, categorical: set[str] | None = None) -> None:
        self._categorical = categorical or set()
        self._combinations: set[tuple[tuple[str, str], ...]] = set()
        self._values: dict[str, set[str]] = defaultdict(set)
        self._produced = 0

    def record(self, facts: dict[str, Any]) -> None:
        self._produced += 1
        keys = [name for name in facts if name in self._categorical] or list(facts)
        signature = tuple(sorted((name, _freeze(facts[name])) for name in keys))
        self._combinations.add(signature)
        for name, value in facts.items():
            self._values[name].add(_freeze(value))

    def summary(self, *, requested: int, dropped: int, total_retries: int) -> RunSummary:
        unique = len(self._combinations)
        ratio = unique / self._produced if self._produced else 0.0
        return RunSummary(
            requested=requested,
            produced=self._produced,
            dropped=dropped,
            total_retries=total_retries,
            unique_scenarios=unique,
            diversity_ratio=round(ratio, 4),
            per_variable_spread={name: len(values) for name, values in self._values.items()},
        )


def scenario_space_size(scenario: ScenarioSpec) -> int | None:
    """Size of the enumerable scenario space: product of choice/weighted_choice cardinalities.

    Returns ``None`` when there are no categorical variables (the space is then driven
    by range/faker/sequence and is effectively unbounded — no duplicate risk to warn about).
    """
    categoricals = _categoricals(scenario)
    if not categoricals:
        return None
    product = 1
    for _, var in categoricals:
        product *= len(var.values)
    return product


def duplicate_warning(scenario: ScenarioSpec, n: int) -> str | None:
    """Pre-run warning when the enumerable scenario space is smaller than *n*."""
    size = scenario_space_size(scenario)
    if size is not None and size < n:
        return f"scenario space ~{size} combos < n={n}; expect duplicate scenarios."
    return None
