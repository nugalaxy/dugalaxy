"""JSONL writer. One sample per line — the lingua franca of LLM eval/fine-tune datasets.

Disk-backed: each sample is serialized and flushed as it is produced, so nothing
accumulates in memory. ``json.dumps`` guarantees valid, escaped output.
"""

import json
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

from .record import Sample


class JsonlEmitter:
    """Writes one JSON object per line. Use as a context manager."""

    def __init__(self, path: Path, *, include_meta: bool = False) -> None:
        self._path = path
        self._include_meta = include_meta
        self._handle: TextIO | None = None

    def __enter__(self) -> "JsonlEmitter":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("w", encoding="utf-8")
        return self

    def emit(self, sample: Sample) -> None:
        if self._handle is None:  # pragma: no cover - guarded by context manager use
            raise RuntimeError("JsonlEmitter used outside its context manager")
        record = _record_for(sample, include_meta=self._include_meta)
        self._handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._handle.flush()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._handle is not None:
            self._handle.close()


def _record_for(sample: Sample, *, include_meta: bool) -> dict[str, Any]:
    if sample.kind == "conversation":
        record: dict[str, Any] = {
            "session_id": sample.session_id,
            "turns": [{"role": role, "content": content} for role, content in sample.turns],
        }
    elif isinstance(sample.document, dict):
        record = dict(sample.document)  # structured document is the line itself
    else:
        record = {"content": sample.document}

    if include_meta:
        record["_meta"] = {"index": sample.index, "seed": sample.seed, "facts": sample.facts}
    return record
