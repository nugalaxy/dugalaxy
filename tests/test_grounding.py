"""Tests for grounding scenario facts into prompts and payloads — Milestone 2 acceptance."""

import json
from pathlib import Path
from typing import Any

from dugalaxy.generator.grounding import (
    GeneratedRequest,
    GroundedOutput,
    ground_output,
    requires_model,
)
from dugalaxy.scenario import generate_scenario
from dugalaxy.template.loader import load_template
from dugalaxy.template.spec import OutputSpec

FLAGSHIP = Path(__file__).parent.parent / "src" / "dugalaxy" / "templates" / "customer-support.yaml"


def _output(spec: dict[str, Any]) -> OutputSpec:
    from pydantic import TypeAdapter

    return TypeAdapter(OutputSpec).validate_python(spec)


# ── system prompt + fixed/generated grounding ─────────────────────────────────


def test_system_prompt_injects_facts() -> None:
    output = _output(
        {
            "type": "conversation",
            "system_prompt": "User is {{ scenario.user }}.",
            "turns": [{"role": "user", "content": {"type": "fixed", "value": "hi"}}],
        }
    )
    grounded = ground_output(output, {"user": "alice"})
    assert grounded.system_prompt == "User is alice."


def test_fixed_string_block_is_rendered() -> None:
    output = _output(
        {
            "type": "conversation",
            "turns": [
                {"role": "user", "content": {"type": "fixed", "value": "Hello {{ scenario.x }}"}}
            ],
        }
    )
    grounded = ground_output(output, {"x": "there"})
    assert grounded.blocks[0].value == "Hello there"
    assert grounded.blocks[0].request is None
    assert grounded.blocks[0].role == "user"


def test_fixed_map_block_keeps_structure() -> None:
    output = _output(
        {
            "type": "document",
            "content": {
                "type": "fixed",
                "value": {"user": "{{ scenario.u }}", "event": "login"},
            },
        }
    )
    grounded = ground_output(output, {"u": "bob"})
    assert grounded.kind == "document"
    assert grounded.blocks[0].value == {"user": "bob", "event": "login"}
    assert grounded.blocks[0].role is None


def test_generated_block_grounds_instruction_and_validation() -> None:
    output = _output(
        {
            "type": "conversation",
            "turns": [
                {
                    "role": "agent",
                    "content": {
                        "type": "generated",
                        "instruction": "Discuss {{ scenario.product }}.",
                        "max_tokens": 200,
                        "validation": {
                            "min_length": 50,
                            "must_mention": ["{{ scenario.product }}"],
                            "must_not_contain": ["As an AI"],
                        },
                    },
                }
            ],
        }
    )
    grounded = ground_output(output, {"product": "Nimbus CLI"})
    block = grounded.blocks[0]
    assert block.value is None
    request = block.request
    assert isinstance(request, GeneratedRequest)
    assert request.instruction == "Discuss Nimbus CLI."
    assert request.max_tokens == 200
    assert request.min_length == 50
    assert request.must_mention == ("Nimbus CLI",)  # reference resolved to the fact
    assert request.must_not_contain == ("As an AI",)


def test_generated_block_without_validation() -> None:
    output = _output(
        {
            "type": "conversation",
            "turns": [{"role": "agent", "content": {"type": "generated", "instruction": "Reply."}}],
        }
    )
    grounded = ground_output(output, {})
    request = grounded.blocks[0].request
    assert isinstance(request, GeneratedRequest)
    assert request.min_length is None
    assert request.must_mention == ()
    assert request.must_not_contain == ()


# ── flagship end-to-end grounding ─────────────────────────────────────────────


def test_flagship_grounding_produces_valid_embedded_json() -> None:
    """The agent's system prompt embeds the account record as JSON — it must parse."""
    spec = load_template(FLAGSHIP)
    facts = generate_scenario(spec.scenario, seed=42, index=0)
    grounded = ground_output(spec.output, facts)

    assert isinstance(grounded, GroundedOutput)
    assert grounded.kind == "conversation"
    assert grounded.system_prompt is not None
    assert facts["customer"] in grounded.system_prompt

    embedded = grounded.system_prompt.split("```json\n", 1)[1].split("\n```", 1)[0]
    assert json.loads(embedded) == facts["account_record"]

    # The customer turn is natural prose — no JSON pasted by the customer.
    user_block = grounded.blocks[0]
    assert isinstance(user_block.value, str)
    assert "```json" not in user_block.value

    agent_request = grounded.blocks[1].request
    assert isinstance(agent_request, GeneratedRequest)
    assert agent_request.must_mention == (facts["ticket_id"],)


def test_grounding_is_deterministic() -> None:
    spec = load_template(FLAGSHIP)
    facts = generate_scenario(spec.scenario, seed=7, index=3)
    assert ground_output(spec.output, facts) == ground_output(spec.output, facts)


# ── deterministic-only detection ──────────────────────────────────────────────


def test_requires_model_true_when_generated_present() -> None:
    spec = load_template(FLAGSHIP)
    assert requires_model(spec.output) is True


def test_requires_model_false_for_all_fixed_conversation() -> None:
    output = _output(
        {
            "type": "conversation",
            "turns": [{"role": "user", "content": {"type": "fixed", "value": "hi"}}],
        }
    )
    assert requires_model(output) is False


def test_requires_model_document_variants() -> None:
    fixed_doc = _output({"type": "document", "content": {"type": "fixed", "value": {"k": "v"}}})
    generated_doc = _output(
        {"type": "document", "content": {"type": "generated", "instruction": "write"}}
    )
    assert requires_model(fixed_doc) is False
    assert requires_model(generated_doc) is True


# ── validity trap end-to-end (nasty values through the whole pipeline) ─────────


def test_nasty_scenario_value_stays_valid_json_in_prose() -> None:
    """A scenario value with quotes/backslashes/newlines must serialize validly."""
    nasty = 'cmd "x" \\ end\nNEXT'
    output = _output(
        {
            "type": "conversation",
            "turns": [
                {
                    "role": "user",
                    "content": {
                        "type": "fixed",
                        "value": "```json\n{{ scenario.payload | json(indent=2) }}\n```",
                    },
                }
            ],
        }
    )
    facts = {"payload": {"command_line": nasty}}
    grounded = ground_output(output, facts)
    assert isinstance(grounded.blocks[0].value, str)
    embedded = grounded.blocks[0].value.split("```json\n", 1)[1].split("\n```", 1)[0]
    assert json.loads(embedded) == {"command_line": nasty}
