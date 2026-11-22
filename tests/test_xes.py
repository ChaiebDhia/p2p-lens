from __future__ import annotations

import gzip

import pytest

from p2p_lens.cli import main
from p2p_lens.eventlog import load_log, load_xes
from p2p_lens.schema import SchemaError

XES = """<?xml version="1.0" encoding="UTF-8"?>
<log xmlns="http://www.xes-standard.org/">
  <trace>
    <string key="concept:name" value="case-1"/>
    <event>
      <string key="concept:name" value="Register"/>
      <date key="time:timestamp" value="2025-01-01T10:00:00.000+01:00"/>
      <string key="org:resource" value="alice"/>
    </event>
    <event>
      <string key="concept:name" value="Approve"/>
      <date key="time:timestamp" value="2025-01-03T10:00:00.000+01:00"/>
    </event>
    <event><string key="concept:name" value="No timestamp"/></event>
  </trace>
  <trace>
    <event>
      <string key="concept:name" value="Register"/>
      <date key="time:timestamp" value="2025-01-02T10:00:00.000+01:00"/>
    </event>
  </trace>
</log>
"""


def test_load_xes_parses_namespaced_files(tmp_path) -> None:
    path = tmp_path / "log.xes"
    path.write_text(XES)
    log = load_xes(path)
    assert len(log) == 3
    assert set(log["case_id"]) == {"case-1", "trace-0"}
    assert log["timestamp"].dt.tz is None
    assert "alice" in set(log["resource"])
    assert "unknown" in set(log["resource"])


def test_load_xes_gzip_and_dispatch(tmp_path) -> None:
    path = tmp_path / "log.xes.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(XES)
    assert len(load_log(path)) == 3


def test_load_xes_without_usable_events(tmp_path) -> None:
    path = tmp_path / "empty.xes"
    path.write_text("<log><trace><event><string key='x' value='y'/></event></trace></log>")
    with pytest.raises(SchemaError, match="no usable events"):
        load_xes(path)


def test_xml_entity_bomb_is_rejected(tmp_path) -> None:
    path = tmp_path / "bomb.xes"
    path.write_text(
        '<?xml version="1.0"?><!DOCTYPE log [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        "<log><trace><event><string key='concept:name' value='&b;'/></event></trace></log>"
    )
    with pytest.raises(ValueError):
        load_xes(path)


def test_csv_needs_column_names(tmp_path) -> None:
    path = tmp_path / "log.csv"
    path.write_text("c,a,t\n1,A,2025-01-01\n")
    with pytest.raises(SchemaError, match="--case-col"):
        load_log(path)


def test_cli_analyze_xes(tmp_path) -> None:
    path = tmp_path / "log.xes"
    path.write_text(XES)
    out = tmp_path / "out"
    assert main(["analyze-log", "--log", str(path), "--out", str(out)]) == 0
    assert "2 cases" in (out / "report.md").read_text()
