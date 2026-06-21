"""Tests for template discovery — the data behind `dugalaxy list` and the picker."""

from pathlib import Path

import pytest

from dugalaxy.template.discovery import discover_templates

_TEMPLATE = """\
meta:
  name: my-local
  description: a local one
scenario:
  variables:
    x:
      type: choice
      values: ["a"]
output:
  type: document
  content:
    type: fixed
    value: "{{ scenario.x }}"
generation:
  n: 1
"""


def test_discovers_bundled_customer_support(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no local templates here
    infos = discover_templates()
    names = {i.name for i in infos}
    assert "customer-support" in names
    assert all(i.source == "bundled" for i in infos)


def test_local_template_listed_and_shadows_bundled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "my-local.yaml").write_text(_TEMPLATE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    infos = discover_templates()
    local = [i for i in infos if i.name == "my-local"]
    assert len(local) == 1
    assert local[0].source == "./templates"
    assert local[0].description == "a local one"


def test_non_template_yaml_is_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A config-like YAML with no scenario/output must not appear as a template.
    (tmp_path / "dugalaxy.config.yaml").write_text("provider: ollama\nmodel: llama3.2\n", "utf-8")
    monkeypatch.chdir(tmp_path)

    names = {i.name for i in discover_templates()}
    assert "dugalaxy.config" not in names


def test_missing_bundled_dir_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # An unusual install with no bundled templates dir must return [] — never a
    # raw traceback from .iterdir() on a path that isn't there.
    class _Absent:
        def __truediv__(self, _name: str) -> "_Absent":
            return self

        def is_dir(self) -> bool:
            return False

    monkeypatch.setattr("dugalaxy.template.discovery.files", lambda _pkg: _Absent())
    monkeypatch.chdir(tmp_path)  # no local templates either

    assert discover_templates() == []
