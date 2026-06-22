"""Tests for the doctor diagnostics core — Milestone 1 (onboarding).

No real network: the Ollama reachability probe is driven by an httpx.MockTransport,
matching the provider-test idiom.
"""

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from dugalaxy.authoring import diagnose
from dugalaxy.authoring.diagnostics import Check, Diagnosis


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ollama_up(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"models": []})


def _ollama_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _check(diagnosis: Diagnosis, label: str) -> Check:
    return next(c for c in diagnosis.checks if c.label == label)


def test_no_config_falls_back_to_local_ollama(tmp_path: Path) -> None:
    diagnosis = diagnose(cwd=tmp_path, ollama_client=_client(_ollama_up))
    config = _check(diagnosis, "Config")
    assert config.ok
    assert "no config file" in config.detail


def test_ollama_reachable_is_a_pass(tmp_path: Path) -> None:
    diagnosis = diagnose(cwd=tmp_path, ollama_client=_client(_ollama_up))
    provider = _check(diagnosis, "Provider")
    assert provider.ok
    assert "reachable" in provider.detail
    # A local provider needs no key.
    assert _check(diagnosis, "API key").ok


def test_ollama_unreachable_is_a_fail_with_fix(tmp_path: Path) -> None:
    diagnosis = diagnose(cwd=tmp_path, ollama_client=_client(_ollama_down))
    provider = _check(diagnosis, "Provider")
    assert not provider.ok
    assert provider.fix is not None and "ollama pull" in provider.fix.lower()
    # Only the model path is down, so the next action still offers the zero-setup win.
    assert "quickstart" in diagnosis.next_action


def test_hosted_provider_with_key_set_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DUGALAXY_DOCTOR_KEY", "sk-x")
    diagnosis = diagnose(
        cwd=tmp_path,
        overrides={"provider": "openai_compatible", "api_key_env": "DUGALAXY_DOCTOR_KEY"},
    )
    assert _check(diagnosis, "Provider").ok
    key = _check(diagnosis, "API key")
    assert key.ok and "DUGALAXY_DOCTOR_KEY" in key.detail


def test_hosted_provider_with_key_unset_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DUGALAXY_DOCTOR_KEY", raising=False)
    diagnosis = diagnose(
        cwd=tmp_path,
        overrides={"provider": "openai_compatible", "api_key_env": "DUGALAXY_DOCTOR_KEY"},
    )
    key = _check(diagnosis, "API key")
    assert not key.ok
    assert key.fix is not None and "DUGALAXY_DOCTOR_KEY" in key.fix
    assert diagnosis.next_action == key.fix or key.fix in diagnosis.next_action


def test_hosted_provider_without_api_key_env_fails(tmp_path: Path) -> None:
    diagnosis = diagnose(cwd=tmp_path, overrides={"provider": "openai_compatible"})
    key = _check(diagnosis, "API key")
    assert not key.ok
    assert "api_key_env" in key.detail


def test_never_reads_the_key_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUGALAXY_DOCTOR_KEY", "super-secret-value")
    diagnosis = diagnose(
        cwd=tmp_path,
        overrides={"provider": "anthropic", "api_key_env": "DUGALAXY_DOCTOR_KEY"},
    )
    rendered = " ".join(c.detail + (c.fix or "") for c in diagnosis.checks)
    assert "super-secret-value" not in rendered


def test_invalid_config_file_fails_and_skips_provider(tmp_path: Path) -> None:
    bad = tmp_path / "dugalaxy.config.yaml"
    bad.write_text("provider: not_a_real_provider\n", encoding="utf-8")
    diagnosis = diagnose(config_path=bad, cwd=tmp_path)
    config = _check(diagnosis, "Config")
    assert not config.ok
    # With no valid config, the provider checks are skipped rather than run on bad data.
    assert not any(c.label == "Provider" for c in diagnosis.checks)


def test_templates_are_found_from_bundled_examples(tmp_path: Path) -> None:
    diagnosis = diagnose(cwd=tmp_path, ollama_client=_client(_ollama_up))
    templates = _check(diagnosis, "Templates")
    assert templates.ok  # bundled examples always ship


def test_output_dir_writable_passes(tmp_path: Path) -> None:
    diagnosis = diagnose(cwd=tmp_path, ollama_client=_client(_ollama_up))
    assert _check(diagnosis, "Output dir").ok


def test_output_dir_not_writable_fails_with_fix(tmp_path: Path) -> None:
    # A non-existent directory makes the probe creation raise OSError — a reliable,
    # cross-platform stand-in for "can't write here".
    missing = tmp_path / "does-not-exist"
    diagnosis = diagnose(cwd=missing, ollama_client=_client(_ollama_up))
    out = _check(diagnosis, "Output dir")
    assert not out.ok
    assert out.fix is not None and "--output-dir" in out.fix


def test_no_templates_found_fails_with_fix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dugalaxy.authoring.diagnostics.discover_templates", lambda: [])
    diagnosis = diagnose(cwd=tmp_path, ollama_client=_client(_ollama_up))
    templates = _check(diagnosis, "Templates")
    assert not templates.ok
    assert templates.fix is not None and "init" in templates.fix


def test_invalid_config_next_action_is_a_single_legible_line(tmp_path: Path) -> None:
    # Regression: the raw multi-line validation error must never become the next action.
    bad = tmp_path / "dugalaxy.config.yaml"
    bad.write_text("provider: not_a_real_provider\n", encoding="utf-8")
    diagnosis = diagnose(config_path=bad, cwd=tmp_path)
    assert "\n" not in diagnosis.next_action
    assert "validation error" not in diagnosis.next_action.lower()


def test_all_green_next_action_points_at_quickstart(tmp_path: Path) -> None:
    diagnosis = diagnose(cwd=tmp_path, ollama_client=_client(_ollama_up))
    assert diagnosis.ok
    assert "quickstart" in diagnosis.next_action
