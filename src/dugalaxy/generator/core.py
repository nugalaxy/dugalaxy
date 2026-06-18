"""Per-sample pipeline orchestration. Disk-backed: context never accumulates prior samples.

For each sample index: generate deterministic facts -> ground them into prompts and
payloads -> for each generated block, call the model (cache first, then retry up to
max_retries, else drop) and validate structurally -> write the sample to disk
immediately. Only lightweight diversity counters are kept in memory; the produced
dataset and the model's context never accumulate prior samples.
"""

import random
from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from dugalaxy.cost.cache import ResponseCache
from dugalaxy.emit import IndexEmitter, JsonlEmitter, Sample, SampleEmitter, YamlEmitter
from dugalaxy.providers.base import CompletionRequest, Message, TextProvider
from dugalaxy.reporting.summary import DiversityTracker, RunSummary, duplicate_warning
from dugalaxy.scenario import generate_scenario
from dugalaxy.template.errors import DugalaxyError
from dugalaxy.template.spec import ConversationOutput, Meta, TemplateSpec

from .grounding import (
    GeneratedRequest,
    GroundedBlock,
    GroundedOutput,
    ground_output,
    requires_model,
)
from .interpolation import to_json
from .validation import validate_generated

_KNOWN_FORMATS = {"jsonl", "yaml"}


class GeneratorError(DugalaxyError):
    """The run could not proceed (e.g. a model is required but no provider was given)."""


@dataclass(frozen=True)
class RunResult:
    """The outcome of a generation run."""

    summary: RunSummary
    output_files: tuple[Path, ...]
    pre_run_warning: str | None


def _api_role(role: str) -> str:
    """Map a free-form template role to a provider-legal wire role.

    ``user`` stays ``user``; everything else (``assistant``, ``agent``, ...) is the
    model side and maps to ``assistant``. The emit-time label is unaffected — only
    what we send to the API. Roles stay alternating, which Anthropic requires.
    """
    return "user" if role.lower() == "user" else "assistant"


def _build_request(
    system_prompt: str | None,
    context: list[Message],
    instruction: str,
    max_tokens: int | None,
) -> CompletionRequest:
    """Build the wire request, delivering *instruction* as the trailing user message.

    Merging the instruction into a preceding user turn (or sending it alone) keeps the
    message roles alternating and the system prompt as pure ground-truth context.
    """
    messages = list(context)
    if messages and messages[-1].role == "user":
        merged = f"{messages[-1].content}\n\n{instruction}"
        messages[-1] = Message(role="user", content=merged)
    else:
        messages.append(Message(role="user", content=instruction))
    return CompletionRequest(system=system_prompt, messages=tuple(messages), max_tokens=max_tokens)


def _generate(
    provider: TextProvider,
    cache: ResponseCache | None,
    request: CompletionRequest,
    spec: GeneratedRequest,
    max_retries: int,
) -> tuple[str | None, int]:
    """Return ``(text, retries_used)``; ``text`` is ``None`` if every attempt failed.

    A cached, still-valid completion short-circuits with zero retries. On a miss the
    provider is called up to ``max_retries + 1`` times; the first valid completion is
    cached and returned. Only validated completions are ever cached.
    """
    if cache is not None:
        cached = cache.get(cache.make_key(request, provider.fingerprint))
        if cached is not None and validate_generated(cached.text, spec).ok:
            return cached.text, 0

    for attempt in range(max_retries + 1):
        completion = provider.complete(request)
        if validate_generated(completion.text, spec).ok:
            if cache is not None:
                cache.put(cache.make_key(request, provider.fingerprint), completion)
            return completion.text, attempt
    return None, max_retries


def _build_sample(
    grounded: GroundedOutput,
    facts: dict[str, object],
    *,
    index: int,
    meta: Meta,
    seed: int,
    provider: TextProvider | None,
    cache: ResponseCache | None,
    max_retries: int,
) -> tuple[Sample | None, int]:
    """Produce one sample (or ``None`` if any generated block was dropped) + retries used."""
    session_id = f"{meta.name}_{index:02d}"
    retries = 0

    def fixed_text(block: GroundedBlock) -> str:
        return block.value if isinstance(block.value, str) else to_json(block.value, indent=2)

    if grounded.kind == "conversation":
        turns: list[tuple[str, str]] = []
        context: list[Message] = []
        for block in grounded.blocks:
            if block.request is None:
                content = fixed_text(block)
                role = block.role or "user"
                turns.append((role, content))
                context.append(Message(role=_api_role(role), content=content))
            else:
                assert provider is not None  # guaranteed by requires_model check
                request = _build_request(
                    grounded.system_prompt,
                    context,
                    block.request.instruction,
                    block.request.max_tokens,
                )
                text, used = _generate(provider, cache, request, block.request, max_retries)
                retries += used
                if text is None:
                    return None, retries
                role = block.role or "assistant"
                turns.append((role, text))
                context.append(Message(role="assistant", content=text))
        sample = Sample(
            index=index,
            session_id=session_id,
            kind="conversation",
            turns=tuple(turns),
            document=None,
            facts=facts,
            seed=seed,
        )
        return sample, retries

    # document
    block = grounded.blocks[0]
    if block.request is None:
        document: str | dict[str, object] | None = block.value
    else:
        assert provider is not None  # guaranteed by requires_model check
        request = _build_request(
            grounded.system_prompt, [], block.request.instruction, block.request.max_tokens
        )
        text, used = _generate(provider, cache, request, block.request, max_retries)
        retries += used
        if text is None:
            return None, retries
        document = text
    sample = Sample(
        index=index,
        session_id=session_id,
        kind="document",
        turns=(),
        document=document,
        facts=facts,
        seed=seed,
    )
    return sample, retries


def _open_emitters(
    stack: ExitStack,
    *,
    meta: Meta,
    kind: str,
    output_dir: Path,
    formats: Sequence[str],
) -> tuple[list[SampleEmitter], tuple[Path, ...]]:
    unknown = set(formats) - _KNOWN_FORMATS
    if unknown:
        raise GeneratorError(f"Unknown output format(s): {', '.join(sorted(unknown))}")

    emitters: list[SampleEmitter] = []
    files: list[Path] = []
    if "jsonl" in formats:
        path = output_dir / f"{meta.name}.jsonl"
        emitters.append(stack.enter_context(JsonlEmitter(path)))
        files.append(path)
    if "yaml" in formats:
        path = output_dir / f"{meta.name}.yaml"
        emitters.append(
            stack.enter_context(
                YamlEmitter(
                    path,
                    dataset_name=meta.dataset_name or meta.name,
                    description=meta.description,
                    kind=kind,
                )
            )
        )
        files.append(path)
    index_path = output_dir / "index.jsonl"
    emitters.append(stack.enter_context(IndexEmitter(index_path)))
    files.append(index_path)
    return emitters, tuple(files)


def generate_dataset(
    template: TemplateSpec,
    *,
    provider: TextProvider | None = None,
    cache: ResponseCache | None = None,
    n: int | None = None,
    seed: int | None = None,
    max_retries: int | None = None,
    output_dir: Path | None = None,
    output_formats: Sequence[str] | None = None,
) -> RunResult:
    """Run the full generation pipeline, writing samples to disk as they are produced.

    Values default from ``template.generation`` but can be overridden per call. A
    template with no generated content is deterministic-only and needs no provider.
    """
    gen = template.generation
    n = gen.n if n is None else n
    if seed is not None:
        effective_seed = seed
    elif gen.seed is not None:
        effective_seed = gen.seed
    else:
        effective_seed = random.randrange(2**31)
    max_retries = gen.max_retries if max_retries is None else max_retries
    out_dir = Path(gen.output_dir) if output_dir is None else output_dir
    formats = list(gen.output_formats) if output_formats is None else list(output_formats)

    if requires_model(template.output) and provider is None:
        raise GeneratorError(
            "Template has generated content but no provider was supplied. "
            "Configure a provider, or use a deterministic-only template."
        )

    kind = "conversation" if isinstance(template.output, ConversationOutput) else "document"
    tracker = DiversityTracker()
    dropped = 0
    total_retries = 0

    with ExitStack() as stack:
        emitters, files = _open_emitters(
            stack, meta=template.meta, kind=kind, output_dir=out_dir, formats=formats
        )
        for index in range(n):
            facts = generate_scenario(template.scenario, seed=effective_seed, index=index)
            grounded = ground_output(template.output, facts)
            sample, retries = _build_sample(
                grounded,
                facts,
                index=index,
                meta=template.meta,
                seed=effective_seed,
                provider=provider,
                cache=cache,
                max_retries=max_retries,
            )
            total_retries += retries
            if sample is None:
                dropped += 1
                continue
            for emitter in emitters:
                emitter.emit(sample)
            tracker.record(facts)

    summary = tracker.summary(requested=n, dropped=dropped, total_retries=total_retries)
    return RunResult(
        summary=summary,
        output_files=files,
        pre_run_warning=duplicate_warning(template.scenario, n),
    )
