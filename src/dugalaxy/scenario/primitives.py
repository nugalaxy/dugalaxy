"""Primitive variable types: choice, weighted_choice, range, sequence, faker.

Each primitive is a pure function of its spec plus a deterministic input (a
seeded :class:`random.Random`, the sample index, or a derived integer seed for
faker). No global state — reproducibility comes entirely from the caller's seed.
"""

import random

from dugalaxy.template.spec import (
    ChoiceVar,
    FakerVar,
    RangeVar,
    SequenceVar,
    WeightedChoiceVar,
)

from .faker_registry import render_faker


def gen_choice(var: ChoiceVar, rng: random.Random) -> str:
    """Pick one value uniformly from the list."""
    return rng.choice(var.values)


def gen_weighted_choice(var: WeightedChoiceVar, rng: random.Random) -> str:
    """Pick one value with the given weights (weights need not sum to 1)."""
    keys = list(var.values.keys())
    weights = list(var.values.values())
    return rng.choices(keys, weights=weights, k=1)[0]


def gen_range(var: RangeVar, rng: random.Random) -> int:
    """Uniform random integer in [min, max], inclusive on both ends."""
    return rng.randint(var.min, var.max)


def gen_sequence(var: SequenceVar, sample_index: int) -> int:
    """Deterministic incrementing counter: ``start + step * sample_index``."""
    return var.start + var.step * sample_index


def gen_faker(var: FakerVar, seed: int) -> str:
    """Render a whitelisted faker provider, seeded for reproducibility."""
    return render_faker(var, seed)
