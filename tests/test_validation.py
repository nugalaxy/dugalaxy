"""Tests for structural validation of generated content — Milestone 4."""

from dugalaxy.generator.grounding import GeneratedRequest
from dugalaxy.generator.validation import validate_generated


def _request(**kwargs: object) -> GeneratedRequest:
    base: dict[str, object] = {
        "instruction": "write something",
        "max_tokens": None,
        "min_length": None,
        "max_length": None,
        "must_mention": (),
        "must_not_contain": (),
    }
    base.update(kwargs)
    return GeneratedRequest(**base)  # type: ignore[arg-type]


def test_passes_clean_text() -> None:
    result = validate_generated("A perfectly fine reply.", _request())
    assert result.ok
    assert result.reason is None


def test_empty_text_fails() -> None:
    assert validate_generated("   \n  ", _request()).ok is False


def test_min_length_enforced() -> None:
    result = validate_generated("short", _request(min_length=100))
    assert not result.ok
    assert "too short" in (result.reason or "")


def test_max_length_enforced() -> None:
    result = validate_generated("x" * 50, _request(max_length=10))
    assert not result.ok
    assert "too long" in (result.reason or "")


def test_must_mention_present_passes() -> None:
    result = validate_generated("Your ticket is TICKET-42.", _request(must_mention=("TICKET-42",)))
    assert result.ok


def test_must_mention_absent_fails() -> None:
    result = validate_generated("No ticket id here.", _request(must_mention=("TICKET-42",)))
    assert not result.ok
    assert "TICKET-42" in (result.reason or "")


def test_must_not_contain_blocks_banned_text() -> None:
    result = validate_generated(
        "As an AI, I cannot help.", _request(must_not_contain=("As an AI",))
    )
    assert not result.ok
    assert "banned" in (result.reason or "")


def test_combined_checks_pass() -> None:
    text = "Your order ORD-1 is confirmed and invoice INV-9 is attached; thanks!"
    result = validate_generated(
        text,
        _request(min_length=20, max_length=200, must_mention=("ORD-1", "INV-9")),
    )
    assert result.ok
