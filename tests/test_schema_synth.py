from __future__ import annotations

import pandas as pd
import pytest

from p2p_lens.schema import Dataset, SchemaError
from p2p_lens.synth import DeviationRates, generate


def test_generation_is_deterministic() -> None:
    a, ga = generate(200, seed=5)
    b, gb = generate(200, seed=5)
    assert ga == gb
    pd.testing.assert_frame_equal(a.ekbe, b.ekbe)


def test_different_seeds_differ() -> None:
    a, _ = generate(200, seed=5)
    b, _ = generate(200, seed=6)
    assert not a.ekko["BEDAT"].equals(b.ekko["BEDAT"])


def test_rejects_zero_cases() -> None:
    with pytest.raises(ValueError):
        generate(0)


def test_zero_rates_inject_nothing() -> None:
    rates = DeviationRates(0, 0, 0, 0, 0, 0)
    ds, gt = generate(150, seed=3, rates=rates)
    assert gt.no_pr == gt.rework == gt.late_payment == 0
    assert len(ds.eban) == 150
    assert ds.po_changes.empty


def test_csv_round_trip(tmp_path, dataset: Dataset) -> None:
    dataset.save(tmp_path)
    loaded = Dataset.load(tmp_path)
    assert len(loaded.ekko) == len(dataset.ekko)
    assert loaded.ekko["BEDAT"].dtype.kind == "M"
    assert set(loaded.ekbe["VGABE"]) == {"1", "2"}


def test_load_missing_file(tmp_path) -> None:
    with pytest.raises(SchemaError, match="missing file"):
        Dataset.load(tmp_path)


def test_validate_catches_missing_column(dataset: Dataset) -> None:
    broken = Dataset(
        dataset.ekko.drop(columns="ZBD1T"),
        dataset.ekpo,
        dataset.ekbe,
        dataset.eban,
        dataset.po_changes,
        dataset.payments,
    )
    with pytest.raises(SchemaError, match="missing columns"):
        broken.validate()


def test_validate_catches_orphans_and_bad_types(dataset: Dataset) -> None:
    orphan = dataset.payments.copy()
    orphan.loc[0, "EBELN"] = "NOPE"
    with pytest.raises(SchemaError, match="not present in EKKO"):
        Dataset(
            dataset.ekko, dataset.ekpo, dataset.ekbe, dataset.eban, dataset.po_changes, orphan
        ).validate()
    text_dates = dataset.ekko.assign(BEDAT=dataset.ekko["BEDAT"].astype(str))
    with pytest.raises(SchemaError, match="datetime"):
        Dataset(
            text_dates,
            dataset.ekpo,
            dataset.ekbe,
            dataset.eban,
            dataset.po_changes,
            dataset.payments,
        ).validate()


def test_validate_catches_duplicates_vgabe_and_terms(dataset: Dataset) -> None:
    dup = pd.concat([dataset.ekko, dataset.ekko.head(1)], ignore_index=True)
    with pytest.raises(SchemaError, match="unique"):
        Dataset(
            dup, dataset.ekpo, dataset.ekbe, dataset.eban, dataset.po_changes, dataset.payments
        ).validate()
    bad_vgabe = dataset.ekbe.copy()
    bad_vgabe.loc[0, "VGABE"] = "9"
    with pytest.raises(SchemaError, match="VGABE"):
        Dataset(
            dataset.ekko,
            dataset.ekpo,
            bad_vgabe,
            dataset.eban,
            dataset.po_changes,
            dataset.payments,
        ).validate()
    bad_terms = dataset.ekko.copy()
    bad_terms.loc[0, "ZBD1T"] = 0
    with pytest.raises(SchemaError, match="ZBD1T"):
        Dataset(
            bad_terms,
            dataset.ekpo,
            dataset.ekbe,
            dataset.eban,
            dataset.po_changes,
            dataset.payments,
        ).validate()
