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
  `MissingReferenceError`, `CyclicDependencyError`.

<!--
RELEASE PROCESS (how "release notes" work on GitHub):
1. Move items from [Unreleased] into a new dated, versioned section below.
2. Commit, then tag:  git tag -a v0.1.0 -m "v0.1.0"  &&  git push --tags
3. On GitHub: Releases -> Draft a new release -> pick the tag -> paste these notes.
   The tag is the source of truth; the GitHub Release is the public-facing note.
-->
