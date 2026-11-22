"""End-to-end analysis of a SAP-style procure-to-pay dataset."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from p2p_lens.conformance import (
    DEVIATIONS,
    ConformanceResult,
    check_precedence,
    detect_deviations,
)
from p2p_lens.eventlog import build_event_log
from p2p_lens.mining import SECONDS_PER_DAY, LogAnalysis, analyze_log
from p2p_lens.schema import Dataset


@dataclass
class P2PAnalysis:
    """Everything the findings, value model and report are built from."""

    n_cases: int
    span_days: int
    log: LogAnalysis
    conformance: ConformanceResult
    deviations: pd.DataFrame
    deviation_counts: dict[str, int]
    approval: dict[str, float]
    vendors: pd.DataFrame
    money: dict[str, float]


def _days(delta: pd.Series) -> pd.Series:
    seconds: pd.Series = delta.dt.total_seconds()
    return seconds / SECONDS_PER_DAY


def analyze(
    ds: Dataset, high_value_threshold: float = 10_000.0, price_tolerance: float = 0.05
) -> P2PAnalysis:
    """Analyse a validated dataset: mining, conformance, deviations, vendors and money."""
    ds.validate()
    log = build_event_log(ds)
    log_analysis = analyze_log(log)
    conformance = check_precedence(log)
    flags = detect_deviations(ds, price_tolerance=price_tolerance)
    counts = {name: int(flags[name].sum()) for name in DEVIATIONS}

    ekko = ds.ekko.assign(EBELN=ds.ekko["EBELN"].astype(str)).set_index("EBELN")
    ekpo = ds.ekpo.assign(EBELN=ds.ekpo["EBELN"].astype(str))
    ekbe = ds.ekbe.assign(EBELN=ds.ekbe["EBELN"].astype(str))
    pay = ds.payments.assign(EBELN=ds.payments["EBELN"].astype(str))
    idx = ekko.index

    po_value = ekpo.groupby("EBELN")["NETWR"].sum().reindex(idx)
    ir = ekbe[ekbe["VGABE"] == "2"].sort_values(["EBELN", "BUDAT"])
    gr = ekbe[ekbe["VGABE"] == "1"]
    first_ir_time = ir.groupby("EBELN")["BUDAT"].min().reindex(idx)
    first_ir_amount = ir.groupby("EBELN")["DMBTR"].first().reindex(idx)
    first_gr_time = gr.groupby("EBELN")["BUDAT"].min().reindex(idx)
    paid = pay.groupby("EBELN")["AUGDT"].max().reindex(idx)
    due = first_ir_time + pd.to_timedelta(ekko["ZBD1T"].to_numpy(), unit="D")

    approval_days = _days(ekko["REL_DATE"] - ekko["BEDAT"])
    high = po_value > high_value_threshold
    approval = {
        "threshold": float(high_value_threshold),
        "n_high_value": float(high.sum()),
        "median_high_days": float(approval_days[high].median()) if high.any() else 0.0,
        "median_low_days": float(approval_days[~high].median()) if (~high).any() else 0.0,
    }

    lead = _days(first_gr_time - ekko["REL_DATE"])
    any_dev = flags.any(axis=1)
    vendors = (
        pd.DataFrame(
            {
                "vendor": ekko["LIFNR"].to_numpy(),
                "gr_lead_days": lead.to_numpy(),
                "late": flags["late_payment"].to_numpy(),
                "any_deviation": any_dev.to_numpy(),
            }
        )
        .groupby("vendor")
        .agg(
            cases=("late", "size"),
            mean_gr_lead_days=("gr_lead_days", "mean"),
            late_share=("late", "mean"),
            deviation_rate=("any_deviation", "mean"),
        )
        .reset_index()
        .sort_values("mean_gr_lead_days", ascending=False)
        .reset_index(drop=True)
    )

    mismatch = flags["price_mismatch"]
    diff = (first_ir_amount - po_value).where(mismatch, 0.0)
    late = flags["late_payment"]
    dup_rows = ir.assign(DMBTR=ir["DMBTR"].round(2)).duplicated(subset=["EBELN", "DMBTR"])
    money = {
        "total_spend": float(po_value.sum()),
        "duplicate_invoice_value": float(ir.loc[dup_rows, "DMBTR"].sum()),
        "overbilling_exposure": float(diff.clip(lower=0.0).sum()),
        "late_invoice_value": float(first_ir_amount[late].sum()),
        "mean_days_late": float(_days(paid - due)[late].mean()) if late.any() else 0.0,
        "mean_po_value": float(po_value.mean()),
    }
    span = int((ekko["BEDAT"].max() - ekko["BEDAT"].min()).days) + 1
    return P2PAnalysis(
        n_cases=len(idx),
        span_days=span,
        log=log_analysis,
        conformance=conformance,
        deviations=flags,
        deviation_counts=counts,
        approval=approval,
        vendors=vendors,
        money=money,
    )
