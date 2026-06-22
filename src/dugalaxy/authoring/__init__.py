"""Authoring aids: helping a user reach a working setup and a working template.

This package holds the user-onboarding surfaces that sit *around* the generation
engine — the things that turn a cold `pip install` into a first success. It starts
with diagnostics (`dugalaxy doctor`); the AI template builder lands here later.
"""

from .diagnostics import Check, Diagnosis, diagnose

__all__ = ["Check", "Diagnosis", "diagnose"]
