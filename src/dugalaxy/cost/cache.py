"""Response cache keyed by (prompt + params) hash. Makes seeded prose reproducible on cache hit.

Disk-backed so it survives across runs: an identical prompt (same backend, model,
system, messages, and max_tokens) returns the stored completion instead of calling
— and paying for — the provider again. One small JSON file per cache key.

The cache is robust to crashes: writes are atomic (temp file then ``os.replace``),
and a corrupted or partially written entry is treated as a miss rather than an error.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from dugalaxy.providers.base import Completion, CompletionRequest, Usage


class ResponseCache:
    """A simple disk cache of provider completions, keyed by request + backend."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_key(request: CompletionRequest, fingerprint: str) -> str:
        """Stable SHA-256 key over everything that can change the model's output.

        ``fingerprint`` identifies the backend (provider + endpoint + model), so the
        same model string served by two different endpoints never collides.
        """
        payload = {
            "fingerprint": fingerprint,
            "system": request.system,
            "max_tokens": request.max_tokens,
            "messages": [[m.role, m.content] for m in request.messages],
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, key: str) -> Completion | None:
        """Return the cached completion for *key*, or ``None`` on a miss.

        A missing, unreadable, or corrupted entry (e.g. a partial write from a
        crashed run) is treated as a miss so it is simply regenerated.
        """
        path = self._path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Completion(
                text=data["text"],
                usage=Usage(
                    input_tokens=data.get("input_tokens", 0),
                    output_tokens=data.get("output_tokens", 0),
                ),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def put(self, key: str, completion: Completion) -> None:
        """Atomically store *completion* under *key*.

        Writes to a temp file in the same directory, then ``os.replace`` swaps it in
        — so a reader never sees a half-written entry.
        """
        record = {
            "text": completion.text,
            "input_tokens": completion.usage.input_tokens,
            "output_tokens": completion.usage.output_tokens,
        }
        blob = json.dumps(record, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(dir=self._dir, prefix=f"{key}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(blob)
            os.replace(tmp_name, self._path(key))
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
