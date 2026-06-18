"""Curated whitelist of exposed faker providers.

Only the providers listed here can be used from a template. Each is rendered
through a per-variable-seeded :class:`~faker.Faker` instance so that, given the
same seed, the same value comes out every run (the determinism contract, §3.3).
Exposing a small, named set keeps templates portable and the surface auditable.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from faker import Faker

from dugalaxy.template.errors import UnknownFakerKindError
from dugalaxy.template.spec import FakerVar

# Each provider takes the seeded Faker instance plus any template kwargs (e.g.
# ``days_back``) and returns a string. Unknown kwargs are ignored.
FakerProvider = Callable[..., str]

# Fixed reference "now" for time-based providers, interpreted as UTC. Anchoring to
# a recorded constant — rather than wall-clock time — is what makes timestamps
# reproduce across calendar time, not just across machines and processes. A
# template may override it per variable with an ``anchor`` kwarg (ISO-8601).
DEFAULT_DATETIME_ANCHOR = "2025-01-01T00:00:00"


def _datetime_recent(
    fake: Faker,
    days_back: int = 30,
    anchor: str = DEFAULT_DATETIME_ANCHOR,
    **_: Any,
) -> str:
    """An ISO-8601 UTC timestamp within ``days_back`` days before ``anchor``.

    The offset within the window is drawn from the seeded Faker instance, and the
    window end is the fixed ``anchor`` — so the result depends only on the seed and
    these kwargs, never on the wall clock or the host timezone.
    """
    end = datetime.fromisoformat(anchor)
    window_seconds = days_back * 24 * 60 * 60
    offset = int(fake.random_int(0, window_seconds))
    dt = end - timedelta(seconds=offset)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ipv4(fake: Faker, **_: Any) -> str:
    return str(fake.ipv4())


def _name(fake: Faker, **_: Any) -> str:
    return str(fake.name())


def _email(fake: Faker, **_: Any) -> str:
    return str(fake.email())


def _uuid4(fake: Faker, **_: Any) -> str:
    return str(fake.uuid4())


def _domain_name(fake: Faker, **_: Any) -> str:
    return str(fake.domain_name())


def _mac_address(fake: Faker, **_: Any) -> str:
    return str(fake.mac_address())


def _sha256(fake: Faker, **_: Any) -> str:
    """A 64-char hex digest — stands in for a file or process hash."""
    return str(fake.sha256())


def _file_path(fake: Faker, **_: Any) -> str:
    """A filesystem path — stands in for a process image path."""
    return str(fake.file_path())


def _hostname(fake: Faker, **_: Any) -> str:
    """A host/workstation name."""
    return str(fake.hostname())


FAKER_PROVIDERS: dict[str, FakerProvider] = {
    "datetime_recent": _datetime_recent,
    "ipv4": _ipv4,
    "name": _name,
    "email": _email,
    "uuid4": _uuid4,
    "domain_name": _domain_name,
    "mac_address": _mac_address,
    # Security-oriented kinds for SOC/EDR-style telemetry.
    "sha256": _sha256,
    "file_path": _file_path,
    "hostname": _hostname,
}

# Public, stable view of the supported kinds (used for validation messages/tests).
FAKER_KINDS: frozenset[str] = frozenset(FAKER_PROVIDERS)


def render_faker(var: FakerVar, seed: int) -> str:
    """Render a ``faker`` variable deterministically from *seed*.

    Raises:
        UnknownFakerKindError: ``var.kind`` is not in the whitelist.
    """
    provider = FAKER_PROVIDERS.get(var.kind)
    if provider is None:
        valid = ", ".join(sorted(FAKER_KINDS))
        raise UnknownFakerKindError(f"Unknown faker kind '{var.kind}'. Supported kinds: {valid}.")
    fake = Faker()
    fake.seed_instance(seed)
    kwargs = var.model_extra or {}
    return provider(fake, **kwargs)
