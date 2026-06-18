"""Orchestrates per-sample scenario generation with deterministic seeding.

Seeding contract (§3.3):
- one global ``seed`` drives everything;
- the per-sample seed is derived from ``(global_seed, sample_index)``;
- each variable's RNG (and faker instance) is derived from ``(sample_seed, name)``.

So sample *N*'s facts are reproducible and independent of sample *N-1*. Seeds are
derived with SHA-256 (not Python's per-process-randomised ``hash``) so the same
inputs reproduce the same facts across runs, machines, and processes.
"""

import hashlib
import random
from typing import Any

from dugalaxy.template.spec import (
    ChoiceVar,
    ComputedVar,
    FakerVar,
    ObjectVar,
    RangeVar,
    ScenarioSpec,
    SequenceVar,
    VariableSpec,
    WeightedChoiceVar,
)

from .composites import render_computed, render_object
from .primitives import gen_choice, gen_faker, gen_range, gen_sequence, gen_weighted_choice
from .resolver import resolve_order

# A scenario's resolved facts: variable name -> value (str/int/dict).
ScenarioFacts = dict[str, Any]


def derive_seed(*parts: object) -> int:
    """Derive a stable 64-bit integer seed from the given parts (order matters)."""
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "big")


def _generate_variable(
    name: str,
    var: VariableSpec,
    sample_seed: int,
    sample_index: int,
    facts: ScenarioFacts,
) -> Any:
    """Generate a single variable's value from its own derived seed."""
    var_seed = derive_seed(sample_seed, name)

    if isinstance(var, ChoiceVar):
        return gen_choice(var, random.Random(var_seed))
    if isinstance(var, WeightedChoiceVar):
        return gen_weighted_choice(var, random.Random(var_seed))
    if isinstance(var, RangeVar):
        return gen_range(var, random.Random(var_seed))
    if isinstance(var, SequenceVar):
        return gen_sequence(var, sample_index)
    if isinstance(var, FakerVar):
        return gen_faker(var, var_seed)
    if isinstance(var, ComputedVar):
        return render_computed(var, facts)
    if isinstance(var, ObjectVar):
        return render_object(var, facts)
    raise TypeError(f"Unsupported variable type for '{name}': {type(var).__name__}")


def generate_scenario(scenario: ScenarioSpec, *, seed: int, index: int) -> ScenarioFacts:
    """Generate the deterministic facts for sample *index* under *seed*.

    Variables are resolved in dependency order so composites see their references
    already populated. The returned dict maps each variable name to its value.
    """
    sample_seed = derive_seed(seed, index)
    facts: ScenarioFacts = {}
    for name in resolve_order(scenario.variables):
        facts[name] = _generate_variable(name, scenario.variables[name], sample_seed, index, facts)
    return facts
