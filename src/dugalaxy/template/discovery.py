"""Discover the templates Dugalaxy can run: the bundled examples plus any the user
has in their working directory.

Used by ``dugalaxy list`` and by the interactive picker when ``dugalaxy gen`` is run
without a template. Discovery is deliberately lightweight — it reads each file's
``meta`` for a name and description but does not fully validate it (a half-written
template should still be listable). Ordering matches resolution precedence: a user's
own templates come before the bundled examples that share a name.
"""

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TemplateInfo:
    """A template Dugalaxy found, for listing and selection."""

    name: str
    description: str
    source: str  # human label: "bundled", "./templates", or "./"
    path: Path


def _read_meta(path: Path) -> tuple[str, str] | None:
    """Return ``(name, description)`` if *path* looks like a template, else ``None``."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict) or "scenario" not in raw or "output" not in raw:
        return None
    meta_raw = raw.get("meta")
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    name = str(meta.get("name") or path.stem)
    description = str(meta.get("description") or "")
    return name, description


def discover_templates() -> list[TemplateInfo]:
    """Find templates in the working directory and the bundled examples.

    Working-directory templates are listed first (they win during resolution), then
    bundled examples whose name isn't already taken locally.
    """
    found: list[TemplateInfo] = []
    local_names: set[str] = set()

    for directory, label in ((Path("templates"), "./templates"), (Path("."), "./")):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            meta = _read_meta(path)
            if meta is None:
                continue
            name, description = meta
            found.append(TemplateInfo(name, description, label, path))
            local_names.add(name)

    bundled_dir = files("dugalaxy") / "templates"
    for entry in sorted(bundled_dir.iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".yaml"):
            continue
        path = Path(str(entry))
        meta = _read_meta(path)
        if meta is None or meta[0] in local_names:
            continue
        found.append(TemplateInfo(meta[0], meta[1], "bundled", path))

    return found
