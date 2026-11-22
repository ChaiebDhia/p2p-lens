# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-22

### Added
- SAP-style schema (EKKO, EKPO, EKBE, EBAN plus change and payment tables) with validation.
- Seeded synthetic generator that records exact ground-truth deviation counts.
- Event-log builder and flat-CSV loader.
- Process mining: variants, case durations, directly-follows waiting times.
- Conformance: five precedence rules and six deviation detectors.
- Eleven deterministic findings (F01 to F11).
- Assumption-driven value model with scenarios, ROI and payback.
- Grounded copilot with TF-IDF retrieval, optional Ollama and OpenAI-compatible backends,
  a grounding check and an extractive fallback.
- Markdown and HTML reports with optional charts.
- CLI: `generate`, `analyze`, `analyze-log` (XES, XES.gz, CSV), `ask`, `demo`, with `--verbose` logging.
- Safe XES parsing via defusedxml.
- Executive summary section in the report; `export` command (activity and case tables);
  `--p2p-map` activity mapping to run P2P conformance on real logs.
- 78 tests including Hypothesis property tests (about 98% coverage), ruff, mypy strict.
- Benchmark script and performance notes; MkDocs site with a Pages deploy workflow.
- GitHub Actions CI matrix, release workflow, CodeQL and Dependabot.
