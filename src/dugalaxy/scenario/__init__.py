"""Deterministic, seeded scenario generation engine.

Samples the variation axes of a scenario BEFORE any model call. The model never
invents these facts. Per-sample seed derived from (global_seed, sample_index);
per-variable RNG from (sample_seed, variable_name) so faker is reproducible too.
"""

from .engine import ScenarioFacts, derive_seed, generate_scenario
from .faker_registry import FAKER_KINDS
from .resolver import resolve_order

__all__ = [
    "FAKER_KINDS",
    "ScenarioFacts",
    "derive_seed",
    "generate_scenario",
    "resolve_order",
]
