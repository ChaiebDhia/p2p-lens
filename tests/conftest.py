from __future__ import annotations

import pytest

from p2p_lens.analysis import P2PAnalysis, analyze
from p2p_lens.schema import Dataset
from p2p_lens.synth import GroundTruth, generate


@pytest.fixture(scope="session")
def generated() -> tuple[Dataset, GroundTruth]:
    return generate(n_cases=800, seed=7)


@pytest.fixture(scope="session")
def dataset(generated: tuple[Dataset, GroundTruth]) -> Dataset:
    return generated[0]


@pytest.fixture(scope="session")
def truth(generated: tuple[Dataset, GroundTruth]) -> GroundTruth:
    return generated[1]


@pytest.fixture(scope="session")
def analysis(dataset: Dataset) -> P2PAnalysis:
    return analyze(dataset)
