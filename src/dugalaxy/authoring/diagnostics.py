"""Plain-words environment diagnostics behind ``dugalaxy doctor``.

A tired user whose run just failed needs to know *which* piece is missing and the
one command that fixes it — not a stack trace. :func:`diagnose` runs a handful of
fast, read-only checks (config, provider reachability, API key, templates, output
directory) and returns a structured result the CLI renders as ✓/✗ lines plus the
single most useful next action. The same checks are reused inside the guided
first-run flow.

The checks never read an API key's *value* (only whether its named variable is
set), and never write anything except a short-lived probe file when testing that
the output directory is writable.
"""

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from dugalaxy.config.loader import load_config
from dugalaxy.config.schema import Config, ConfigError
from dugalaxy.providers import DEFAULT_BASE_URLS
from dugalaxy.template.discovery import discover_templates

# The zero-setup win always works (deterministic, no model), so it is the natural
# fallback to offer whenever only the model path is missing.
_QUICKSTART_HINT = "Or see it work now with no setup: dugalaxy gen quickstart"


@dataclass(frozen=True)
class Check:
    """One diagnostic line: a label, pass/fail, the finding, and an optional fix."""

    label: str
    ok: bool
    detail: str
    fix: str | None = None


@dataclass(frozen=True)
class Diagnosis:
    """The full health check: the individual checks plus the single next action."""

    checks: list[Check]
    next_action: str

    @property
    def ok(self) -> bool:
        """True when every check passed."""
        return all(check.ok for check in self.checks)


def diagnose(
    *,
    config_path: Path | None = None,
    overrides: Mapping[str, Any] | None = None,
    cwd: Path | None = None,
    ollama_client: httpx.Client | None = None,
) -> Diagnosis:
    """Run the environment checks and return a :class:`Diagnosis`.

    *config_path* is an explicit config file; when ``None`` a ``dugalaxy.config.yaml``
    in *cwd* is used if present (else built-in defaults). *overrides* are CLI flags
    (``provider``/``model``/…), matching ``gen``'s precedence. *ollama_client* lets a
    test inject a transport for the reachability probe; in production a short-timeout
    client is created.
    """
    cwd = cwd or Path.cwd()
    checks: list[Check] = []

    config_check, config = _check_config(config_path, overrides, cwd)
    checks.append(config_check)
    if config is not None:
        checks.extend(_check_provider(config, ollama_client))
    checks.append(_check_templates())
    checks.append(_check_output_writable(cwd))

    return Diagnosis(checks=checks, next_action=_next_action(checks))


def _check_config(
    config_path: Path | None,
    overrides: Mapping[str, Any] | None,
    cwd: Path,
) -> tuple[Check, Config | None]:
    """Resolve the effective config, reporting whether a file was found and valid.

    A missing config file is fine — Dugalaxy defaults to local Ollama — so absence is
    a pass. An unreadable or invalid file is a real failure, and we return no config
    so the dependent provider checks are skipped rather than run on bad data.
    """
    path = config_path or (cwd / "dugalaxy.config.yaml")
    present = path.is_file()
    try:
        config = load_config(path if present else None, overrides=overrides)
    except ConfigError as exc:
        # The full reason belongs in the detail (shown under this ✗ line); the fix —
        # which also becomes the single "Next:" action — must stay one short, readable
        # instruction, never a multi-line validation dump.
        return (
            Check(
                "Config",
                False,
                f"{path} is invalid:\n{exc}",
                "Fix the errors above in the config file, or remove it to use defaults.",
            ),
            None,
        )

    if present:
        detail = f"using {path}"
    else:
        detail = "no config file — using defaults (provider: ollama, local)"
    return Check("Config", True, detail), config


def _check_provider(config: Config, client: httpx.Client | None) -> list[Check]:
    """Check the resolved provider is usable: Ollama reachable, or a hosted key set."""
    base_url = config.base_url or DEFAULT_BASE_URLS[config.provider]

    if config.provider == "ollama":
        if _ollama_reachable(base_url, client):
            provider = Check(
                "Provider", True, f"Ollama reachable at {base_url} (model: {config.model})"
            )
        else:
            provider = Check(
                "Provider",
                False,
                f"Ollama not reachable at {base_url}",
                f"Start Ollama and run `ollama pull {config.model}`, "
                "or pick a hosted provider with --provider/--model.",
            )
        return [provider, Check("API key", True, "not needed (Ollama is local)")]

    provider = Check("Provider", True, f"{config.provider} / {config.model} at {base_url}")
    if not config.api_key_env:
        key = Check(
            "API key",
            False,
            f"no api_key_env set for provider '{config.provider}'",
            "Set 'api_key_env' in dugalaxy.config.yaml to the env var holding your key.",
        )
    elif os.environ.get(config.api_key_env):
        key = Check("API key", True, f"{config.api_key_env} is set")
    else:
        key = Check(
            "API key",
            False,
            f"{config.api_key_env} is not set in the environment",
            f'Set it, e.g.  $env:{config.api_key_env}="..."  (PowerShell).',
        )
    return [provider, key]


def _ollama_reachable(base_url: str, client: httpx.Client | None) -> bool:
    """Return True if a local Ollama server answers at *base_url*.

    Uses the cheap ``/api/tags`` endpoint with a short timeout; any connection or
    HTTP error means "not reachable" — this is a diagnosis, never a hard failure.
    """
    url = base_url.rstrip("/") + "/api/tags"
    owned = client is None
    client = client or httpx.Client(timeout=2.0)
    try:
        return client.get(url).status_code < 400
    except httpx.HTTPError:
        return False
    finally:
        if owned:
            client.close()


def _check_templates() -> Check:
    """Count the templates Dugalaxy can find (bundled examples + the user's own)."""
    count = len(discover_templates())
    if count:
        return Check("Templates", True, f"{count} found (bundled examples + your own)")
    return Check(
        "Templates",
        False,
        "none found",
        "Run `dugalaxy init` to scaffold one.",
    )


def _check_output_writable(cwd: Path) -> Check:
    """Confirm output can be written by creating a probe file in *cwd*.

    Uses a uniquely-named temp file (auto-removed) so the check can never truncate or
    delete a user's own file, and never leaves a stray probe behind.
    """
    try:
        with tempfile.NamedTemporaryFile(dir=cwd, prefix=".dugalaxy-write-probe-"):
            pass
    except OSError as exc:
        reason = exc.strerror or str(exc)
        return Check(
            "Output dir",
            False,
            f"{cwd} is not writable ({reason})",
            "Point output somewhere writable with --output-dir, or fix this directory's "
            "permissions.",
        )
    return Check("Output dir", True, f"{cwd} is writable")


def _next_action(checks: list[Check]) -> str:
    """Pick the single most useful next step from the check results.

    All green → point at the instant demo. If only the model path is missing, the
    user can still get a win with zero setup, so lead with that fix *and* the
    quickstart. Otherwise surface the first real fix.
    """
    failed = [check for check in checks if not check.ok]
    if not failed:
        return "Ready — try: dugalaxy gen quickstart"

    model_labels = {"Provider", "API key"}
    if all(check.label in model_labels for check in failed):
        fix = failed[0].fix or _QUICKSTART_HINT
        return f"{fix}  {_QUICKSTART_HINT}"
    return failed[0].fix or _QUICKSTART_HINT
