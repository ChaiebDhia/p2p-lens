# Architecture

```text
synth.generate ──> Dataset (6 tables) ──> eventlog.build_event_log ──> mining.analyze_log
                        │                          │                          │
                        │                          └─> conformance.check_precedence
                        └─> conformance.detect_deviations
                                         │
                                  analysis.analyze  ──>  P2PAnalysis
                                         │
                       findings.build_findings ──> [Finding F01..F11]
                          │            │                 │
                   value.compute_value │          copilot.ask ──> Answer
                          │            │                 (retrieve, LLM?, verify, fallback)
                          └──────> report.* ──> report.md / report.html / charts
```

## Design decisions

- **One case per purchase order.** Simple, explainable, and enough for the deviations modelled.
  Item-level cases are on the roadmap.
- **Detection from tables, mining from the log.** Deviations that need amounts or terms (price
  mismatch, late payment) use the tables; ordering rules use the event log. Both agree where they
  overlap (`invoice_before_gr` equals the goods-receipt-to-invoice precedence violation, asserted in
  tests).
- **Findings are text built from numbers, not generated.** This is what makes grounding checkable.
- **LLM is optional and untrusted.** Its output passes a verifier or is discarded.
- **Standard library HTTP.** The LLM clients use `urllib`, so there is no SDK lock-in.
- **Typed and tested.** `mypy --strict`, ruff, and a 90% coverage gate in CI.

## Module map

| Module | Responsibility |
|---|---|
| `schema.py` | Table definitions, `Dataset`, validation, CSV I/O |
| `synth.py` | Seeded generator and `GroundTruth` |
| `eventlog.py` | Tables to event log; flat CSV loader |
| `mining.py` | Variants, durations, edge waiting times (log only) |
| `conformance.py` | Precedence rules, deviation detectors |
| `analysis.py` | Orchestration, vendors, money figures |
| `findings.py` | `Finding` model and builders |
| `value.py` | `Assumptions`, scenarios, ROI |
| `copilot.py` | Retrieval, prompt, grounding check, backends |
| `report.py` | Block model rendered to Markdown or HTML, charts |
| `cli.py` | `argparse` entry point |
