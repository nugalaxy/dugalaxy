"""Run summary contract: requested/produced/dropped/retries + provable diversity metric.

Also the pre-run duplicate warning when enumerable scenario space < n.

Diversity is computed incrementally from lightweight per-sample signatures (a set of
scenario-combination hashes and per-variable value sets), never by holding the
produced dataset in memory — that would violate the disk-backed contract.
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
    unique_scenarios: int
    diversity_ratio: float  # unique_scenarios / produced (0.0 when nothing produced)
    per_variable_spread: dict[str, int]  # variable name -> count of distinct values seen


def _freeze(value: Any) -> str:
    """A stable, hashable string form of a fact value (dicts/lists included)."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return repr(value)


class DiversityTracker:
    """Accumulates diversity signatures across produced samples (not their content)."""

    def __init__(self) -> None:
        self._combinations: set[tuple[tuple[str, str], ...]] = set()
        self._values: dict[str, set[str]] = defaultdict(set)
        self._produced = 0

    def record(self, facts: dict[str, Any]) -> None:
        self._produced += 1
        signature = tuple(sorted((name, _freeze(value)) for name, value in facts.items()))
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
    product = 1
    found = False
    for var in scenario.variables.values():
        if isinstance(var, (ChoiceVar, WeightedChoiceVar)):
            product *= len(var.values)
            found = True
    return product if found else None


def duplicate_warning(scenario: ScenarioSpec, n: int) -> str | None:
    """Pre-run warning when the enumerable scenario space is smaller than *n*."""
    size = scenario_space_size(scenario)
    if size is not None and size < n:
        return f"scenario space ≈ {size} combos < n={n}; expect duplicate scenarios."
    return None
