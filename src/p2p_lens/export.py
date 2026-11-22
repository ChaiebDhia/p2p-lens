"""Export an event log and case table in the activity-table / case-table shape that
process-mining platforms ingest (one row per event, one row per case)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from p2p_lens.conformance import DEVIATIONS, detect_deviations
from p2p_lens.eventlog import build_event_log
from p2p_lens.schema import Dataset


def build_case_table(ds: Dataset) -> pd.DataFrame:
    """One row per purchase order: attributes plus a 0/1 flag per deviation."""
    flags = detect_deviations(ds)
    ekko = ds.ekko.assign(EBELN=ds.ekko["EBELN"].astype(str)).set_index("EBELN")
    value = ds.ekpo.assign(EBELN=ds.ekpo["EBELN"].astype(str)).groupby("EBELN")["NETWR"].sum()
    cases = pd.DataFrame(
        {
            "case_id": ekko.index,
            "vendor": ekko["LIFNR"].to_numpy(),
            "created_by": ekko["ERNAM"].to_numpy(),
            "po_date": ekko["BEDAT"].to_numpy(),
            "payment_terms_days": ekko["ZBD1T"].to_numpy(),
            "po_value_eur": value.reindex(ekko.index).round(2).to_numpy(),
        }
    )
    for name in DEVIATIONS:
        cases[name] = flags[name].astype(int).to_numpy()
    return cases


def export_tables(ds: Dataset, out_dir: str | Path) -> list[Path]:
    """Write ``activities.csv`` and ``cases.csv`` and return their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log = build_event_log(ds).rename(
        columns={
            "case_id": "Case ID",
            "activity": "Activity",
            "timestamp": "Timestamp",
            "resource": "Resource",
        }
    )
    activities = out / "activities.csv"
    cases = out / "cases.csv"
    log.to_csv(activities, index=False, date_format="%Y-%m-%d %H:%M:%S")
    build_case_table(ds).to_csv(cases, index=False, date_format="%Y-%m-%d %H:%M:%S")
    return [activities, cases]
