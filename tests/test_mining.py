from __future__ import annotations

import pandas as pd
import pytest

from p2p_lens.eventlog import build_event_log, load_flat_log
from p2p_lens.mining import analyze_log, edge_table, variant_table
from p2p_lens.schema import ACT_IR, ACT_PAY, SchemaError


def _log(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["case_id", "activity", "timestamp"]).assign(
        timestamp=lambda d: pd.to_datetime(d["timestamp"])
    )


def test_event_log_is_sorted_and_complete(dataset) -> None:
    log = build_event_log(dataset)
    assert list(log.columns) == ["case_id", "activity", "timestamp", "resource"]
    assert log["case_id"].nunique() == len(dataset.ekko)
    for _, grp in log.groupby("case_id"):
        assert grp["timestamp"].is_monotonic_increasing


def test_variants_edges_and_durations_on_known_log() -> None:
    log = _log(
        [
            ("1", "A", "2025-01-01"),
            ("1", "B", "2025-01-03"),
            ("1", "C", "2025-01-04"),
            ("2", "A", "2025-01-01"),
            ("2", "B", "2025-01-05"),
            ("2", "C", "2025-01-06"),
            ("3", "A", "2025-01-01"),
            ("3", "C", "2025-01-02"),
        ]
    )
    variants = variant_table(log)
    assert variants.loc[0, "variant"] == "A > B > C"
    assert variants.loc[0, "cases"] == 2
    assert variants["share"].sum() == pytest.approx(1.0)
    edges = edge_table(log).set_index(["src", "dst"])
    assert edges.loc[("A", "B"), "mean_days"] == pytest.approx(3.0)
    assert edges.loc[("A", "B"), "count"] == 2
    result = analyze_log(log)
    assert result.n_cases == 3
    assert result.throughput["max_days"] == pytest.approx(5.0)


def test_single_event_cases_have_no_edges() -> None:
    log = _log([("1", "A", "2025-01-01"), ("2", "A", "2025-01-02")])
    assert edge_table(log).empty


def test_empty_or_malformed_log_is_rejected() -> None:
    with pytest.raises(ValueError):
        analyze_log(pd.DataFrame({"case_id": [], "activity": [], "timestamp": []}))
    with pytest.raises(ValueError, match="missing column"):
        variant_table(pd.DataFrame({"x": [1]}))


def test_payment_wait_dominates_but_is_contractual(analysis) -> None:
    top = analysis.log.edges.iloc[0]
    assert (top["src"], top["dst"]) == (ACT_IR, ACT_PAY)


def test_high_value_orders_wait_longer_for_release(analysis) -> None:
    assert analysis.approval["median_high_days"] > 2 * analysis.approval["median_low_days"]


def test_slow_vendors_surface_first(analysis) -> None:
    top5 = set(analysis.vendors["vendor"].head(5))
    assert len(top5 & {"V0001", "V0002", "V0003", "V0004", "V0005"}) >= 4


def test_load_flat_log(tmp_path) -> None:
    path = tmp_path / "log.csv"
    path.write_text(
        "case,act,ts,who\n1,A,2025-01-01T10:00:00Z,x\n1,B,2025-01-02T10:00:00Z,y\n"
        "2,A,2025-01-01T10:00:00Z,x\n"
    )
    log = load_flat_log(path, "case", "act", "ts", "who")
    assert len(log) == 3
    assert log["timestamp"].dt.tz is None
    no_resource = load_flat_log(path, "case", "act", "ts")
    assert set(no_resource["resource"]) == {"unknown"}
    with pytest.raises(SchemaError, match="columns not found"):
        load_flat_log(path, "nope", "act", "ts")
