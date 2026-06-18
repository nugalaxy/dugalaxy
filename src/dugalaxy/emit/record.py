"""The Sample record: one produced sample, ready for any emitter to write.

Lives in its own leaf module so both the emitters and the generator core can
depend on it without an import cycle.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Sample:
    """One produced sample.

    A conversation sample carries ``turns`` (ordered ``(role, content)`` pairs) and
    ``document`` is ``None``; a document sample carries ``document`` (a structured
    map or a prose string) and ``turns`` is empty. ``facts`` and ``seed`` are
    retained for the index and for optional ``--include-meta`` output.
    """

    index: int
    session_id: str
    kind: str  # "conversation" | "document"
    turns: tuple[tuple[str, str], ...]
    document: str | dict[str, Any] | None
    facts: dict[str, Any]
    seed: int


class SampleEmitter(Protocol):
    """A disk-backed writer that emits one produced sample at a time."""

    def emit(self, sample: Sample) -> None: ...
