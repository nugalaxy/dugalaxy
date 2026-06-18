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
  `must_not_contain` references resolved to the actual facts.

<!--
RELEASE PROCESS (how "release notes" work on GitHub):
1. Move items from [Unreleased] into a new dated, versioned section below.
2. Commit, then tag:  git tag -a v0.1.0 -m "v0.1.0"  &&  git push --tags
3. On GitHub: Releases -> Draft a new release -> pick the tag -> paste these notes.
   The tag is the source of truth; the GitHub Release is the public-facing note.
-->
