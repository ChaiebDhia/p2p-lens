from __future__ import annotations

import pandas as pd
import pytest
import yaml

from p2p_lens import cli
from p2p_lens.conformance import (
    ROLE_TO_ACTIVITY,
    check_precedence,
    load_activity_map,
    remap_log,
)
from p2p_lens.eventlog import build_event_log
from p2p_lens.export import build_case_table, export_tables
from p2p_lens.schema import SchemaError


def test_export_tables_match_analysis(tmp_path, dataset, analysis) -> None:
    activities, cases = export_tables(dataset, tmp_path)
    log = pd.read_csv(activities)
    table = pd.read_csv(cases)
    assert list(log.columns) == ["Case ID", "Activity", "Timestamp", "Resource"]
    assert len(log) == len(build_event_log(dataset))
    assert len(table) == analysis.n_cases
    for name, count in analysis.deviation_counts.items():
        assert int(table[name].sum()) == count


def test_case_table_values(dataset) -> None:
    table = build_case_table(dataset)
    assert table["case_id"].is_unique
    assert (table["po_value_eur"] > 0).all()
    assert set(table["payment_terms_days"]) <= {14, 30, 45, 60}


def test_cli_export(tmp_path) -> None:
    cli.main(["generate", "--cases", "100", "--out", str(tmp_path / "d")])
    assert cli.main(["export", "--data", str(tmp_path / "d"), "--out", str(tmp_path / "e")]) == 0
    assert (tmp_path / "e" / "activities.csv").exists()


def _renamed_log_csv(path, dataset) -> None:
    log = build_event_log(dataset)
    log["activity"] = "SAP: " + log["activity"]
    log.to_csv(path, index=False)


def _map_file(path) -> None:
    roles = {role: [f"SAP: {name}"] for role, name in ROLE_TO_ACTIVITY.items()}
    roles["mandatory"] = ["order", "goods_receipt", "invoice", "payment"]  # type: ignore[assignment]
    path.write_text(yaml.safe_dump(roles))


def test_activity_map_recovers_ground_truth_on_a_renamed_log(tmp_path, dataset, truth) -> None:
    csv, mapping = tmp_path / "log.csv", tmp_path / "map.yaml"
    _renamed_log_csv(csv, dataset)
    _map_file(mapping)
    from p2p_lens.eventlog import load_flat_log

    log = load_flat_log(csv, "case_id", "activity", "timestamp")
    amap = load_activity_map(mapping)
    remapped = remap_log(log, amap)
    result = check_precedence(remapped, amap.mandatory)
    gr_ir = [v for k, v in result.violations.items() if "Goods Receipt ->" in k]
    assert gr_ir == [truth.invoice_before_gr]
    assert result.missing_mandatory == 0


def test_cli_analyze_log_with_map(tmp_path, dataset, truth) -> None:
    csv, mapping, out = tmp_path / "log.csv", tmp_path / "map.yaml", tmp_path / "out"
    _renamed_log_csv(csv, dataset)
    _map_file(mapping)
    code = cli.main(
        [
            "analyze-log",
            "--log",
            str(csv),
            "--case-col",
            "case_id",
            "--activity-col",
            "activity",
            "--timestamp-col",
            "timestamp",
            "--p2p-map",
            str(mapping),
            "--out",
            str(out),
        ]
    )
    text = (out / "report.md").read_text()
    assert code == 0
    assert "P2P conformance on mapped activities" in text
    assert f"| Post Goods Receipt -> Post Invoice Receipt | {truth.invoice_before_gr} |" in text


def test_example_map_is_valid() -> None:
    amap = load_activity_map("examples/p2p-map.example.yaml")
    assert len(amap.names) == 7
    assert len(amap.mandatory) == 4


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("- just a list", "mapping"),
        ("bogus: [a]", "unknown role"),
        ("order: a", "list of activity names"),
        ("{}", "no activities"),
        ("order: [a]\nmandatory: [invoice]", "not present"),
    ],
)
def test_bad_activity_maps(tmp_path, content: str, message: str) -> None:
    path = tmp_path / "m.yaml"
    path.write_text(content)
    with pytest.raises(SchemaError, match=message):
        load_activity_map(path)


def test_map_that_matches_nothing(dataset) -> None:
    from p2p_lens.conformance import ActivityMap

    with pytest.raises(SchemaError, match="none of the mapped"):
        remap_log(build_event_log(dataset), ActivityMap({"Nope": "x"}, ()))


def test_default_mandatory_excludes_optional_roles(tmp_path) -> None:
    path = tmp_path / "m.yaml"
    path.write_text("requisition: [a]\norder: [b]\nchange: [c]\ninvoice: [d]\n")
    amap = load_activity_map(path)
    assert len(amap.mandatory) == 2


def test_executive_summary_is_in_the_report(tmp_path) -> None:
    cli.main(["demo", "--out", str(tmp_path), "--cases", "300"])
    text = (tmp_path / "report" / "report.md").read_text()
    assert "## Executive summary" in text
    assert "hypotheses to test" in text
    assert "largest sized opportunity" in text
    assert text.index("## Executive summary") < text.index("## Findings")
