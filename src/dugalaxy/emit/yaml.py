"""YAML writer for human-readable round-tripping — the Echo dataset envelope.

Emits the envelope Echo's seeder ingests directly: a header (version, dataset_name,
description) followed by a ``conversations:`` (or ``documents:``) list. Written
incrementally — the header once, then each item appended — so nothing accumulates
in memory. Each item is serialized with ``yaml.dump`` (then indented under the list
key), so quotes, backslashes, and newlines in content stay valid YAML.

Multi-line strings (our JSON-bearing turns, multi-paragraph prose) render as block
literals (``|``) rather than double-quoted scalars with ``\\n`` escapes, so embedded
JSON shows up cleanly indented. That preference lives on a local ``SafeDumper``
subclass — never registered on PyYAML's shared Dumper — so it cannot leak into other
code that serializes YAML.
"""

import textwrap
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

import yaml

from .record import Sample

_VERSION = "1.0"


class _BlockDumper(yaml.SafeDumper):
    """SafeDumper that prefers block literals for multi-line strings.

    A subclass (not a global representer) so the block-style preference stays
    scoped to this emitter and never mutates PyYAML's shared Dumper state.
    """


def _represent_str(dumper: _BlockDumper, data: str) -> yaml.ScalarNode:
    """Render strings containing a newline as ``|`` block scalars.

    For everything else, pass ``style=None`` and let PyYAML pick its usual style.
    PyYAML also falls back to a quoted style on its own when a string cannot be a
    valid block scalar (e.g. trailing whitespace) — that graceful degradation to
    valid YAML is fine and intentionally not fought.
    """
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_BlockDumper.add_representer(str, _represent_str)


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
            Dumper=_BlockDumper,
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
            [item],
            Dumper=_BlockDumper,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=1000,
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
