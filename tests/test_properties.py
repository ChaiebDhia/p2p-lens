"""Property-based tests: invariants that must hold for any seed, size or rates."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from p2p_lens.analysis import analyze
from p2p_lens.conformance import DEVIATIONS
from p2p_lens.copilot import check_grounding, extractive_answer, retrieve
from p2p_lens.findings import build_findings
from p2p_lens.synth import DeviationRates, generate

FAST = settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
rate = st.floats(min_value=0.0, max_value=0.6)


@FAST
@given(
    seed=st.integers(0, 10_000),
    n=st.integers(20, 120),
    rates=st.builds(DeviationRates, rate, rate, rate, rate, rate, rate),
)
def test_detection_equals_ground_truth_for_any_rates(
    seed: int, n: int, rates: DeviationRates
) -> None:
    ds, truth = generate(n, seed=seed, rates=rates)
    counts = analyze(ds).deviation_counts
    assert {k: counts[k] for k in DEVIATIONS} == {k: getattr(truth, k) for k in DEVIATIONS}


@FAST
@given(seed=st.integers(0, 10_000), n=st.integers(20, 100))
def test_log_invariants(seed: int, n: int) -> None:
    ds, _ = generate(n, seed=seed)
    a = analyze(ds)
    assert a.n_cases == n
    assert a.log.variants["cases"].sum() == n
    assert (a.log.durations >= 0).all()
    assert 0.0 <= a.conformance.conformance_rate <= 1.0
    assert (a.log.edges["mean_days"] >= 0).all()


@FAST
@given(
    seed=st.integers(0, 500),
    question=st.text(alphabet="abcdefghij klmnop", min_size=0, max_size=40),
)
def test_extractive_answers_always_pass_the_grounding_check(seed: int, question: str) -> None:
    findings = build_findings(analyze(generate(40, seed=seed)[0]))
    context = retrieve(question, findings)
    assert len(context) <= 3
    if context:
        assert check_grounding(extractive_answer(context), context).ok
