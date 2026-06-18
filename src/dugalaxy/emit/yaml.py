"""YAML writer for human-readable round-tripping — the Echo dataset envelope.

Emits the envelope Echo's seeder ingests directly: a header (version, dataset_name,
description) followed by a ``conversations:`` (or ``documents:``) list. Written
incrementally — the header once, then each item appended — so nothing accumulates
in memory. Each item is serialized with ``yaml.dump`` (then indented under the list
key), so quotes, backslashes, and newlines in content stay valid YAML.
"""

import textwrap
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

import yaml

from .record import Sample

_VERSION = "1.0"


class YamlEmitter:
    """Streams an Echo-style YAML envelope. Use as a context manager."""

    def __init__(
        self,
        path: Path,
        *,
        dataset_name: str,
        description: str,
        kind: str,
        include_meta: bool = False,
    ) -> None:
        self._path = path
        self._dataset_name = dataset_name
        self._description = description
        self._list_key = "conversations" if kind == "conversation" else "documents"
        self._include_meta = include_meta
        self._handle: TextIO | None = None
        self._count = 0

    def __enter__(self) -> "YamlEmitter":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("w", encoding="utf-8")
        header = yaml.dump(
            {
                "version": _VERSION,
                "dataset_name": self._dataset_name,
                "description": self._description,
            },
            sort_keys=False,
            allow_unicode=True,
        )
        self._handle.write(header)
        return self

    def emit(self, sample: Sample) -> None:
        if self._handle is None:  # pragma: no cover - guarded by context manager use
            raise RuntimeError("YamlEmitter used outside its context manager")
        if self._count == 0:
            self._handle.write(f"{self._list_key}:\n")
        item = _item_for(sample, include_meta=self._include_meta)
        block = yaml.dump(
            [item], sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000
        )
        self._handle.write(textwrap.indent(block, "  "))
        self._handle.flush()
        self._count += 1

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._handle is not None:
            if self._count == 0:
                self._handle.write(f"{self._list_key}: []\n")
            self._handle.close()


def _item_for(sample: Sample, *, include_meta: bool) -> dict[str, Any]:
    if sample.kind == "conversation":
        item: dict[str, Any] = {
            "session_id": sample.session_id,
            "turns": [{"role": role, "content": content} for role, content in sample.turns],
        }
    elif isinstance(sample.document, dict):
        item = dict(sample.document)
    else:
        item = {"content": sample.document}

    if include_meta:
        item["_meta"] = {"index": sample.index, "seed": sample.seed, "facts": sample.facts}
    return item
