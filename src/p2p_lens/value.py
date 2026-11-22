"""Transparent value model: observed rates times explicit, editable assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import pandas as pd
import yaml
from pydantic import BaseModel, Field

from p2p_lens.analysis import P2PAnalysis


class Assumptions(BaseModel):
    """Every number the value model uses that does not come from the data."""

    cost_per_change_eur: float = Field(gt=0)
    changes_per_reworked_case: float = Field(gt=0)
    late_fee_rate: float = Field(ge=0, le=1)
    duplicate_interception_rate: float = Field(ge=0, le=1)
    overbilling_recovery_rate: float = Field(ge=0, le=1)
    program_cost_eur: float = Field(gt=0)
    scenarios: dict[str, float]


def load_assumptions(path: str | Path | None = None) -> Assumptions:
    """Load assumptions from a YAML file, or the packaged defaults when path is None."""
    if path is None:
        text = (
            resources.files("p2p_lens")
            .joinpath("config/default_assumptions.yaml")
            .read_text("utf-8")
        )
    else:
        text = Path(path).read_text("utf-8")
    return Assumptions.model_validate(yaml.safe_load(text))


@dataclass
class ValueCase:
    """Annual benefit per lever and scenario, plus return on the program cost."""

    annual_cases: float
    levers: pd.DataFrame
    summary: pd.DataFrame


def compute_value(
    a: P2PAnalysis, assumptions: Assumptions, annual_cases: float | None = None
) -> ValueCase:
    """Scale observed per-case rates to ``annual_cases`` and apply the assumptions.

    ``annual_cases`` defaults to the observed volume annualised from the data span.
    """
    if annual_cases is None:
        annual_cases = a.n_cases * 365.0 / a.span_days
    if annual_cases <= 0:
        raise ValueError("annual_cases must be positive")
    scale = annual_cases / a.n_cases
    c = a.deviation_counts
    m = a.money
    # Annual euro size of each problem before any program (the addressable base).
    base = {
        "Rework handling": c["rework"]
        * assumptions.changes_per_reworked_case
        * assumptions.cost_per_change_eur,
        "Late-payment fees": m["late_invoice_value"] * assumptions.late_fee_rate,
        "Duplicate-invoice leakage": m["duplicate_invoice_value"]
        * assumptions.duplicate_interception_rate,
        "Overbilling recovery": m["overbilling_exposure"] * assumptions.overbilling_recovery_rate,
    }
    rows = []
    for lever, value in base.items():
        row: dict[str, float | str] = {"lever": lever, "annual_problem_eur": value * scale}
        for name, share in assumptions.scenarios.items():
            row[name] = value * scale * share
        rows.append(row)
    levers = pd.DataFrame(rows)
    summary_rows = []
    for name in assumptions.scenarios:
        benefit = float(levers[name].sum())
        summary_rows.append(
            {
                "scenario": name,
                "annual_benefit_eur": benefit,
                "roi_year1_pct": 100.0
                * (benefit - assumptions.program_cost_eur)
                / assumptions.program_cost_eur,
                "payback_months": 12.0 * assumptions.program_cost_eur / benefit
                if benefit
                else float("inf"),
            }
        )
    return ValueCase(annual_cases=annual_cases, levers=levers, summary=pd.DataFrame(summary_rows))
