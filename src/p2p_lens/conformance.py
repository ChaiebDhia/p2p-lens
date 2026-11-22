"""Conformance checking: precedence rules and table-based deviation detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from p2p_lens.schema import (
    ACT_CHG,
    ACT_GR,
    ACT_IR,
    ACT_PAY,
    ACT_PO,
    ACT_PR,
    ACT_REL,
    MANDATORY,
    Dataset,
    SchemaError,
)

ROLE_TO_ACTIVITY: dict[str, str] = {
    "requisition": ACT_PR,
    "order": ACT_PO,
    "release": ACT_REL,
    "change": ACT_CHG,
    "goods_receipt": ACT_GR,
    "invoice": ACT_IR,
    "payment": ACT_PAY,
}

DEVIATIONS: tuple[str, ...] = (
    "no_pr",
    "rework",
    "invoice_before_gr",
    "price_mismatch",
    "duplicate_invoice",
    "late_payment",
)

# (earlier activity, later activity): the earlier one must not happen after the later one.
PRECEDENCE_RULES: tuple[tuple[str, str], ...] = (
    (ACT_PR, ACT_PO),
    (ACT_PO, ACT_REL),
    (ACT_REL, ACT_GR),
    (ACT_GR, ACT_IR),
    (ACT_IR, ACT_PAY),
)


@dataclass
class ConformanceResult:
    """Outcome of precedence and completeness checks on an event log."""

    n_cases: int
    violations: dict[str, int]
    missing_mandatory: int
    conforming_cases: int

    @property
    def conformance_rate(self) -> float:
        return self.conforming_cases / self.n_cases if self.n_cases else 0.0


def check_precedence(
    log: pd.DataFrame, mandatory: tuple[str, ...] = MANDATORY
) -> ConformanceResult:
    """Check each precedence rule on the first occurrence of each activity per case.

    ``mandatory`` lists the activities every conforming case must contain.
    """
    first = log.groupby(["case_id", "activity"])["timestamp"].min().unstack()
    for activity in mandatory:
        if activity not in first.columns:
            first[activity] = pd.NaT
    violated_any = pd.Series(False, index=first.index)
    violations: dict[str, int] = {}
    for before, after in PRECEDENCE_RULES:
        if before not in first.columns or after not in first.columns:
            violations[f"{before} -> {after}"] = 0
            continue
        bad = first[before].notna() & first[after].notna() & (first[before] > first[after])
        violations[f"{before} -> {after}"] = int(bad.sum())
        violated_any |= bad
    incomplete = first[list(mandatory)].isna().any(axis=1)
    conforming = ~(violated_any | incomplete)
    return ConformanceResult(
        n_cases=len(first),
        violations=violations,
        missing_mandatory=int(incomplete.sum()),
        conforming_cases=int(conforming.sum()),
    )


def detect_deviations(ds: Dataset, price_tolerance: float = 0.05) -> pd.DataFrame:
    """Flag each purchase order for every deviation type (boolean columns, index EBELN)."""
    cases = pd.Index(ds.ekko["EBELN"].astype(str), name="EBELN")
    out = pd.DataFrame(index=cases)

    out["no_pr"] = ~cases.isin(ds.eban["EBELN"].astype(str))
    out["rework"] = cases.isin(ds.po_changes["EBELN"].astype(str))

    ir = ds.ekbe[ds.ekbe["VGABE"] == "2"].copy()
    gr = ds.ekbe[ds.ekbe["VGABE"] == "1"]
    ir["EBELN"] = ir["EBELN"].astype(str)
    first_ir_time = ir.groupby("EBELN")["BUDAT"].min().reindex(cases)
    first_gr_time = gr.assign(EBELN=gr["EBELN"].astype(str)).groupby("EBELN")["BUDAT"].min()
    first_gr_time = first_gr_time.reindex(cases)
    out["invoice_before_gr"] = (first_ir_time < first_gr_time).fillna(False).to_numpy()

    po_value = ds.ekpo.assign(EBELN=ds.ekpo["EBELN"].astype(str)).groupby("EBELN")["NETWR"].sum()
    first_ir_amount = (
        ir.sort_values(["EBELN", "BUDAT"]).groupby("EBELN")["DMBTR"].first().reindex(cases)
    )
    ratio = first_ir_amount / po_value.reindex(cases)
    out["price_mismatch"] = ((ratio - 1.0).abs() > price_tolerance).fillna(False).to_numpy()

    dup = ir.assign(DMBTR=ir["DMBTR"].round(2)).duplicated(subset=["EBELN", "DMBTR"])
    out["duplicate_invoice"] = cases.isin(ir.loc[dup, "EBELN"])

    terms = ds.ekko.set_index(ds.ekko["EBELN"].astype(str))["ZBD1T"].reindex(cases)
    due = first_ir_time + pd.to_timedelta(terms.to_numpy(), unit="D")
    paid = (
        ds.payments.assign(EBELN=ds.payments["EBELN"].astype(str)).groupby("EBELN")["AUGDT"].max()
    )
    out["late_payment"] = (paid.reindex(cases) > due).fillna(False).to_numpy()
    return out[list(DEVIATIONS)].astype(bool)


@dataclass
class ActivityMap:
    """Maps the activity names of a real log onto the canonical P2P activities."""

    names: dict[str, str]
    mandatory: tuple[str, ...]


def load_activity_map(path: str | Path) -> ActivityMap:
    """Load a YAML mapping of P2P roles to the activity names used in a real log.

    Roles: requisition, order, release, change, goods_receipt, invoice, payment. An optional
    ``mandatory`` list names the roles every case must contain (default: every mapped role
    except requisition and change).
    """
    raw = yaml.safe_load(Path(path).read_text("utf-8"))
    if not isinstance(raw, dict):
        raise SchemaError("activity map must be a YAML mapping of role to activity names")
    names: dict[str, str] = {}
    roles = {k: v for k, v in raw.items() if k != "mandatory"}
    for role, activities in roles.items():
        if role not in ROLE_TO_ACTIVITY:
            raise SchemaError(f"unknown role '{role}'; expected one of {sorted(ROLE_TO_ACTIVITY)}")
        if not isinstance(activities, list) or not all(isinstance(a, str) for a in activities):
            raise SchemaError(f"role '{role}' must map to a list of activity names")
        for activity in activities:
            names[activity] = ROLE_TO_ACTIVITY[role]
    if not names:
        raise SchemaError("activity map contains no activities")
    optional = {"requisition", "change"}
    default = [r for r in roles if r not in optional]
    chosen = raw.get("mandatory", default)
    unknown = [r for r in chosen if r not in roles]
    if unknown:
        raise SchemaError(f"mandatory roles not present in the map: {unknown}")
    return ActivityMap(names, tuple(ROLE_TO_ACTIVITY[r] for r in chosen))


def remap_log(log: pd.DataFrame, activity_map: ActivityMap) -> pd.DataFrame:
    """Keep only mapped events and rename them to the canonical activities."""
    mapped = log[log["activity"].isin(activity_map.names)].copy()
    if mapped.empty:
        raise SchemaError("none of the mapped activity names occur in the log")
    mapped["activity"] = mapped["activity"].map(activity_map.names)
    return mapped.sort_values(["case_id", "timestamp"], kind="stable").reset_index(drop=True)
