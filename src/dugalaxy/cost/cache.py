"""Response cache keyed by (prompt + params) hash. Makes seeded prose reproducible on cache hit.

Disk-backed so it survives across runs: an identical prompt (same system, messages,
model, and max_tokens) returns the stored completion instead of calling — and paying
for — the provider again. One small JSON file per cache key.
"""

import hashlib
import json
from pathlib import Path

from dugalaxy.providers.base import Completion, CompletionRequest, Usage


class ResponseCache:
    """A simple disk cache of provider completions, keyed by request + model."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_key(request: CompletionRequest, model: str) -> str:
        """Stable SHA-256 key over everything that can change the model's output."""
        payload = {
            "model": model,
            "system": request.system,
            "max_tokens": request.max_tokens,
            "messages": [[m.role, m.content] for m in request.messages],
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, key: str) -> Completion | None:
        """Return the cached completion for *key*, or ``None`` on a miss."""
        path = self._path(key)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Completion(
            text=data["text"],
            usage=Usage(
                input_tokens=data.get("input_tokens", 0),
                output_tokens=data.get("output_tokens", 0),
            ),
        )

    def put(self, key: str, completion: Completion) -> None:
        """Store *completion* under *key*."""
        record = {
            "text": completion.text,
            "input_tokens": completion.usage.input_tokens,
            "output_tokens": completion.usage.output_tokens,
        }
        self._path(key).write_text(
            json.dumps(record, ensure_ascii=False),
            encoding="utf-8",
        )
