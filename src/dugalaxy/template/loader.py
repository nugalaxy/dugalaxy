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

_VALID_OUTPUT_TYPES = "conversation, document"


def _format_loc(loc: tuple[Any, ...]) -> str:
    """Render a Pydantic error location tuple as a readable dotted path.

    Integers become ``[i]`` (list indices); everything else is dotted. Discriminated-
    union tags (e.g. ``document``) appear as path segments — they name the variant the
    value matched, which is usually what the author wrote as ``type:``.
    """
    parts: list[str] = []
    for seg in loc:
        if isinstance(seg, int):
            parts.append(f"[{seg}]")
        else:
            parts.append(f".{seg}" if parts else str(seg))
    return "".join(parts) or "(root)"


def _output_shape_hint(raw: dict[str, Any]) -> str | None:
    """A targeted hint for the most common output-shape mistakes, or ``None``.

    The raw Pydantic message for these is opaque (a missing-field error deep in a
    discriminated union), so we translate the author's actual structure into advice.
    """
    output = raw.get("output")
    if not isinstance(output, dict):
        return None
    out_type = output.get("type")
    if out_type not in ("conversation", "document"):
        return f"output.type must be one of: {_VALID_OUTPUT_TYPES} (got '{out_type}')."
    if out_type == "document" and "turns" in output and "content" not in output:
        return (
            "a 'document' output produces one artifact and uses a single 'content:' block, "
            "not 'turns:'. For a back-and-forth, use 'type: conversation' with 'turns:'."
        )
    if out_type == "conversation" and "content" in output and "turns" not in output:
        return (
            "a 'conversation' output uses 'turns:', not a single 'content:'. For one "
            "standalone artifact, use 'type: document' with 'content:'."
        )
    return None


def _format_validation_error(exc: ValidationError, raw: dict[str, Any]) -> str:
    """Turn a Pydantic ValidationError into a few clean, human lines (no URLs, no repr)."""
    lines: list[str] = []
    for err in exc.errors():
        loc = _format_loc(err["loc"])
        detail = "required field is missing" if err["type"] == "missing" else err["msg"]
        lines.append(f"  - {loc}: {detail}")
    message = "\n".join(lines)
    hint = _output_shape_hint(raw)
    if hint:
        message += f"\n\nHint: {hint}"
    return message


def extract_refs(value: Any) -> set[str]:
    """Return all ``scenario.X`` variable names referenced anywhere in *value*.

    Recurses into dicts and lists so it works for both ``computed`` (string) and
    ``object`` (nested map) variable definitions.
    """
    if isinstance(value, str):
        return set(_VAR_REF_RE.findall(value))
    if isinstance(value, dict):
        refs: set[str] = set()
        for v in value.values():
            refs |= extract_refs(v)
        return refs
    if isinstance(value, list):
        refs = set()
        for item in value:
            refs |= extract_refs(item)
        return refs
    return set()


def _check_content_refs(
    content: FixedContent | GeneratedContent,
    defined: set[str],
    location: str,
) -> None:
    """Raise :exc:`MissingReferenceError` if *content* references an undefined variable."""
    if isinstance(content, FixedContent):
        for ref in extract_refs(content.value):
            if ref not in defined:
                raise MissingReferenceError(
                    f"{location}: content references undefined variable '{ref}'"
                )
    else:
        for ref in extract_refs(content.instruction):
            if ref not in defined:
                raise MissingReferenceError(
                    f"{location}: instruction references undefined variable '{ref}'"
                )
        if content.validation:
            for item in content.validation.must_mention:
                for ref in extract_refs(item):
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
            for ref in extract_refs(var.value):
                if ref not in defined:
                    raise MissingReferenceError(
                        f"Variable '{var_name}' references undefined variable '{ref}'"
                    )

    # Output references
    output = spec.output
    if isinstance(output, ConversationOutput):
        if output.system_prompt:
            for ref in extract_refs(output.system_prompt):
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
            deps[var_name] = extract_refs(var.value) & defined

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
        TemplateLoadError: file read, YAML parse failure, or schema mismatch.
        MissingReferenceError: A template expression names an undefined variable.
        CyclicDependencyError: Composite variables have circular dependencies.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TemplateLoadError(f"Cannot read '{path}': {exc}") from exc
    return load_template_text(text, source=f"'{path}'")


def load_template_text(text: str, *, source: str = "the template") -> TemplateSpec:
    """Validate template YAML *text* into a :class:`TemplateSpec`, with legible errors.

    The shared core behind :func:`load_template`; it takes YAML already in memory so the
    AI template builder can validate a model's output without writing a file first.
    *source* names the origin in error messages (a path, or e.g. "the generated template").

    Raises:
        TemplateLoadError: YAML parse failure or schema mismatch.
        MissingReferenceError: A template expression names an undefined variable.
        CyclicDependencyError: Composite variables have circular dependencies.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TemplateLoadError(f"Invalid YAML in {source}: {exc}") from exc

    if not isinstance(raw, dict):
        raise TemplateLoadError(f"{source} must be a YAML mapping, got {type(raw).__name__}")

    try:
        spec = TemplateSpec.model_validate(raw)
    except ValidationError as exc:
        raise TemplateLoadError(
            f"{source} is not a valid template:\n{_format_validation_error(exc, raw)}"
        ) from exc

    _check_references(spec)
    _check_no_cycles(spec)

    return spec
