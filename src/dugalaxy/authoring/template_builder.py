"""The AI template builder: turn a one-line description into a valid template.

This is the bridge that lets a user reach Dugalaxy's value without learning the YAML
by hand. A model drafts a template from the user's description; we validate that draft
with the *real* loader and, on failure, hand the legible error back to the model to fix
(up to a small retry budget). Two guarantees make it safe to trust:

1. **Never a broken file.** A draft is written only after it loads cleanly. If the model
   can't produce a valid template, we fall back to copying the closest bundled example —
   the user is never left blocked, even offline or with no model.
2. **Honest.** The result is a *starting point*, never claimed as verified. The caller
   says so to the user.

The grammar and the faker-kind whitelist in the prompt are derived from the live code
(the bundled examples and ``FAKER_KINDS``), so they cannot drift from what the loader
actually accepts.
"""

import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from dugalaxy.providers.base import (
    CompletionRequest,
    Message,
    ProviderError,
    TextProvider,
)
from dugalaxy.scenario.faker_registry import FAKER_KINDS
from dugalaxy.template.errors import DugalaxyError
from dugalaxy.template.loader import load_template_text
from dugalaxy.template.spec import ConversationOutput, TemplateSpec

# The two vetted, public examples we use both as few-shot prompts and as fallbacks.
# Restricting fallbacks to this explicit pair (never `discover_templates`) keeps the
# private security template — and any unvetted local templates — out of generated files.
_CONVERSATION_EXAMPLE = "customer-support"
_DOCUMENT_EXAMPLE = "quickstart"

# Words in a description that hint at a single artifact (a document) rather than a
# back-and-forth (a conversation); used only to pick the closer fallback example.
_DOCUMENT_HINTS = frozenset(
    {
        "email",
        "report",
        "document",
        "invoice",
        "post",
        "article",
        "profile",
        "record",
        "form",
        "review",
        "summary",
        "note",
        "listing",
        "description",
    }
)

# Enough tokens for a full template; templates run ~120 lines.
BUILDER_MAX_OUTPUT_TOKENS = 2048

# How many times the model may try to fix an invalid draft before we fall back.
DEFAULT_MAX_RETRIES = 3


@dataclass(frozen=True)
class BuildResult:
    """The outcome of a build: where the template landed and how we got there."""

    path: Path
    output_shape: str  # "conversation" or "document"
    from_fallback: bool
    attempts: int  # model calls made (0 when no model was available)
    fallback_source: str | None = None  # bundled example copied, when from_fallback
    last_error: str | None = None  # the final validation/provider error, when from_fallback


def build_template(
    description: str,
    *,
    provider: TextProvider | None,
    name: str | None = None,
    output_dir: Path | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> BuildResult:
    """Draft a valid template for *description*, writing it to ``<slug>.yaml``.

    With a *provider*, the model drafts the template and we validate-and-retry. Without
    one (or if every attempt fails), we copy the closest bundled example so the user is
    never blocked. The destination never overwrites an existing file. The returned
    template is always loadable; ``from_fallback`` says whether it came from the model.
    """
    out_dir = output_dir or Path.cwd()
    dest = _unique_path(out_dir / f"{slugify(name or description)}.yaml")

    yaml_text: str | None = None
    spec: TemplateSpec | None = None
    attempts = 0
    last_error: str | None = None
    if provider is not None:
        yaml_text, spec, attempts, last_error = _generate_with_retries(
            description, provider, max_retries
        )
    else:
        last_error = "no model available"

    if yaml_text is not None and spec is not None:
        dest.write_text(yaml_text, encoding="utf-8")
        return BuildResult(
            path=dest,
            output_shape=_output_shape(spec),
            from_fallback=False,
            attempts=attempts,
        )

    source_name = _closest_example(description)
    source_text = _example_text(source_name)
    spec = load_template_text(source_text, source=f"bundled example '{source_name}'")
    dest.write_text(source_text, encoding="utf-8")
    return BuildResult(
        path=dest,
        output_shape=_output_shape(spec),
        from_fallback=True,
        attempts=attempts,
        fallback_source=source_name,
        last_error=last_error,
    )


def _generate_with_retries(
    description: str, provider: TextProvider, max_retries: int
) -> tuple[str | None, TemplateSpec | None, int, str | None]:
    """Run the generate-and-validate loop; return ``(yaml_text, spec, attempts, last_error)``.

    ``yaml_text``/``spec`` are ``None`` if no attempt produced a loadable template. The
    validated spec is returned so the caller need not re-parse. On a validation failure we
    append the legible loader error to the conversation and ask for a fix; a provider
    failure can't be fixed by retrying, so we stop and let the caller fall back.
    """
    system = _system_prompt()
    conversation: list[Message] = [Message(role="user", content=_task_prompt(description))]
    last_error: str | None = None

    for attempt in range(1, max_retries + 1):
        try:
            completion = provider.complete(
                CompletionRequest(
                    system=system,
                    messages=tuple(conversation),
                    max_tokens=BUILDER_MAX_OUTPUT_TOKENS,
                )
            )
        except ProviderError as exc:
            return None, None, attempt, f"the model call failed: {exc}"

        yaml_text = _strip_code_fences(completion.text)
        try:
            spec = load_template_text(yaml_text, source="the generated template")
            return yaml_text, spec, attempt, None
        except DugalaxyError as exc:
            last_error = str(exc)
            conversation.append(Message(role="assistant", content=completion.text))
            conversation.append(Message(role="user", content=_fix_prompt(exc)))

    return None, None, max_retries, last_error


def slugify(text: str) -> str:
    """Turn a name or description into a short, file-safe kebab-case slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50].strip("-") or "dataset"


def _unique_path(base: Path) -> Path:
    """Return *base*, or ``stem-2.yaml``, ``stem-3.yaml``… never overwriting an existing file."""
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = base.with_name(f"{base.stem}-{counter}{base.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _strip_code_fences(text: str) -> str:
    """Remove a surrounding ``` / ```yaml code fence if the model wrapped its output."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]  # drop the opening ``` (or ```yaml) line
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _output_shape(spec: TemplateSpec) -> str:
    return "conversation" if isinstance(spec.output, ConversationOutput) else "document"


def _closest_example(description: str) -> str:
    """Pick the bundled example whose shape best fits *description* (fallback source)."""
    words = set(re.findall(r"[a-z]+", description.lower()))
    if words & _DOCUMENT_HINTS:
        return _DOCUMENT_EXAMPLE
    return _CONVERSATION_EXAMPLE


def _example_text(name: str) -> str:
    """Read a bundled example template's YAML text."""
    return (files("dugalaxy") / "templates" / f"{name}.yaml").read_text(encoding="utf-8")


def _system_prompt() -> str:
    """Build the system prompt: the grammar, the faker whitelist, and two real examples."""
    kinds = ", ".join(sorted(FAKER_KINDS))
    return f"""\
You are a generator of Dugalaxy synthetic-data templates. Output ONE valid template as \
YAML and nothing else — no prose, no explanation, no code fences.

A template has four top-level sections:
  meta:        name, description, version
  scenario:    variables generated deterministically by a seeded engine (the FACTS)
  output:      what the model writes around those facts (conversation OR document)
  generation:  n, seed, max_retries, output_dir, output_formats

Pick the output shape deliberately:
  - type: conversation  → a back-and-forth, with `turns:` (each turn has a role + content)
  - type: document      → ONE standalone artifact, with a single `content:` block

Content blocks are one of two kinds:
  - type: fixed      → the engine fills it (a string, or a structured map serialized for you)
  - type: generated  → the MODEL writes it; may have `validation:` with `min_length`,
                       `max_length`, `must_mention`, `must_not_contain` (structural only)

Scenario variable types:
  choice, weighted_choice, range (integer, inclusive), sequence, faker,
  computed (a string interpolating other vars), object (a structured map of other vars).
Reference other variables anywhere with {{{{ scenario.var_name }}}}.

Rules you must follow:
  - Use ONLY these faker kinds: {kinds}. Never invent a kind.
  - Build any structured payload (e.g. a JSON record for the model's ground truth) as an
    `object` variable and serialize it with the `| json` filter, e.g.
    {{{{ scenario.record | json(indent=2) }}}}. Never hand-write a JSON string.
  - Keep `must_mention` entries to short, reliably-reproducible strings (an id, a name) —
    never a whole sentence.
  - Ground the model: put the facts in a `fixed` block or the system prompt; let the
    `generated` block write only prose.

Here are two complete, valid templates to follow exactly in form.

EXAMPLE 1 — a conversation:
{_example_text(_CONVERSATION_EXAMPLE)}

EXAMPLE 2 — a document:
{_example_text(_DOCUMENT_EXAMPLE)}
"""


def builder_input_text(description: str) -> str:
    """The prompt text (system + task) sent on the first call — for a pre-run cost estimate."""
    return f"{_system_prompt()}\n{_task_prompt(description)}"


def _task_prompt(description: str) -> str:
    return (
        f"Create a Dugalaxy template for this dataset:\n\n{description}\n\n"
        "Output only the YAML template."
    )


def _fix_prompt(error: DugalaxyError) -> str:
    return (
        f"That template did not load. The validator said:\n\n{error}\n\n"
        "Return the full corrected template as YAML only — no prose, no code fences."
    )
