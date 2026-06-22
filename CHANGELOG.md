# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Rewrote the README and `docs/getting-started.md` around the guided flow: the README now
  leads with the one-sentence AI-builder hook and four literal numbered steps
  (install → `dugalaxy` → `gen quickstart` → `new "<description>"`), with the
  differentiators moved below the fold; getting-started is a linear walkthrough that mirrors
  the tool step-for-step. The template spec is cross-linked as "go deeper," never a
  prerequisite.
- Hosted-model setup docs are now self-contained and cross-platform: the README and
  getting-started show the `dugalaxy.config.yaml` to drop in the working directory inline
  (no longer pointing pip users at a repo-only example file they don't have) and give the
  exact command to set the API-key environment variable in both PowerShell (`$env:`) and
  bash/zsh (`export`), noting it lives only in the current terminal window.

### Added
- AI template builder (`authoring/template_builder.py`) + `dugalaxy new "<description>"`:
  drafts a template from one sentence. A model writes YAML; we validate it with the real
  loader and, on failure, hand the legible error back to the model to fix (up to 3 tries).
  Two safety guarantees: a draft is written only after it loads cleanly, and if no valid
  template is produced (or no model is available) it copies the closest bundled example —
  the user is never blocked or handed a broken file. The result is always presented as a
  starting point, never as verified. The bare-`dugalaxy` "no template" branch now runs the
  builder interactively (with model-bootstrap guidance); `new` is its non-interactive twin.
  The prompt's grammar and faker-kind whitelist are derived from live code so they can't
  drift from what the loader accepts. New `load_template_text()` validates YAML from memory.
- Interactive guided first-run on bare `dugalaxy`: on a real terminal it leads a new
  user from a zero-setup win (runs the deterministic `quickstart` and shows one real
  sample) to the next step (`gen` if they have a template, else `init` — the seam
  where the AI builder lands next). Non-interactive (piped/CI/redirected) prints the
  static welcome and exits 0, never blocking on a prompt. The win never crashes the
  front door: a write failure is reported in plain words, not a traceback.
- `dugalaxy doctor` (`authoring/diagnostics.py`): a plain-words environment health
  check — config presence/validity, provider reachability (pings local Ollama),
  hosted API-key presence (the named env var only, never its value), template count,
  and output-directory writability — each rendered as a ✓/✗ line with a one-line fix,
  ending in the single most useful next action. Reusable core for the guided
  first-run flow. The command always exits 0 (a missing model is an expected state,
  not an error — the zero-setup demo still works).
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

### Added
- Faker whitelist gained everyday people/place kinds: `city`, `country`, `company`,
  `phone_number` (seeded and deterministic like the rest; golden-tested).
- **Docs are discoverable after `pip install`.** A freshly installed user has no local
  repo, so the learning links are now surfaced as URLs where they'll look: the welcome
  screen has a **Learn** section (getting started, template format, project), `dugalaxy init`
  points at the format guide, the PyPI sidebar gets a **Documentation** link
  (`[project.urls]`), and the README's doc links are now absolute so they work on PyPI.
- **A real template-spec reference** (`docs/template-spec.md`). It was a stub — a list of
  the vocabulary words but not the *structure*, so neither a human nor an LLM could tell
  that a `conversation` uses `turns:` while a `document` uses a single `content:`. It now
  leads with the two output shapes (when to use each, the common mistake, full annotated
  examples of both), then content blocks, scenario variables, and generation controls.
- **Documented the supported faker kinds** in `docs/template-spec.md` (a table of every
  `kind:` with what it produces). Previously the valid set appeared only in the error
  message and the code, so `faker` comments pointing "see docs for the kinds" led nowhere;
  they now point at the real list.
- The pre-run plan now prints the **resolved template path** (`template: <file>`), so the exact
  file that ran is always visible — closing the silent-precedence surprise when a local template
  shadows a bundled one of the same name.
- **Zero-setup first run:** a bundled, fully deterministic `quickstart` template
  (`dugalaxy gen quickstart`) produces synthetic profiles with no model, no API key, and
  no config — it runs instantly straight after `pip install`. Onboarding (welcome banner,
  README, getting-started, `init`) now leads with it before the model-based example.
- `dugalaxy list` lists the templates Dugalaxy can find — bundled examples plus any in
  your working directory (`template/discovery.py`).
- `dugalaxy gen` with no template argument now prompts you to pick one interactively;
  run non-interactively, it errors with guidance instead of hanging.
- A branded welcome panel (with a galaxy mark, degrading to ASCII where the terminal
  can't render the emoji) on bare `dugalaxy`, plus a project logo (`assets/logo.svg`)
  embedded in the README.

### Changed
- Flagship example is now **`customer-support`** (a relatable, non-domain-specific
  conversation template), shipped **inside the package** at
  `dugalaxy/templates/customer-support.yaml`. It is bundled in the wheel, so
  `pip install dugalaxy && dugalaxy gen customer-support` works with no repo clone.
- Template resolution (`cli/main.py`) now falls back to the bundled example templates
  after checking the working directory, so installed users can run the examples by name.
  Your own `./templates/<name>.yaml` still takes precedence.
- Onboarding: the pre-run plan now prints the **output location and formats** before a
  run; `dugalaxy init` explains the Ollama prerequisite, the provider override, and where
  output lands; `docs/getting-started.md` documents the full template → gen → output loop
  with a troubleshooting section.
- Packaging metadata: added the author email and Python 3.10/3.11/3.12 classifiers.
- The public surface is now domain-neutral: removed residual security/SOC-flavored language
  from `SECURITY.md`, code comments, and test fixtures (the templates were already neutral).

### Fixed
- **Dropped samples now report *why*.** A sample dropped after its generated turn failed
  validation every retry previously vanished into a bare "dropped 1" with an empty output
  file — a user couldn't tell an empty model reply from a too-short one or a missing
  required mention. The run summary now lists the reasons with counts (e.g. "dropped
  because: output is empty"); the validation reason was already computed, just discarded.
- **Legible schema errors.** An invalid template previously surfaced the raw Pydantic
  error (location noise, a `errors.pydantic.dev` URL, truncated `input_type=` repr) — hard
  to parse even for the authors. Errors are now formatted as clean `path: problem` lines,
  and common output-shape mistakes get a targeted hint (e.g. using `turns:` under a
  `document` output, or an unknown `output.type`, now explains the right shape).
- **Bundled templates now actually ship in the wheel.** An unanchored `templates/` entry
  in `.gitignore` also matched `src/dugalaxy/templates/`, so the built wheel contained no
  example templates and `dugalaxy list` / `gen quickstart` failed on a clean install.
  Anchored the ignore to the root workspace only; the wheel now carries `customer-support`
  and `quickstart`. `discover_templates` also guards a missing bundled directory instead of
  raising a `FileNotFoundError` traceback.
- **A provider failure mid-run now stops gracefully instead of discarding the run.** When a
  model call fails part-way through (e.g. an exhausted rate-limit quota) after at least one
  sample has been produced, the run stops cleanly, keeps the samples already written to
  disk, and reports "Stopped early" with the reason and the normal summary (exiting non-zero).
  A failure before any sample exists still surfaces the actionable connection/auth error.
- **Progress feedback during a run.** A long model-backed run no longer looks like a
  frozen terminal: `generate_dataset` reports per-sample progress through an `on_progress`
  hook, and the CLI renders it as a `rich` progress bar. The bar is transient and shown
  only on an interactive terminal, so piped and CI output stay clean.
- **Safe-by-default sample count.** `dugalaxy gen` with no `--n` against a model-backed
  template now produces a single sample (and says so, pointing at `--n N` for the full
  set) instead of firing the template's production count — a forgotten flag should never
  trigger a large paid or quota-consuming run. Free deterministic-only runs are unchanged
  and still honor the template's `n`.
- Refreshed the cost estimator's price table with current models — `gemini-2.5-flash`
  (and `-pro`/`-flash-lite`), `gpt-4.1`, and the Claude 4.x family (`claude-opus-4-8`,
  `claude-sonnet-4-6`, `claude-haiku-4-5`) — so common models are priced and the cost cap
  can protect them instead of falling through to the unknown-price path. Anthropic prices
  are authoritative; other providers' values are best-effort and config-overridable.
- The `dugalaxy init` starter template now matches the realistic conversation shape: the
  customer speaks in natural prose and the structured ticket record grounds the agent in the
  system prompt (previously the customer "pasted" a JSON blob, inherited from an earlier design).
- When a model is required but Ollama isn't reachable, the connection failure now reports an
  actionable message (start Ollama, pick another provider, or run `dugalaxy gen quickstart`)
  instead of a raw transport error.
- Unknown-price runs (`cli/main.py`): the confirmation prompt now states **"cost unknown
  for this model — you may be billed"** instead of a generic prompt, so the trust-fatal
  unknown-cost case is explicit. The run still blocks on confirmation as before.
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
