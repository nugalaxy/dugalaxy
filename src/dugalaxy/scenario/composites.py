"""Composite variable types: computed (string composition) and object (structured map).

Composites reference already-resolved siblings with the universal ``{{ scenario.x }}``
rule. Rendering here is plain substitution only; the richer interpolation engine
(the ``| json`` filter, grounding into prompts) is built in the generator layer.
Resolution order is guaranteed by :mod:`dugalaxy.scenario.resolver`, so every
referenced value is already present in *scenario* by the time we render.
"""

from typing import Any

from jinja2 import Environment, StrictUndefined

from dugalaxy.template.spec import ComputedVar, ObjectVar

# StrictUndefined turns any unresolved reference into a loud error rather than an
# empty string. (Missing refs are normally caught at load time; this is a
# defensive backstop.) Prose output is not HTML, so autoescaping is off.
_env = Environment(undefined=StrictUndefined, autoescape=False)


def _render_str(template_str: str, scenario: dict[str, Any]) -> str:
    return _env.from_string(template_str).render(scenario=scenario)


def _render_value(value: Any, scenario: dict[str, Any]) -> Any:
    """Recursively interpolate string leaves; pass non-strings through unchanged."""
    if isinstance(value, str):
        return _render_str(value, scenario)
    if isinstance(value, dict):
        return {k: _render_value(v, scenario) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_value(item, scenario) for item in value]
    return value


def render_computed(var: ComputedVar, scenario: dict[str, Any]) -> str:
    """Build a string by interpolating other scenario variables."""
    return _render_str(var.value, scenario)


def render_object(var: ObjectVar, scenario: dict[str, Any]) -> dict[str, Any]:
    """Build a structured map with each leaf interpolated from scenario facts.

    Returns a plain Python ``dict`` — serialization to valid JSON happens later,
    at emit/interpolation time, via the ``| json`` filter.
    """
    rendered = _render_value(var.value, scenario)
    assert isinstance(rendered, dict)  # value is dict[str, Any] by construction
    return rendered
