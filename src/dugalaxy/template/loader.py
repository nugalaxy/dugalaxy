"""Parse a template YAML file into validated spec objects. Fails fast with legible errors."""

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .errors import CyclicDependencyError, MissingReferenceError, TemplateLoadError
from .spec import (
    ComputedVar,
    ConversationOutput,
    DocumentOutput,
    FixedContent,
    GeneratedContent,
    ObjectVar,
    TemplateSpec,
)

# Matches {{ scenario.var_name }} and {{ scenario.var_name | filter(...) }}
_VAR_REF_RE = re.compile(r"\{\{\s*scenario\.(\w+)")


def _extract_refs(value: Any) -> set[str]:
    """Return all ``scenario.X`` variable names referenced anywhere in *value*."""
    if isinstance(value, str):
        return set(_VAR_REF_RE.findall(value))
    if isinstance(value, dict):
        refs: set[str] = set()
        for v in value.values():
            refs |= _extract_refs(v)
        return refs
    if isinstance(value, list):
        refs = set()
        for item in value:
            refs |= _extract_refs(item)
        return refs
    return set()


def _check_content_refs(
    content: FixedContent | GeneratedContent,
    defined: set[str],
    location: str,
) -> None:
    """Raise :exc:`MissingReferenceError` if *content* references an undefined variable."""
    if isinstance(content, FixedContent):
        for ref in _extract_refs(content.value):
            if ref not in defined:
                raise MissingReferenceError(
                    f"{location}: content references undefined variable '{ref}'"
                )
    else:
        for ref in _extract_refs(content.instruction):
            if ref not in defined:
                raise MissingReferenceError(
                    f"{location}: instruction references undefined variable '{ref}'"
                )
        if content.validation:
            for item in content.validation.must_mention:
                for ref in _extract_refs(item):
                    if ref not in defined:
                        raise MissingReferenceError(
                            f"{location}: must_mention references undefined variable '{ref}'"
                        )


def _check_references(spec: TemplateSpec) -> None:
    """Raise :exc:`MissingReferenceError` if any template expression names an undefined variable."""
    defined = set(spec.scenario.variables.keys())

    # Composite variable definitions
    for var_name, var in spec.scenario.variables.items():
        if isinstance(var, (ComputedVar, ObjectVar)):
            for ref in _extract_refs(var.value):
                if ref not in defined:
                    raise MissingReferenceError(
                        f"Variable '{var_name}' references undefined variable '{ref}'"
                    )

    # Output references
    output = spec.output
    if isinstance(output, ConversationOutput):
        if output.system_prompt:
            for ref in _extract_refs(output.system_prompt):
                if ref not in defined:
                    raise MissingReferenceError(
                        f"output.system_prompt references undefined variable '{ref}'"
                    )
        for i, turn in enumerate(output.turns):
            _check_content_refs(turn.content, defined, f"turn[{i}] role='{turn.role}'")
    elif isinstance(output, DocumentOutput):
        _check_content_refs(output.content, defined, "output.content")


def _check_no_cycles(spec: TemplateSpec) -> None:
    """Raise :exc:`CyclicDependencyError` if composite variables have circular dependencies."""
    defined = set(spec.scenario.variables.keys())

    # Build dependency edges: only composite vars create edges
    deps: dict[str, set[str]] = {name: set() for name in defined}
    for var_name, var in spec.scenario.variables.items():
        if isinstance(var, (ComputedVar, ObjectVar)):
            deps[var_name] = _extract_refs(var.value) & defined

    # DFS-based cycle detection (three-colour algorithm)
    white, gray, black = 0, 1, 2
    state: dict[str, int] = {name: white for name in defined}

    def visit(node: str, stack: list[str]) -> None:
        state[node] = gray
        stack.append(node)
        for dep in deps[node]:
            if state[dep] == gray:
                idx = stack.index(dep)
                cycle = " -> ".join([*stack[idx:], dep])
                raise CyclicDependencyError(f"Circular dependency: {cycle}")
            if state[dep] == white:
                visit(dep, stack)
        stack.pop()
        state[node] = black

    for node in list(defined):
        if state[node] == white:
            visit(node, [])


def load_template(path: Path) -> TemplateSpec:
    """Parse *path* into a validated :class:`TemplateSpec`, failing fast with legible errors.

    Raises:
        TemplateLoadError: YAML parse failure or schema mismatch.
        MissingReferenceError: A template expression names an undefined variable.
        CyclicDependencyError: Composite variables have circular dependencies.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TemplateLoadError(f"Cannot read '{path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise TemplateLoadError(f"Invalid YAML in '{path}': {exc}") from exc

    if not isinstance(raw, dict):
        raise TemplateLoadError(
            f"Template '{path}' must be a YAML mapping, got {type(raw).__name__}"
        )

    try:
        spec = TemplateSpec.model_validate(raw)
    except ValidationError as exc:
        raise TemplateLoadError(f"Schema error in '{path}':\n{exc}") from exc

    _check_references(spec)
    _check_no_cycles(spec)

    return spec
