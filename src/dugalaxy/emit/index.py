"""Local index of produced samples for tracking and resumability.

One JSON line per produced sample (index, session_id, seed), written as each sample
lands so a run's progress is always on disk.
"""

import json
from pathlib import Path
from types import TracebackType
from typing import TextIO

from .record import Sample


class IndexEmitter:
    """Appends a small tracking record per produced sample. Use as a context manager."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: TextIO | None = None

    def __enter__(self) -> "IndexEmitter":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("w", encoding="utf-8")
        return self

    def emit(self, sample: Sample) -> None:
        if self._handle is None:  # pragma: no cover - guarded by context manager use
            raise RuntimeError("IndexEmitter used outside its context manager")
        entry = {"index": sample.index, "session_id": sample.session_id, "seed": sample.seed}
        self._handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._handle.flush()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._handle is not None:
            self._handle.close()
