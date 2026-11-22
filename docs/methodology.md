# Methodology

## Deviation definitions

| Deviation | Definition |
|---|---|
| `no_pr` | The purchase order has no requisition row. |
| `rework` | At least one change event after creation. |
| `invoice_before_gr` | First invoice receipt is earlier than first goods receipt. |
| `price_mismatch` | The first invoice differs from the order value by more than 5% (configurable). |
| `duplicate_invoice` | Two or more invoice documents for the order with the same amount (rounded to cents). |
| `late_payment` | Payment clearing is later than first invoice date plus `ZBD1T` days. |

## Process-mining measures

- **Variant:** the ordered activity sequence of a case. Share and cumulative share are reported.
- **Case duration:** last event minus first event, in days.
- **Waiting time:** for each pair of consecutive events in a case, the elapsed days; summarised per
  directly-follows pair (count, mean, median, p90, total case-days).
- **Bottleneck ranking:** by total case-days, excluding the invoice-to-payment wait, which is
  determined by contractual payment terms rather than by process friction.

## Conformance

Five precedence rules (requisition before order, order before release, release before goods receipt,
goods receipt before invoice, invoice before payment) are checked on the first occurrence of each
activity. A case **conforms** when it breaks no rule and contains all mandatory activities
(order, release, goods receipt, invoice, payment). A missing requisition is reported separately as
`no_pr` and does not break conformance.

## Verification

The generator injects each deviation from an explicit per-case flag and records the exact count.
The analysis never sees the flags. Tests assert the counts match exactly for four seeds.

## Grounding check

Given an answer and the retrieved findings: (1) it must contain at least one `[Fnn]` citation,
(2) every cited id must be one of the retrieved findings, (3) every number in the answer (after
removing citations and list markers) must appear in a cited finding or in the question. Numbers are
compared as floats after removing thousands separators. The check is intentionally strict: a correct
answer that rounds a number differently falls back to the extractive answer rather than risk an
unsupported figure.
