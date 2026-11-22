"""Markdown and self-contained HTML reports, plus optional PNG charts."""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from p2p_lens.analysis import P2PAnalysis
from p2p_lens.conformance import ConformanceResult
from p2p_lens.findings import Finding
from p2p_lens.mining import LogAnalysis
from p2p_lens.schema import (
    ACT_CHG,
    ACT_GR,
    ACT_IR,
    ACT_PAY,
    ACT_PO,
    ACT_PR,
    ACT_REL,
)
from p2p_lens.value import Assumptions, ValueCase

SHORT = {
    ACT_PR: "PR",
    ACT_PO: "PO",
    ACT_REL: "REL",
    ACT_CHG: "CHG",
    ACT_GR: "GR",
    ACT_IR: "IR",
    ACT_PAY: "PAY",
}
LEGEND = (
    "PR purchase requisition, PO purchase order, REL release, CHG change, "
    "GR goods receipt, IR invoice receipt, PAY payment clearing."
)


@dataclass
class Block:
    """One renderable report block: kind is h1, h2, p, table or img."""

    kind: str
    text: str = ""
    table: pd.DataFrame | None = None


def short_variant(variant: str, limit: int = 110) -> str:
    """Abbreviate known P2P activities and truncate very long labels."""
    text = " > ".join(SHORT.get(a, a) for a in variant.split(" > "))
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}" if abs(value) < 1000 else f"{value:,.0f}"
    return str(value)


def _md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(str(c) for c in df.columns) + " |"
    rule = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows = ["| " + " | ".join(_fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, rule, *rows])


def _html_table(df: pd.DataFrame) -> str:
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(_fmt(v))}</td>" for v in row) + "</tr>"
        for row in df.itertuples(index=False)
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _uses_p2p_names(log: LogAnalysis) -> bool:
    text = " ".join(log.variants["variant"].head(8))
    return any(name in text for name in SHORT)


def _variants_view(log: LogAnalysis, top: int = 8) -> pd.DataFrame:
    v = log.variants.head(top).copy()
    v["variant"] = v["variant"].map(short_variant)
    v["share_pct"] = (v["share"] * 100).round(1)
    return v[["variant", "cases", "share_pct"]]


def _edges_view(log: LogAnalysis, top: int = 6, exclude_payment: bool = False) -> pd.DataFrame:
    edges = log.edges[log.edges["dst"] != ACT_PAY] if exclude_payment else log.edges
    e = edges.head(top).copy()
    e["src"] = e["src"].map(lambda s: SHORT.get(s, s))
    e["dst"] = e["dst"].map(lambda s: SHORT.get(s, s))
    return e[["src", "dst", "count", "mean_days", "median_days", "p90_days", "total_days"]].round(1)


def log_blocks(
    log: LogAnalysis, title: str = "Process analysis", exclude_payment: bool = False
) -> list[Block]:
    """Blocks for any event log (no SAP tables needed)."""
    t = log.throughput
    return [
        Block("h1", title),
        Block(
            "p",
            f"{log.n_cases} cases, {log.n_events} events. Case duration: median "
            f"{t['median_days']:.1f} days, p90 {t['p90_days']:.1f} days, "
            f"max {t['max_days']:.1f} days.",
        ),
        Block("h2", "Most common variants"),
        Block("table", table=_variants_view(log)),
        *([Block("p", f"Legend: {LEGEND}")] if _uses_p2p_names(log) else []),
        Block(
            "h2",
            "Longest waits between consecutive steps"
            + (" (excluding contractual payment terms)" if exclude_payment else ""),
        ),
        Block("table", table=_edges_view(log, exclude_payment=exclude_payment)),
    ]


ACTIONS: dict[str, str] = {
    "F03": "Freeze price, quantity and date after release; route changes through an approval step.",
    "F04": "Require a requisition before an order can be created (system check or release rule).",
    "F05": "Block invoice posting until the goods receipt exists (three-way-match configuration).",
    "F06": "Tighten price tolerances and auto-block invoices outside them.",
    "F07": "Add a duplicate check on vendor, amount and reference before posting.",
    "F08": "Schedule payment runs against due dates and add an approval SLA.",
    "F09": "Delegate approval limits so high-value releases do not wait for one approver.",
    "F10": "Review lead times in vendor master data and run vendor scorecards.",
}


def executive_blocks(
    a: P2PAnalysis, findings: list[Finding], value: ValueCase | None = None
) -> list[Block]:
    """A one-page summary: headline, sized opportunity and actions to test."""
    by_id = {f.id: f for f in findings}
    happy = by_id["F02"].metrics["happy_path_pct"]
    median = by_id["F01"].metrics["median_days"]
    text = (
        f"{a.n_cases} purchase orders over {a.span_days} days. {happy}% follow the reference path "
        f"and the median cycle time is {median:.1f} days."
    )
    if value is not None:
        top = value.levers.sort_values("annual_problem_eur", ascending=False).iloc[0]
        text += (
            f" The largest sized opportunity is '{top['lever']}': about "
            f"{top['annual_problem_eur']:,.0f} EUR a year at {value.annual_cases:,.0f} orders a "
            f"year before any program ({top['base']:,.0f} EUR in the base scenario). These "
            "figures depend on editable assumptions."
        )
    actions = pd.DataFrame(
        {
            "finding": list(ACTIONS),
            "suggested action to test": list(ACTIONS.values()),
            "evidence": [by_id[i].text for i in ACTIONS],
        }
    )
    return [
        Block("h2", "Executive summary"),
        Block("p", text),
        Block(
            "p", "Actions below are hypotheses to test with the process owners, not conclusions."
        ),
        Block("table", table=actions),
    ]


def mapped_blocks(
    result: ConformanceResult, n_events: int, n_mapped: int, mandatory: tuple[str, ...]
) -> list[Block]:
    """Conformance results for a real log whose activities were mapped to P2P roles."""
    rules = pd.DataFrame(
        {
            "rule (earlier -> later)": list(result.violations),
            "violations": list(result.violations.values()),
        }
    )
    share = 100.0 * n_mapped / n_events if n_events else 0.0
    return [
        Block("h2", "P2P conformance on mapped activities"),
        Block(
            "p",
            f"{n_mapped} of {n_events} events ({share:.1f}%) matched the activity map. "
            f"{result.conforming_cases} of {result.n_cases} cases "
            f"({100.0 * result.conformance_rate:.1f}%) break no precedence rule and contain every "
            f"mandatory step ({', '.join(mandatory)}).",
        ),
        Block("table", table=rules),
    ]


def p2p_blocks(
    a: P2PAnalysis,
    findings: list[Finding],
    value: ValueCase | None = None,
    assumptions: Assumptions | None = None,
    chart_files: list[str] | None = None,
) -> list[Block]:
    """Blocks for the full procure-to-pay report."""
    blocks = log_blocks(a.log, "Procure-to-pay process intelligence report", exclude_payment=True)
    blocks[2:2] = [
        Block(
            "p",
            "Data note: results describe the dataset you supplied. If it was produced by "
            "`p2p-lens generate` it is synthetic and the numbers illustrate the method only.",
        ),
        *executive_blocks(a, findings, value),
    ]
    blocks.append(Block("h2", "Findings"))
    blocks.append(
        Block(
            "table",
            table=pd.DataFrame(
                {
                    "id": [f.id for f in findings],
                    "title": [f.title for f in findings],
                    "statement": [f.text for f in findings],
                }
            ),
        )
    )
    dev = pd.DataFrame(
        {
            "deviation": list(a.deviation_counts),
            "cases": list(a.deviation_counts.values()),
            "share_pct": [round(100.0 * v / a.n_cases, 1) for v in a.deviation_counts.values()],
        }
    )
    blocks += [Block("h2", "Deviations"), Block("table", table=dev)]
    blocks += [Block("h2", "Slowest vendors"), Block("table", table=a.vendors.head(5).round(2))]
    for name in chart_files or []:
        blocks.append(Block("img", name))
    if value is not None and assumptions is not None:
        blocks += [
            Block("h2", "Value model (assumption-driven)"),
            Block(
                "p",
                f"Scaled to {value.annual_cases:,.0f} purchase orders per year. Benefits are "
                "observed rates multiplied by the editable assumptions in "
                "`default_assumptions.yaml`; they are scenarios, not forecasts. Program cost "
                f"assumed: {assumptions.program_cost_eur:,.0f} EUR.",
            ),
            Block("table", table=value.levers.round(0)),
            Block("table", table=value.summary.round(1)),
        ]
    return blocks


def render_markdown(blocks: list[Block]) -> str:
    out: list[str] = []
    for b in blocks:
        if b.kind == "h1":
            out.append(f"# {b.text}\n")
        elif b.kind == "h2":
            out.append(f"\n## {b.text}\n")
        elif b.kind == "p":
            out.append(f"{b.text}\n")
        elif b.kind == "table" and b.table is not None:
            out.append(_md_table(b.table) + "\n")
        elif b.kind == "img":
            out.append(f"![{b.text}]({b.text})\n")
    return "\n".join(out)


def render_html(blocks: list[Block], base_dir: Path | None = None) -> str:
    """Render a self-contained HTML page; chart images are inlined as base64."""
    parts: list[str] = []
    for b in blocks:
        if b.kind == "h1":
            parts.append(f"<h1>{html.escape(b.text)}</h1>")
        elif b.kind == "h2":
            parts.append(f"<h2>{html.escape(b.text)}</h2>")
        elif b.kind == "p":
            parts.append(f"<p>{html.escape(b.text)}</p>")
        elif b.kind == "table" and b.table is not None:
            parts.append(_html_table(b.table))
        elif b.kind == "img":
            path = (base_dir or Path(".")) / b.text
            if path.exists():
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                parts.append(
                    f'<img alt="{html.escape(b.text)}" src="data:image/png;base64,{encoded}">'
                )
    style = (
        "body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;"
        "color:#1b1f24}table{border-collapse:collapse;margin:1rem 0;width:100%;font-size:.9rem}"
        "th,td{border:1px solid #d0d7de;padding:.35rem .6rem;text-align:left}"
        "th{background:#f6f8fa}img{max-width:100%}"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>p2p-lens report</title><style>{style}</style></head><body>"
        + "\n".join(parts)
        + "</body></html>"
    )


def write_charts(a: P2PAnalysis, out_dir: Path) -> list[str]:
    """Write PNG charts if matplotlib is installed; return the file names written."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    variants = _variants_view(a.log, 6).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.barh(variants["variant"], variants["share_pct"], color="#2f6fdb")
    ax.set_xlabel("share of cases (%)")
    ax.set_title("Top process variants")
    fig.tight_layout()
    fig.savefig(out_dir / "variants.png", dpi=130)
    plt.close(fig)
    written.append("variants.png")

    dev = pd.Series(a.deviation_counts) / a.n_cases * 100
    fig, ax = plt.subplots(figsize=(8, 3.6))
    dev.sort_values().plot.barh(ax=ax, color="#d1453b")
    ax.set_xlabel("share of purchase orders (%)")
    ax.set_title("Deviation rates")
    fig.tight_layout()
    fig.savefig(out_dir / "deviations.png", dpi=130)
    plt.close(fig)
    written.append("deviations.png")
    return written
