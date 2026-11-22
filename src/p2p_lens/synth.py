"""Seeded synthetic SAP-style procure-to-pay data with known ground truth.

Every deviation is injected from an explicit per-case flag, so the analysis can be
checked against the exact number of injected cases (see tests/test_ground_truth.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from p2p_lens.schema import TABLE_COLUMNS, Dataset


@dataclass(frozen=True)
class DeviationRates:
    """Probability that a case carries each injected deviation."""

    no_pr: float = 0.12
    rework: float = 0.18
    invoice_before_gr: float = 0.07
    price_mismatch: float = 0.06
    duplicate_invoice: float = 0.015
    late_payment: float = 0.21


@dataclass(frozen=True)
class GroundTruth:
    """Exact counts of the deviations that were injected."""

    n_cases: int
    no_pr: int
    rework: int
    invoice_before_gr: int
    price_mismatch: int
    duplicate_invoice: int
    late_payment: int


N_VENDORS = 40
N_SLOW_VENDORS = 5
HIGH_VALUE = 10_000.0


def _days(value: float) -> pd.Timedelta:
    return pd.Timedelta(days=float(value))


def generate(
    n_cases: int = 2000,
    seed: int = 42,
    start: str = "2025-01-01",
    window_days: int = 365,
    rates: DeviationRates | None = None,
) -> tuple[Dataset, GroundTruth]:
    """Generate a dataset of ``n_cases`` purchase orders and its ground truth."""
    if n_cases < 1:
        raise ValueError("n_cases must be at least 1")
    rates = rates or DeviationRates()
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp(start)
    vendors = [f"V{v:04d}" for v in range(1, N_VENDORS + 1)]
    slow = set(vendors[:N_SLOW_VENDORS])
    buyers = [f"BUYER{b:02d}" for b in range(1, 9)]

    ekko, ekpo, ekbe, eban, chg, pay = [], [], [], [], [], []
    counts = dict.fromkeys(
        [
            "no_pr",
            "rework",
            "invoice_before_gr",
            "price_mismatch",
            "duplicate_invoice",
            "late_payment",
        ],
        0,
    )
    doc_seq = 5_000_000

    for idx in range(n_cases):
        ebeln = f"45{idx:08d}"
        vendor = vendors[int(rng.integers(0, N_VENDORS))]
        buyer = buyers[int(rng.integers(0, len(buyers)))]
        po_dt = (
            t0
            + _days(int(rng.integers(0, window_days)))
            + pd.Timedelta(hours=int(rng.integers(8, 17)))
        )

        n_items = int(rng.integers(1, 5))
        total = float(rng.lognormal(8.1, 1.0))
        shares = rng.dirichlet(np.ones(n_items))
        values = [round(total * float(s), 2) for s in shares[:-1]]
        values.append(round(total - sum(values), 2))
        if values[-1] <= 0:
            values = [round(total / n_items, 2)] * n_items
        po_value = round(sum(values), 2)
        for item, value in enumerate(values, start=1):
            ekpo.append(
                {
                    "EBELN": ebeln,
                    "EBELP": f"{item * 10:05d}",
                    "MATNR": f"MAT{int(rng.integers(1, 400)):05d}",
                    "MENGE": int(rng.integers(1, 200)),
                    "NETWR": value,
                }
            )

        has_pr = rng.random() >= rates.no_pr
        if has_pr:
            eban.append(
                {
                    "BANFN": f"10{idx:08d}",
                    "EBELN": ebeln,
                    "BADAT": po_dt - _days(rng.uniform(0.5, 6.0)),
                    "ERNAM": buyer,
                }
            )
        else:
            counts["no_pr"] += 1

        if po_value > HIGH_VALUE:
            rel_dt = po_dt + _days(rng.uniform(2.0, 7.0))
        else:
            rel_dt = po_dt + _days(rng.uniform(0.2, 2.0))

        lead_mean = 14.0 if vendor in slow else 6.0
        lead = max(4.0, float(rng.gamma(4.0, lead_mean / 4.0)))
        gr_dt = rel_dt + _days(lead)

        reworked = rng.random() < rates.rework
        if reworked:
            counts["rework"] += 1
            n_changes = int(rng.choice([1, 2, 3], p=[0.7, 0.2, 0.1]))
            for _ in range(n_changes):
                chg.append(
                    {
                        "EBELN": ebeln,
                        "UDATE": rel_dt + _days(rng.uniform(0.05, lead * 0.9)),
                        "FNAME": str(rng.choice(["NETPR", "MENGE", "EINDT"])),
                        "USERNAME": buyer,
                    }
                )

        invoice_early = rng.random() < rates.invoice_before_gr
        if invoice_early:
            counts["invoice_before_gr"] += 1
            ir_dt = gr_dt - _days(rng.uniform(0.5, 3.5))
        else:
            ir_dt = gr_dt + _days(rng.uniform(0.5, 5.0))

        mismatch = rng.random() < rates.price_mismatch
        if mismatch:
            counts["price_mismatch"] += 1
            sign = 1.0 if rng.random() < 0.7 else -1.0
            invoice_amount = round(po_value * (1.0 + sign * rng.uniform(0.07, 0.20)), 2)
        else:
            invoice_amount = round(po_value * rng.uniform(0.98, 1.02), 2)

        terms = int(rng.choice([14, 30, 45, 60]))
        ekko.append(
            {
                "EBELN": ebeln,
                "LIFNR": vendor,
                "BEDAT": po_dt,
                "ERNAM": buyer,
                "BSART": "NB",
                "REL_DATE": rel_dt,
                "ZBD1T": terms,
                "WAERS": "EUR",
            }
        )
        ekbe.append(
            {
                "EBELN": ebeln,
                "BELNR": f"{doc_seq}",
                "VGABE": "1",
                "BUDAT": gr_dt,
                "DMBTR": po_value,
            }
        )
        doc_seq += 1
        ekbe.append(
            {
                "EBELN": ebeln,
                "BELNR": f"{doc_seq}",
                "VGABE": "2",
                "BUDAT": ir_dt,
                "DMBTR": invoice_amount,
            }
        )
        doc_seq += 1

        if rng.random() < rates.duplicate_invoice:
            counts["duplicate_invoice"] += 1
            ekbe.append(
                {
                    "EBELN": ebeln,
                    "BELNR": f"{doc_seq}",
                    "VGABE": "2",
                    "BUDAT": ir_dt + _days(rng.uniform(1.0, 5.0)),
                    "DMBTR": invoice_amount,
                }
            )
            doc_seq += 1

        due = ir_dt + _days(terms)
        late = rng.random() < rates.late_payment
        if late:
            counts["late_payment"] += 1
            pay_dt = due + _days(rng.uniform(2.0, 20.0))
        else:
            pay_dt = due - _days(rng.uniform(0.0, 3.0))
        pay.append({"EBELN": ebeln, "AUGDT": pay_dt, "DMBTR": invoice_amount})

    frames = {
        "EKKO": pd.DataFrame(ekko),
        "EKPO": pd.DataFrame(ekpo),
        "EKBE": pd.DataFrame(ekbe),
        "EBAN": pd.DataFrame(eban, columns=TABLE_COLUMNS["EBAN"]),
        "PO_CHANGES": pd.DataFrame(chg, columns=TABLE_COLUMNS["PO_CHANGES"]),
        "PAYMENTS": pd.DataFrame(pay),
    }
    for name, columns in TABLE_COLUMNS.items():
        frames[name] = frames[name][columns]
    for name in ("EBAN", "PO_CHANGES"):
        for col in ("BADAT", "UDATE"):
            if col in frames[name].columns:
                frames[name][col] = pd.to_datetime(frames[name][col])
    ds = Dataset(
        ekko=frames["EKKO"],
        ekpo=frames["EKPO"],
        ekbe=frames["EKBE"],
        eban=frames["EBAN"],
        po_changes=frames["PO_CHANGES"],
        payments=frames["PAYMENTS"],
    )
    ds.validate()
    return ds, GroundTruth(n_cases=n_cases, **counts)
