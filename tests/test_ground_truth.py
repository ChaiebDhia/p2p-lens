"""The strongest test: detection must reproduce the injected ground truth exactly."""

from __future__ import annotations

import pytest

from p2p_lens.analysis import analyze
from p2p_lens.conformance import DEVIATIONS
from p2p_lens.synth import GroundTruth, generate


def test_detected_counts_equal_injected_counts(analysis, truth: GroundTruth) -> None:
    for name in DEVIATIONS:
        assert analysis.deviation_counts[name] == getattr(truth, name), name


@pytest.mark.parametrize("seed", [1, 2, 3, 11])
def test_ground_truth_holds_across_seeds(seed: int) -> None:
    ds, gt = generate(n_cases=300, seed=seed)
    counts = analyze(ds).deviation_counts
    assert {k: counts[k] for k in DEVIATIONS} == {k: getattr(gt, k) for k in DEVIATIONS}


def test_precedence_violations_match_invoice_before_gr(analysis, truth: GroundTruth) -> None:
    gr_ir = [v for k, v in analysis.conformance.violations.items() if "Goods Receipt ->" in k]
    assert gr_ir == [truth.invoice_before_gr]


def test_every_other_precedence_rule_is_clean(analysis) -> None:
    others = [v for k, v in analysis.conformance.violations.items() if "Goods Receipt ->" not in k]
    assert others == [0, 0, 0, 0]
