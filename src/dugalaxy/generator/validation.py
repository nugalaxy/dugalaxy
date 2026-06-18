"""Structural validation of generated content (non-empty, length, fact-presence). Not semantic.

These checks are deliberately structural only — they confirm the prose is present, the
right length, and mentions (or avoids) the required strings. They do NOT judge meaning
or correctness; we are honest about that boundary everywhere. ``must_mention`` strings
have already been resolved to actual scenario facts during grounding, so fact-presence
is checked against ground truth.
"""

from dataclasses import dataclass

from .grounding import GeneratedRequest


@dataclass(frozen=True)
class ValidationResult:
    """Whether generated text passed structural validation, and why not if it failed."""

    ok: bool
    reason: str | None = None


def validate_generated(text: str, request: GeneratedRequest) -> ValidationResult:
    """Apply the request's structural checks to *text*."""
    if not text.strip():
        return ValidationResult(False, "output is empty")

    length = len(text)
    if request.min_length is not None and length < request.min_length:
        return ValidationResult(False, f"too short ({length} < min_length {request.min_length})")
    if request.max_length is not None and length > request.max_length:
        return ValidationResult(False, f"too long ({length} > max_length {request.max_length})")

    for needle in request.must_mention:
        if needle not in text:
            return ValidationResult(False, f"missing required mention: {needle!r}")

    for banned in request.must_not_contain:
        if banned in text:
            return ValidationResult(False, f"contains banned text: {banned!r}")

    return ValidationResult(True)
