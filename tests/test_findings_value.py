from __future__ import annotations

import pytest

from p2p_lens.findings import build_findings
from p2p_lens.value import Assumptions, compute_value, load_assumptions


def test_findings_are_sequential_and_deterministic(analysis) -> None:
    first = build_findings(analysis)
    second = build_findings(analysis)
    assert [f.id for f in first] == [f"F{i:02d}" for i in range(1, 12)]
    assert first == second


def test_findings_numbers_match_analysis(analysis) -> None:
    findings = {f.id: f for f in build_findings(analysis)}
    assert findings["F03"].metrics["rework_cases"] == analysis.deviation_counts["rework"]
    assert findings["F08"].metrics["late_cases"] == analysis.deviation_counts["late_payment"]
    assert str(analysis.deviation_counts["no_pr"]) in findings["F04"].text


def test_bottleneck_finding_excludes_payment_terms(analysis) -> None:
    text = {f.id: f for f in build_findings(analysis)}["F09"].text
    assert "Clear Invoice" not in text.split("to")[1].split(":")[0]
    assert "Excluding contractual payment terms" in text


def test_value_model_scales_linearly(analysis) -> None:
    assume = load_assumptions()
    one = compute_value(analysis, assume, annual_cases=10_000)
    two = compute_value(analysis, assume, annual_cases=20_000)
    ratio = two.levers["base"].sum() / one.levers["base"].sum()
    assert ratio == pytest.approx(2.0)


def test_value_scenarios_are_ordered_and_roi_consistent(analysis) -> None:
    assume = load_assumptions()
    value = compute_value(analysis, assume, annual_cases=150_000)
    benefits = value.summary.set_index("scenario")["annual_benefit_eur"]
    assert benefits["conservative"] < benefits["base"] < benefits["optimistic"]
    row = value.summary.set_index("scenario").loc["base"]
    expected = 100 * (row["annual_benefit_eur"] - assume.program_cost_eur) / assume.program_cost_eur
    assert row["roi_year1_pct"] == pytest.approx(expected)
    assert row["payback_months"] == pytest.approx(
        12 * assume.program_cost_eur / row["annual_benefit_eur"]
    )


def test_default_annualisation_uses_observed_span(analysis) -> None:
    value = compute_value(analysis, load_assumptions())
    assert value.annual_cases == pytest.approx(analysis.n_cases * 365 / analysis.span_days)


def test_invalid_inputs_are_rejected(analysis, tmp_path) -> None:
    with pytest.raises(ValueError):
        compute_value(analysis, load_assumptions(), annual_cases=0)
    bad = tmp_path / "a.yaml"
    bad.write_text("cost_per_change_eur: -1\n")
    with pytest.raises(ValueError):
        load_assumptions(bad)


def test_custom_assumptions_file(tmp_path, analysis) -> None:
    path = tmp_path / "a.yaml"
    path.write_text(
        "cost_per_change_eur: 20\nchanges_per_reworked_case: 2\nlate_fee_rate: 0.01\n"
        "duplicate_interception_rate: 0.5\noverbilling_recovery_rate: 0.5\n"
        "program_cost_eur: 1000\nscenarios: {only: 1.0}\n"
    )
    assume = load_assumptions(path)
    assert isinstance(assume, Assumptions)
    assert list(compute_value(analysis, assume, 1000).summary["scenario"]) == ["only"]
