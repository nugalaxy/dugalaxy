"""Authoring aids: helping a user reach a working setup and a working template.

This package holds the user-onboarding surfaces that sit *around* the generation
engine — the things that turn a cold `pip install` into a first success. It starts
with diagnostics (`dugalaxy doctor`); the AI template builder lands here later.
"""

from .diagnostics import Check, Diagnosis, diagnose
from .template_builder import (
    BUILDER_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_RETRIES,
    BuildResult,
    build_template,
    builder_input_text,
    slugify,
)

__all__ = [
    "BUILDER_MAX_OUTPUT_TOKENS",
    "DEFAULT_MAX_RETRIES",
    "BuildResult",
    "Check",
    "Diagnosis",
    "build_template",
    "builder_input_text",
    "diagnose",
    "slugify",
]
