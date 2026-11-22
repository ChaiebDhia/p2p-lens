"""The numbers quoted in the README must match a fresh run of the default demo."""

from __future__ import annotations

from pathlib import Path

from p2p_lens.analysis import analyze
from p2p_lens.findings import build_findings
from p2p_lens.synth import generate

README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_quotes_the_current_demo_results() -> None:
    findings = {f.id: f for f in build_findings(analyze(generate(2000, 42)[0]))}
    text = README.read_text(encoding="utf-8")
    m = {k: f.metrics for k, f in findings.items()}
    expected = [
        f"{int(m['F02']['variants'])} process variants",
        f"covers {m['F02']['happy_path_pct']}% of cases",
        f"{m['F08']['late_pct']}% of invoices paid late",
        f"{m['F03']['rework_pct']}% of orders reworked",
        f"{m['F04']['no_pr_pct']}% of orders without a requisition",
        f"median of {m['F09']['release_high_median_days']} days",
        f"{m['F09']['release_low_median_days']} for smaller orders",
    ]
    missing = [e for e in expected if e not in text]
    assert not missing, f"README is out of date, missing: {missing}"
