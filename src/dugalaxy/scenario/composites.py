"""Composite variable types: computed (string composition) and object (structured map).

Composites reference already-resolved siblings with the universal ``{{ scenario.x }}``
rule, rendered by the shared interpolation engine. Resolution order is guaranteed by
:mod:`dugalaxy.scenario.resolver`, so every referenced value is already present in
*facts* by the time we render here.
"""

from typing import Any

from dugalaxy.generator.interpolation import interpolate, interpolate_structure
from dugalaxy.template.spec import ComputedVar, ObjectVar


def render_computed(var: ComputedVar, facts: dict[str, Any]) -> str:
    """Build a string by interpolating other scenario variables."""
    return interpolate(var.value, facts)


def render_object(var: ObjectVar, facts: dict[str, Any]) -> dict[str, Any]:
    """Build a structured map with each leaf interpolated from scenario facts.

    Returns a plain Python ``dict`` — serialization to valid JSON happens later,
    at grounding/emit time, via the ``| json`` filter (or :func:`to_json`).
    """
    rendered = interpolate_structure(var.value, facts)
    assert isinstance(rendered, dict)  # value is dict[str, Any] by construction
    return rendered
