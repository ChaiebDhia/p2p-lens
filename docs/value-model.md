# Value model

The value model multiplies **observed rates** by **assumptions you control**. It is a way to make a
business case explicit and challengeable, not a forecast.

## Levers

| Lever | Problem size (before any program) |
|---|---|
| Rework handling | reworked cases x changes per case x cost per change |
| Late-payment fees | value of late invoices x late-fee rate |
| Duplicate-invoice leakage | value of duplicate invoices x interception rate |
| Overbilling recovery | positive price differences on mismatched invoices x recovery rate |

Each problem size is scaled from the observed volume to `--annual-cases` (default: observed volume
annualised from the data span), then multiplied by each scenario's share (conservative, base,
optimistic) to give an annual benefit.

## Outputs

`annual_benefit_eur`, `roi_year1_pct = (benefit - program cost) / program cost` and
`payback_months = 12 x program cost / benefit` per scenario.

## Read this before quoting a number

- Every assumption in `default_assumptions.yaml` is a placeholder. Replace them with figures from
  the organisation concerned.
- On synthetic data the result only demonstrates the mechanics. For example, scaling the demo run to
  150,000 orders a year produces very large ratios because the placeholder program cost is small
  relative to the scaled spend. That says something about the placeholders, not about any company.
- Benefits are not additive proof: levers can overlap, and none accounts for implementation risk.
