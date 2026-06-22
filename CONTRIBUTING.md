# Contributing to Dugalaxy

Thanks for your interest! Dugalaxy is early and solo-maintained, so the scope is deliberately
focused. Small, well-scoped contributions are the easiest to accept.

## Development setup

```bash
git clone https://github.com/nugalaxy/dugalaxy.git
cd dugalaxy
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,api]"
pre-commit install
```

## Before you open a PR

```bash
ruff check .          # lint
ruff format .         # format
mypy                  # type-check
pytest                # tests
```

All four must pass. `pre-commit` runs the fast ones automatically on commit.

## Guidelines

- Keep PRs small and single-purpose.
- Add or update tests for any behavior change.
- Match the existing structure (see `docs/` and module docstrings in `src/dugalaxy/`).
- For larger ideas, please open an issue to discuss before building.

## Reporting security issues

Do **not** open a public issue for security problems. See [SECURITY.md](SECURITY.md).
