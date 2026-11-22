# Contributing

Thanks for taking a look. Small, focused pull requests are easiest to review.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,plots]"
pip install pre-commit && pre-commit install   # optional
```

## Before you open a pull request

```bash
make check
```

This runs `ruff check`, `ruff format --check`, `mypy --strict` and `pytest` (90% coverage gate).

## Guidelines

- Add or update tests for every behaviour change. Detection logic must keep matching the injected
  ground truth in `tests/test_ground_truth.py`.
- Findings are deterministic text built from the analysis. Never generate numbers with an LLM.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`,
  `chore:`, `ci:`).
- Update `CHANGELOG.md` under an `Unreleased` heading.
- Be kind: see the [Code of Conduct](CODE_OF_CONDUCT.md).
