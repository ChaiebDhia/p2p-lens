"""Deterministic, citable findings derived from an analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field

from p2p_lens.analysis import P2PAnalysis
from p2p_lens.schema import ACT_PAY, HAPPY_PATH


class Finding(BaseModel):
    """One verifiable statement about the process, with the numbers it rests on."""

    id: str = Field(pattern=r"^F\d{2}$")
    title: str
    text: str
    tags: list[str]
    metrics: dict[str, float]


def _pct(part: float, whole: float) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def build_findings(a: P2PAnalysis) -> list[Finding]:
    """Build findings F01..F11 from an analysis. Same input gives the same output."""
    n = a.n_cases
    c = a.deviation_counts
    t = a.log.throughput
    happy = " > ".join(HAPPY_PATH)
    variants = a.log.variants
    happy_share = _pct(float(variants.loc[variants["variant"] == happy, "cases"].sum()), n)
    top5 = _pct(float(variants["cases"].head(5).sum()), n)
    # The invoice-to-payment wait is set by contractual payment terms, so it is not a bottleneck.
    edges = a.log.edges[a.log.edges["dst"] != ACT_PAY]
    top_edge = edges.iloc[0]
    slow_vendors = a.vendors.head(3)
    out: list[Finding] = []

    def add(title: str, text: str, tags: list[str], metrics: dict[str, float]) -> None:
        out.append(
            Finding(id=f"F{len(out) + 1:02d}", title=title, text=text, tags=tags, metrics=metrics)
        )

    add(
        "Cycle time",
        f"Across {n} purchase orders, the median time from first to last event is "
        f"{t['median_days']:.1f} days and the 90th percentile is {t['p90_days']:.1f} days.",
        ["cycle time", "throughput", "duration", "lead time"],
        {"cases": float(n), "median_days": t["median_days"], "p90_days": t["p90_days"]},
    )
    add(
        "Process variants",
        f"There are {len(variants)} distinct process variants. The reference path "
        f"({happy}) covers {happy_share}% of cases, and the five most common variants cover "
        f"{top5}%.",
        ["variants", "happy path", "straight-through", "touchless", "standard process"],
        {"variants": float(len(variants)), "happy_path_pct": happy_share, "top5_pct": top5},
    )
    add(
        "Rework",
        f"{c['rework']} purchase orders ({_pct(c['rework'], n)}%) were changed after release.",
        ["rework", "change", "changes", "amendment", "purchase order"],
        {"rework_cases": float(c["rework"]), "rework_pct": _pct(c["rework"], n)},
    )
    add(
        "Orders without requisition",
        f"{c['no_pr']} purchase orders ({_pct(c['no_pr'], n)}%) have no purchase requisition.",
        ["requisition", "maverick", "compliance", "no pr", "purchase order"],
        {"no_pr_cases": float(c["no_pr"]), "no_pr_pct": _pct(c["no_pr"], n)},
    )
    add(
        "Invoice before goods receipt",
        f"{c['invoice_before_gr']} purchase orders ({_pct(c['invoice_before_gr'], n)}%) had the "
        "invoice posted before the goods receipt, which breaks the three-way-match order.",
        ["invoice", "goods receipt", "three-way match", "compliance", "control"],
        {
            "invoice_before_gr_cases": float(c["invoice_before_gr"]),
            "invoice_before_gr_pct": _pct(c["invoice_before_gr"], n),
        },
    )
    add(
        "Price mismatch",
        f"{c['price_mismatch']} purchase orders ({_pct(c['price_mismatch'], n)}%) were invoiced "
        f"more than 5% away from the order value. Overbilling exposure is "
        f"{a.money['overbilling_exposure']:.0f} EUR.",
        ["price", "mismatch", "invoice", "overbilling", "tolerance", "money"],
        {
            "price_mismatch_cases": float(c["price_mismatch"]),
            "price_mismatch_pct": _pct(c["price_mismatch"], n),
            "overbilling_eur": round(a.money["overbilling_exposure"], 0),
        },
    )
    add(
        "Duplicate invoices",
        f"{c['duplicate_invoice']} purchase orders ({_pct(c['duplicate_invoice'], n)}%) carry a "
        f"duplicate invoice, worth {a.money['duplicate_invoice_value']:.0f} EUR in total.",
        ["duplicate", "invoice", "leakage", "payment", "money"],
        {
            "duplicate_cases": float(c["duplicate_invoice"]),
            "duplicate_eur": round(a.money["duplicate_invoice_value"], 0),
        },
    )
    add(
        "Late payment",
        f"{c['late_payment']} invoices ({_pct(c['late_payment'], n)}%) were paid after the due "
        f"date, on average {a.money['mean_days_late']:.1f} days late.",
        ["late", "payment", "due date", "terms", "supplier"],
        {
            "late_cases": float(c["late_payment"]),
            "late_pct": _pct(c["late_payment"], n),
            "mean_days_late": round(a.money["mean_days_late"], 1),
        },
    )
    add(
        "Biggest bottleneck",
        f"Excluding contractual payment terms, the step '{top_edge['src']}' to '{top_edge['dst']}' "
        f"accounts for the most waiting time: "
        f"{top_edge['total_days']:.0f} case-days in total, {top_edge['mean_days']:.1f} days on "
        f"average. Releases of orders above {a.approval['threshold']:.0f} EUR take a median of "
        f"{a.approval['median_high_days']:.1f} days versus {a.approval['median_low_days']:.1f} "
        "days for smaller orders.",
        ["bottleneck", "waiting", "approval", "release", "delay", "high value"],
        {
            "top_edge_total_days": round(float(top_edge["total_days"]), 0),
            "top_edge_mean_days": round(float(top_edge["mean_days"]), 1),
            "release_high_median_days": round(a.approval["median_high_days"], 1),
            "release_low_median_days": round(a.approval["median_low_days"], 1),
        },
    )
    names = ", ".join(str(v) for v in slow_vendors["vendor"])
    slowest = float(slow_vendors["mean_gr_lead_days"].iloc[0])
    overall = float(a.vendors["mean_gr_lead_days"].mean())
    add(
        "Slow vendors",
        f"The slowest vendors by delivery lead time are {names}. The slowest averages "
        f"{slowest:.1f} days from release to goods receipt, against {overall:.1f} days across "
        "all vendors.",
        ["vendor", "supplier", "delivery", "lead time", "goods receipt", "slow"],
        {"slowest_vendor_lead_days": round(slowest, 1), "all_vendor_lead_days": round(overall, 1)},
    )
    cf = a.conformance
    add(
        "Conformance",
        f"{cf.conforming_cases} of {n} purchase orders ({_pct(cf.conforming_cases, n)}%) follow "
        "every precedence rule and contain all mandatory steps.",
        ["conformance", "compliance", "rules", "precedence", "fitness"],
        {
            "conforming_cases": float(cf.conforming_cases),
            "conformance_pct": _pct(cf.conforming_cases, n),
        },
    )
    return out
