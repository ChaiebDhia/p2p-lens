"""Turn SAP-style tables (or a flat CSV) into a standard event log."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

import pandas as pd
from defusedxml.ElementTree import iterparse

from p2p_lens.schema import (
    ACT_CHG,
    ACT_GR,
    ACT_IR,
    ACT_PAY,
    ACT_PO,
    ACT_PR,
    ACT_REL,
    ACTIVITY_ORDER,
    LOG_COLUMNS,
    Dataset,
    SchemaError,
)

_RANK = {name: i for i, name in enumerate(ACTIVITY_ORDER)}


def _part(case: pd.Series, activity: str, ts: pd.Series, resource: pd.Series | str) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "case_id": case.astype(str).to_numpy(),
            "activity": activity,
            "timestamp": pd.to_datetime(ts).to_numpy(),
            "resource": resource if isinstance(resource, str) else resource.astype(str).to_numpy(),
        }
    )
    return frame


def build_event_log(ds: Dataset) -> pd.DataFrame:
    """Build the event log: one row per activity occurrence, one case per purchase order.

    Ties on identical timestamps are broken by the canonical activity order, so the
    result is deterministic.
    """
    ir = ds.ekbe[ds.ekbe["VGABE"] == "2"]
    gr = ds.ekbe[ds.ekbe["VGABE"] == "1"]
    parts = [
        _part(ds.eban["EBELN"], ACT_PR, ds.eban["BADAT"], ds.eban["ERNAM"]),
        _part(ds.ekko["EBELN"], ACT_PO, ds.ekko["BEDAT"], ds.ekko["ERNAM"]),
        _part(ds.ekko["EBELN"], ACT_REL, ds.ekko["REL_DATE"], "RELEASE_STRATEGY"),
        _part(ds.po_changes["EBELN"], ACT_CHG, ds.po_changes["UDATE"], ds.po_changes["USERNAME"]),
        _part(gr["EBELN"], ACT_GR, gr["BUDAT"], "SYSTEM"),
        _part(ir["EBELN"], ACT_IR, ir["BUDAT"], "SYSTEM"),
        _part(ds.payments["EBELN"], ACT_PAY, ds.payments["AUGDT"], "FI_CLEARING"),
    ]
    log = pd.concat(parts, ignore_index=True)
    log["_rank"] = log["activity"].map(_RANK)
    log = log.sort_values(["case_id", "timestamp", "_rank"], kind="stable")
    return log.drop(columns="_rank").reset_index(drop=True)[LOG_COLUMNS]


def load_flat_log(
    path: str | Path,
    case_col: str,
    activity_col: str,
    timestamp_col: str,
    resource_col: str | None = None,
    sep: str = ",",
) -> pd.DataFrame:
    """Load any flat event-log CSV and normalise it to the standard columns."""
    raw = pd.read_csv(path, sep=sep)
    needed = [case_col, activity_col, timestamp_col] + ([resource_col] if resource_col else [])
    missing = [c for c in needed if c not in raw.columns]
    if missing:
        raise SchemaError(f"columns not found in {path}: {missing}")
    log = pd.DataFrame(
        {
            "case_id": raw[case_col].astype(str),
            "activity": raw[activity_col].astype(str),
            "timestamp": pd.to_datetime(raw[timestamp_col], utc=True).dt.tz_localize(None),
            "resource": raw[resource_col].astype(str) if resource_col else "unknown",
        }
    )
    if log["timestamp"].isna().any():
        raise SchemaError("timestamp column contains unparseable values")
    log = log.sort_values(["case_id", "timestamp"], kind="stable").reset_index(drop=True)
    return log[LOG_COLUMNS]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def load_xes(
    path: str | Path,
    activity_key: str = "concept:name",
    timestamp_key: str = "time:timestamp",
    resource_key: str = "org:resource",
) -> pd.DataFrame:
    """Load an IEEE XES event log (plain or ``.gz``) into the standard event-log frame.

    Uses ``defusedxml`` so untrusted files cannot trigger entity-expansion attacks. Events without
    an activity or timestamp are skipped and counted in the error if nothing usable remains.
    """
    source = Path(path)
    opener: Any = gzip.open if source.suffix == ".gz" else open
    rows: list[tuple[str, str, str, str]] = []
    unnamed = 0
    with opener(source, "rb") as handle:
        for _, elem in iterparse(handle, events=("end",)):
            if _local(elem.tag) != "trace":
                continue
            attrs = {c.get("key"): c.get("value") for c in elem if _local(c.tag) != "event"}
            case_id = attrs.get("concept:name")
            if not case_id:
                case_id = f"trace-{unnamed}"
                unnamed += 1
            for event in elem:
                if _local(event.tag) != "event":
                    continue
                values = {c.get("key"): c.get("value") for c in event}
                activity, stamp = values.get(activity_key), values.get(timestamp_key)
                if activity and stamp:
                    rows.append((case_id, activity, stamp, values.get(resource_key) or "unknown"))
            elem.clear()
    if not rows:
        raise SchemaError(f"no usable events (activity and timestamp) found in {source}")
    log = pd.DataFrame(rows, columns=LOG_COLUMNS)
    log["timestamp"] = pd.to_datetime(log["timestamp"], utc=True).dt.tz_localize(None)
    return log.sort_values(["case_id", "timestamp"], kind="stable").reset_index(drop=True)


def load_log(
    path: str | Path,
    case_col: str | None = None,
    activity_col: str | None = None,
    timestamp_col: str | None = None,
    resource_col: str | None = None,
    sep: str = ",",
) -> pd.DataFrame:
    """Load an event log from XES (``.xes``, ``.xes.gz``) or a flat CSV."""
    name = str(path).lower()
    if name.endswith((".xes", ".xes.gz")):
        return load_xes(path)
    if not (case_col and activity_col and timestamp_col):
        raise SchemaError("CSV logs need --case-col, --activity-col and --timestamp-col")
    return load_flat_log(path, case_col, activity_col, timestamp_col, resource_col, sep)
