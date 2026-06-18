"""The {{ scenario.x }} interpolation engine (Jinja2-based) and the | json filter.

This is the single place templates turn into text. The ``| json`` filter is the
project's inoculation against its #1 risk: structured payloads are *serialized*
(``json.dumps``), never built by pasting values into a JSON string, so a value
containing a quote, backslash, or newline can never produce invalid JSON.

The module is intentionally a pure leaf — it imports nothing from the rest of the
package — so both the scenario layer (resolving composites) and the generator
layer (grounding content) can depend on it without any import cycle.
"""

import json
from collections.abc import Mapping
from typing import Any

from jinja2 import Environment, StrictUndefined


def to_json(value: Any, indent: int | None = None) -> str:
    """Serialize *value* to valid JSON.

    Escaping is handled by ``json.dumps``, so quotes, backslashes, and newlines in
    the data are always escaped correctly. ``ensure_ascii=False`` keeps non-ASCII
    text readable (still valid JSON).
    """
    return json.dumps(value, indent=indent, ensure_ascii=False)


def _json_filter(value: Any, indent: int | None = None) -> str:
    """Jinja2 ``| json`` filter, e.g. ``{{ scenario.payload | json(indent=2) }}``."""
    return to_json(value, indent=indent)


# StrictUndefined turns an unresolved {{ scenario.x }} into a loud error rather
# than a silent empty string. (Missing references are normally caught at load
# time; this is the defensive backstop.) Output is prose/JSON, never HTML, so
# autoescaping stays off.
_env = Environment(undefined=StrictUndefined, autoescape=False)
_env.filters["json"] = _json_filter


def interpolate(template: str, facts: Mapping[str, Any]) -> str:
    """Render a single string template against scenario *facts*."""
    return _env.from_string(template).render(scenario=facts)


def interpolate_structure(value: Any, facts: Mapping[str, Any]) -> Any:
    """Recursively interpolate string leaves; pass non-strings through unchanged.

    Used for ``object`` variables and ``fixed`` map content: the structure is
    preserved and only its string leaves are rendered, so the result stays a real
    Python object that can be serialized later (e.g. via :func:`to_json`).
    """
    if isinstance(value, str):
        return interpolate(value, facts)
    if isinstance(value, dict):
        return {key: interpolate_structure(item, facts) for key, item in value.items()}
    if isinstance(value, list):
        return [interpolate_structure(item, facts) for item in value]
    return value
