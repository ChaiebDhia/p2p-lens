from __future__ import annotations

import json

import pytest

from p2p_lens import cli
from p2p_lens.findings import build_findings
from p2p_lens.report import (
    p2p_blocks,
    render_html,
    render_markdown,
    short_variant,
    write_charts,
)
from p2p_lens.value import compute_value, load_assumptions


def test_short_variant() -> None:
    assert short_variant("Create Purchase Order > Post Goods Receipt") == "PO > GR"


def test_markdown_and_html_reports(analysis, tmp_path) -> None:
    findings = build_findings(analysis)
    assume = load_assumptions()
    value = compute_value(analysis, assume, 100_000)
    charts = write_charts(analysis, tmp_path)
    blocks = p2p_blocks(analysis, findings, value, assume, charts)
    md = render_markdown(blocks)
    page = render_html(blocks, tmp_path)
    assert "# Procure-to-pay process intelligence report" in md
    assert "Value model (assumption-driven)" in md
    assert "excluding contractual payment terms" in md
    assert page.startswith("<!doctype html>")
    assert "<table>" in page
    assert "data:image/png;base64," in page
    assert "<script" not in page


def test_html_escapes_content() -> None:
    from p2p_lens.report import Block

    page = render_html([Block("p", "<script>alert(1)</script>")])
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_cli_end_to_end(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    data, out = tmp_path / "data", tmp_path / "out"
    assert cli.main(["generate", "--cases", "300", "--seed", "9", "--out", str(data)]) == 0
    truth = json.loads((data / "ground_truth.json").read_text())
    assert truth["n_cases"] == 300
    assert cli.main(["analyze", "--data", str(data), "--out", str(out)]) == 0
    assert (out / "report.md").exists() and (out / "report.html").exists()
    findings = json.loads((out / "findings.json").read_text())
    assert len(findings) == 11
    capsys.readouterr()
    assert cli.main(["ask", "--data", str(data), "how many invoices are paid late?"]) == 0
    assert "[F08]" in capsys.readouterr().out


def test_cli_demo_and_log(tmp_path) -> None:
    assert cli.main(["demo", "--out", str(tmp_path / "demo"), "--cases", "200"]) == 0
    assert (tmp_path / "demo" / "report" / "report.md").exists()
    log = tmp_path / "log.csv"
    log.write_text("c,a,t\n1,A,2025-01-01\n1,B,2025-01-03\n2,A,2025-01-01\n2,B,2025-01-02\n")
    out = tmp_path / "lg"
    code = cli.main(
        [
            "analyze-log",
            "--log",
            str(log),
            "--case-col",
            "c",
            "--activity-col",
            "a",
            "--timestamp-col",
            "t",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert "2 cases" in (out / "report.md").read_text()


def test_cli_errors_return_code_2(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["analyze", "--data", str(tmp_path), "--out", str(tmp_path / "o")]) == 2
    assert "error:" in capsys.readouterr().err
    assert cli.main(["ask", "--data", str(tmp_path), "--backend", "openai", "x"]) == 2


def test_cli_ask_falls_back_when_backend_is_down(tmp_path, capsys, monkeypatch) -> None:
    cli.main(["generate", "--cases", "200", "--out", str(tmp_path)])
    monkeypatch.setenv("P2P_LENS_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("P2P_LENS_API_KEY", "k")
    monkeypatch.setenv("P2P_LENS_MODEL", "m")
    capsys.readouterr()
    code = cli.main(
        ["ask", "--data", str(tmp_path), "--backend", "openai", "--model", "m2", "late payment"]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "[F08]" in captured.out
    assert "fell back" in captured.err


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "1.0.0" in capsys.readouterr().out


def test_legend_only_for_p2p_logs(tmp_path) -> None:
    log = tmp_path / "log.csv"
    log.write_text("c,a,t\n1,A,2025-01-01\n1,B,2025-01-03\n")
    out = tmp_path / "o"
    cli.main(
        [
            "analyze-log",
            "--log",
            str(log),
            "--case-col",
            "c",
            "--activity-col",
            "a",
            "--timestamp-col",
            "t",
            "--out",
            str(out),
        ]
    )
    assert "Legend" not in (out / "report.md").read_text()
    cli.main(["demo", "--out", str(tmp_path / "d"), "--cases", "100"])
    assert "Legend" in (tmp_path / "d" / "report" / "report.md").read_text()
