# Limitations

- **Synthetic by default.** The generator makes the method testable (known ground truth) but cannot
  show how the tool behaves on real organisational data. Real extracts bring partial deliveries,
  multi-item receipts, credit memos, cancellations and reversals that are not modelled.
- **One case per purchase order.** Item-level and multi-invoice cases are collapsed.
- **Simplified tables.** `REL_DATE`, `PO_CHANGES` and `PAYMENTS` are stand-ins for data that, in SAP,
  must be derived from change documents and FI clearing.
- **Rule-based conformance.** Precedence rules and deviation detectors, not alignment against a
  discovered process model.
- **Strict grounding.** The verifier may reject a correct LLM answer that reformats a number.
- **Retrieval is lexical.** TF-IDF over a small, fixed set of findings; no embeddings.
- **Value model is assumption-driven.** See docs/value-model.md.
- **Tested locally on Python 3.12** with pandas 3.1 and 2.2. CI covers 3.11 to 3.13.

## Roadmap

1. Item-level cases and partial deliveries.
2. Conformance checking against a discovered model.
3. Benchmarks on public real-world event logs.
4. Optional embedding retrieval behind the same grounding check.
