"""Command-line interface: generate, analyze, analyze-log, ask, demo."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from p2p_lens import __version__
from p2p_lens.analysis import P2PAnalysis, analyze
from p2p_lens.conformance import check_precedence, load_activity_map, remap_log
from p2p_lens.copilot import (
    Backend,
    BackendError,
    OllamaBackend,
    OpenAICompatBackend,
    ask,
)
from p2p_lens.eventlog import build_event_log, load_log
from p2p_lens.export import export_tables
from p2p_lens.findings import Finding, build_findings
from p2p_lens.mining import analyze_log
from p2p_lens.report import (
    log_blocks,
    mapped_blocks,
    p2p_blocks,
    render_html,
    render_markdown,
    write_charts,
)
from p2p_lens.schema import Dataset, SchemaError
from p2p_lens.synth import generate
from p2p_lens.value import compute_value, load_assumptions

log = logging.getLogger("p2p_lens")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="p2p-lens", description=__doc__)
    p.add_argument("--version", action="version", version=f"p2p-lens {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="show progress messages")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="write a synthetic SAP-style dataset")
    g.add_argument("--cases", type=int, default=2000)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--out", type=Path, required=True)

    a = sub.add_parser("analyze", help="analyse a dataset and write the report")
    a.add_argument("--data", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--assumptions", type=Path, default=None)
    a.add_argument("--annual-cases", type=float, default=None)

    lg = sub.add_parser("analyze-log", help="analyse any event log (XES, XES.gz or CSV)")
    lg.add_argument("--log", type=Path, required=True)
    lg.add_argument("--case-col", default=None, help="CSV only")
    lg.add_argument("--activity-col", default=None, help="CSV only")
    lg.add_argument("--timestamp-col", default=None, help="CSV only")
    lg.add_argument("--resource-col", default=None)
    lg.add_argument("--sep", default=",")
    lg.add_argument(
        "--p2p-map",
        type=Path,
        default=None,
        help="YAML mapping of P2P roles to this log's activity names (adds conformance checks)",
    )
    lg.add_argument("--out", type=Path, required=True)

    ex = sub.add_parser(
        "export", help="write activities.csv and cases.csv for a process-mining tool"
    )
    ex.add_argument("--data", type=Path, required=True)
    ex.add_argument("--out", type=Path, required=True)

    q = sub.add_parser("ask", help="ask a question answered from the findings")
    q.add_argument("--data", type=Path, required=True)
    q.add_argument("--backend", choices=["extractive", "ollama", "openai"], default="extractive")
    q.add_argument("--model", default=None)
    q.add_argument("question")

    d = sub.add_parser("demo", help="generate data and write a full report in one step")
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("--cases", type=int, default=2000)
    d.add_argument("--seed", type=int, default=42)
    return p


def _write_report(out: Path, blocks_md: str, blocks_html: str) -> None:
    (out / "report.md").write_text(blocks_md, encoding="utf-8")
    (out / "report.html").write_text(blocks_html, encoding="utf-8")


def _analyze_dataset(
    data: Path, out: Path, assumptions: Path | None, annual_cases: float | None
) -> tuple[P2PAnalysis, list[Finding]]:
    log.info("loading dataset from %s", data)
    ds = Dataset.load(data)
    result = analyze(ds)
    findings = build_findings(result)
    log.info("analysed %d cases", result.n_cases)
    assume = load_assumptions(assumptions)
    value = compute_value(result, assume, annual_cases)
    out.mkdir(parents=True, exist_ok=True)
    charts = write_charts(result, out)
    blocks = p2p_blocks(result, findings, value, assume, charts)
    _write_report(out, render_markdown(blocks), render_html(blocks, out))
    (out / "findings.json").write_text(
        json.dumps([f.model_dump() for f in findings], indent=2), encoding="utf-8"
    )
    return result, findings


def _backend(kind: str, model: str | None) -> Backend | None:
    if kind == "extractive":
        return None
    if kind == "ollama":
        return OllamaBackend(model=model or "llama3.2")
    backend = OpenAICompatBackend.from_env()
    if model:
        backend.model = model
    return backend


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        if args.command == "generate":
            ds, truth = generate(args.cases, args.seed)
            ds.save(args.out)
            (args.out / "ground_truth.json").write_text(
                json.dumps(truth.__dict__, indent=2), encoding="utf-8"
            )
            print(f"wrote {truth.n_cases} purchase orders to {args.out}")
        elif args.command == "analyze":
            result, findings = _analyze_dataset(
                args.data, args.out, args.assumptions, args.annual_cases
            )
            print(f"analysed {result.n_cases} cases, {len(findings)} findings -> {args.out}")
        elif args.command == "analyze-log":
            event_log = load_log(
                args.log,
                args.case_col,
                args.activity_col,
                args.timestamp_col,
                args.resource_col,
                args.sep,
            )
            blocks = log_blocks(analyze_log(event_log))
            if args.p2p_map:
                amap = load_activity_map(args.p2p_map)
                remapped = remap_log(event_log, amap)
                blocks += mapped_blocks(
                    check_precedence(remapped, amap.mandatory),
                    len(event_log),
                    len(remapped),
                    amap.mandatory,
                )
            args.out.mkdir(parents=True, exist_ok=True)
            _write_report(args.out, render_markdown(blocks), render_html(blocks))
            print(f"analysed {event_log['case_id'].nunique()} cases -> {args.out}")
        elif args.command == "export":
            ds = Dataset.load(args.data)
            paths = export_tables(ds, args.out)
            print("wrote " + ", ".join(str(p) for p in paths))
            log.info("event log rows: %d", len(build_event_log(ds)))
        elif args.command == "ask":
            result = analyze(Dataset.load(args.data))
            answer = ask(args.question, build_findings(result), _backend(args.backend, args.model))
            print(answer.text)
            if answer.fell_back:
                print(f"\n(fell back to extractive answer: {answer.reason})", file=sys.stderr)
        elif args.command == "demo":
            ds, truth = generate(args.cases, args.seed)
            ds.save(args.out / "data")
            result, findings = _analyze_dataset(args.out / "data", args.out / "report", None, None)
            print(f"demo complete: {truth.n_cases} cases, {len(findings)} findings in {args.out}")
    except (SchemaError, BackendError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
