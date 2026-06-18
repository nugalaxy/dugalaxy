"""Templates scenario facts into structured payloads AND injects them into the model prompt.

Given a sample's deterministic facts and the template's ``output`` spec, grounding
renders everything that can be rendered without the model:

- the system prompt (facts injected as ground truth);
- every ``fixed`` block (the engine fills it — strings interpolated, maps kept as
  serializable structures);
- every ``generated`` block's *instruction* plus its structural checks, with any
  ``{{ scenario.x }}`` in ``must_mention`` / ``must_not_contain`` resolved to the
  actual fact values so later validation compares against real ground truth.

The result is a :class:`GroundedOutput` the generator loop consumes: fixed blocks
are already done; generated blocks carry the prompt the model must answer.
"""

from dataclasses import dataclass
from typing import Any

from dugalaxy.template.spec import (
    ContentSpec,
    ConversationOutput,
    DocumentOutput,
    FixedContent,
    GeneratedContent,
    OutputSpec,
)

from .interpolation import interpolate, interpolate_structure


@dataclass(frozen=True)
class GeneratedRequest:
    """A block the model must write: the grounded prompt plus structural checks."""

    instruction: str
    max_tokens: int | None
    min_length: int | None
    max_length: int | None
    must_mention: tuple[str, ...]
    must_not_contain: tuple[str, ...]


@dataclass(frozen=True)
class GroundedBlock:
    """One grounded content block.

    Exactly one of ``value`` (a finished ``fixed`` block) or ``request`` (a
    ``generated`` block awaiting the model) is set. ``role`` is the turn role for
    conversation output, or ``None`` for a document.
    """

    role: str | None
    value: str | dict[str, Any] | None
    request: GeneratedRequest | None


@dataclass(frozen=True)
class GroundedOutput:
    """The fully grounded output for one sample."""

    kind: str  # "conversation" | "document"
    system_prompt: str | None
    blocks: tuple[GroundedBlock, ...]


def _render_fixed(content: FixedContent, facts: dict[str, Any]) -> str | dict[str, Any]:
    """Render a fixed block, preserving its native type (string or structured map)."""
    if isinstance(content.value, str):
        return interpolate(content.value, facts)
    rendered = interpolate_structure(content.value, facts)
    assert isinstance(rendered, dict)  # value is str | dict[str, Any] by the spec
    return rendered


def _render_generated(content: GeneratedContent, facts: dict[str, Any]) -> GeneratedRequest:
    """Render a generated block's instruction and resolve its validation references."""
    validation = content.validation
    must_mention = validation.must_mention if validation else []
    must_not_contain = validation.must_not_contain if validation else []
    return GeneratedRequest(
        instruction=interpolate(content.instruction, facts),
        max_tokens=content.max_tokens,
        min_length=validation.min_length if validation else None,
        max_length=validation.max_length if validation else None,
        must_mention=tuple(interpolate(item, facts) for item in must_mention),
        must_not_contain=tuple(interpolate(item, facts) for item in must_not_contain),
    )


def _ground_content(content: ContentSpec, role: str | None, facts: dict[str, Any]) -> GroundedBlock:
    if isinstance(content, FixedContent):
        return GroundedBlock(role=role, value=_render_fixed(content, facts), request=None)
    return GroundedBlock(role=role, value=None, request=_render_generated(content, facts))


def ground_output(output: OutputSpec, facts: dict[str, Any]) -> GroundedOutput:
    """Ground a template's output spec against one sample's facts."""
    if isinstance(output, ConversationOutput):
        system_prompt = interpolate(output.system_prompt, facts) if output.system_prompt else None
        blocks = tuple(_ground_content(turn.content, turn.role, facts) for turn in output.turns)
        return GroundedOutput(kind="conversation", system_prompt=system_prompt, blocks=blocks)

    if isinstance(output, DocumentOutput):
        block = _ground_content(output.content, None, facts)
        return GroundedOutput(kind="document", system_prompt=None, blocks=(block,))

    raise TypeError(f"Unsupported output type: {type(output).__name__}")
