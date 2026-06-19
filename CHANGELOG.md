# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffold: package structure, tooling, license, docs, CI.
- Template spec data model (`template/spec.py`): Pydantic models for `meta`,
  `scenario`, `output`, and `generation`, including discriminated unions for the
  scenario variable types (`choice`, `weighted_choice`, `range`, `sequence`,
  `faker`, `computed`, `object`), content blocks (`fixed`, `generated`), and
  output shapes (`conversation`, `document`).
- Template loader (`template/loader.py`): parses a YAML template into a validated
  spec, failing fast before any run with legible errors for missing variable
  references and dependency cycles among composite variables.
- Pre-run error types (`template/errors.py`): `TemplateLoadError`,
  `MissingReferenceError`, `CyclicDependencyError`, `UnknownFakerKindError`.
- Deterministic scenario engine (`scenario/`): seeded per-sample/per-variable
  generation of all primitive types (`choice`, `weighted_choice`, `range`,
  `sequence`, `faker`) and composites (`computed`, `object`), with topological
  dependency resolution and cycle/missing-reference detection. Seeds are derived
  with SHA-256 so facts reproduce across runs, processes, and over calendar time;
  faker is seeded per-variable, and `datetime_recent` is anchored to a fixed,
  overridable reference time (no wall-clock drift). Faker whitelist:
  `datetime_recent`, `ipv4`, `name`, `email`, `uuid4`, `domain_name`,
  `mac_address`, plus security kinds `sha256`, `file_path`, `hostname`.
- Interpolation engine (`generator/interpolation.py`): the shared Jinja2
  `{{ scenario.x }}` renderer and the `| json` filter, which serializes structured
  payloads with `json.dumps` so values containing quotes, backslashes, or newlines
  can never produce invalid JSON. Scenario composites now reuse this engine.
- Grounding (`generator/grounding.py`): renders a sample's facts into the system
  prompt and content blocks — fixed blocks filled by the engine, generated blocks
  carrying the model prompt plus structural checks with `must_mention` /
  `must_not_contain` references resolved to the actual facts. `requires_model`
  detects deterministic-only templates (no `generated` block).
- Provider layer (`providers/`): one `TextProvider` interface with adapters for
  `openai_compatible` (covers OpenAI/DeepSeek/Gemini/Groq/Together via `base_url`),
  `anthropic`, and `ollama` (local, no key). `build_provider` constructs from
  config; API keys are resolved from named environment variables only, never disk.
- Runtime config (`config/`): `Config` model and `load_config` with precedence
  CLI flags > config file > defaults; unknown fields and bad values fail legibly.
- Cost (`cost/`): pre-run token/cost estimate with a best-effort price table
  (config-overridable; unknown models flagged, Ollama free), a hard cap via
  `enforce_cap`, and a disk-backed response cache keyed by prompt + params
  (including a per-backend fingerprint, so the same model at different endpoints
  never collides) so an identical prompt is a cache hit (reproducible prose, no
  repeat charges). Cache writes are atomic and corrupted entries degrade to a miss.
- Generator loop (`generator/core.py`): the full per-sample pipeline — scenario →
  ground → model (cache, then retry up to `max_retries`, else drop) → structural
  validation → write to disk immediately. The generated block's instruction is
  merged into the trailing user message so wire roles stay provider-legal
  (`agent`/`assistant` are emit-time labels, never sent). Disk-backed: only
  lightweight diversity counters are held in memory.
- Structural validation (`generator/validation.py`): non-empty, min/max length,
  `must_mention`, `must_not_contain` — structural only, never semantic.
- Emitters (`emit/`): JSONL (one object per line), the Echo YAML envelope
  (streamed incrementally, serialized so content stays valid YAML), and a per-run
  sample index. Each sample is flushed as produced; nothing accumulates.
- Run reporting (`reporting/summary.py`): requested/produced/dropped/retries plus a
  provable diversity metric and a pre-run duplicate warning when the enumerable
  scenario space is smaller than n. The headline diversity ratio counts distinct
  combinations of the **categorical axes** (`choice`/`weighted_choice`) — the same
  axes the duplicate warning uses — so high-cardinality variables (timestamps,
  UUIDs, wide ranges) cannot inflate it; those still appear in the per-variable
  spread.
- CLI (`cli/main.py`): `dugalaxy version`, `dugalaxy init` (scaffolds a commented,
  runnable starter template), and `dugalaxy gen` — the magic moment. `gen` resolves
  a template by name or path, applies CLI > config > template precedence, prints a
  pre-run plan + cost estimate (confirming paid runs, enforcing the cap), runs the
  pipeline, and prints the run summary. Flags include `--n`, `--seed`, `--model`,
  `--provider`, `--format`, `--cost-cap`, `--include-meta`, `--no-cache`, `--yes`.

### Fixed
- YAML envelope (`emit/yaml.py`): multi-line content (JSON-bearing turns,
  multi-paragraph prose) now renders as block literals (`|`) instead of
  double-quoted scalars with `\n` escapes, so embedded JSON reads cleanly in the
  emitted file. Implemented with a local `SafeDumper` subclass — no global
  representer — preserving the streamed, disk-backed contract; the round-trip is
  verified on the real indented file, where the block-scalar indentation risk lives.

<!--
RELEASE PROCESS (how "release notes" work on GitHub):
1. Move items from [Unreleased] into a new dated, versioned section below.
2. Commit, then tag:  git tag -a v0.1.0 -m "v0.1.0"  &&  git push --tags
3. On GitHub: Releases -> Draft a new release -> pick the tag -> paste these notes.
   The tag is the source of truth; the GitHub Release is the public-facing note.
-->
