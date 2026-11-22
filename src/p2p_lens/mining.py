"""Log-only process mining: variants, durations, and directly-follows bottlenecks."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

SECONDS_PER_DAY = 86_400.0


@dataclass
class LogAnalysis:
    """Results that need nothing but an event log."""

    n_cases: int
    n_events: int
    variants: pd.DataFrame
    edges: pd.DataFrame
    durations: pd.Series
    throughput: dict[str, float]


def _require_log(log: pd.DataFrame) -> None:
    for col in ("case_id", "activity", "timestamp"):
        if col not in log.columns:
            raise ValueError(f"event log is missing column '{col}'")
    if log.empty:
        raise ValueError("event log is empty")


def variant_table(log: pd.DataFrame) -> pd.DataFrame:
    """Distinct activity sequences with case counts, share and cumulative share."""
    _require_log(log)
    traces = log.groupby("case_id", sort=False)["activity"].agg(" > ".join)
    counts = traces.value_counts()
    table = counts.rename_axis("variant").reset_index(name="cases")
    table["share"] = table["cases"] / table["cases"].sum()
    table["cum_share"] = table["share"].cumsum()
    return table


def case_durations(log: pd.DataFrame) -> pd.Series:
    """Elapsed days between the first and last event of each case."""
    _require_log(log)
    grouped = log.groupby("case_id", sort=False)["timestamp"]
    return (grouped.max() - grouped.min()).dt.total_seconds() / SECONDS_PER_DAY


def edge_table(log: pd.DataFrame) -> pd.DataFrame:
    """Waiting time for every directly-follows pair, ranked by total waiting time."""
    _require_log(log)
    grouped = log.groupby("case_id", sort=False)
    nxt_activity = grouped["activity"].shift(-1)
    nxt_time = grouped["timestamp"].shift(-1)
    mask = nxt_activity.notna()
    pairs = pd.DataFrame(
        {
            "src": log.loc[mask, "activity"],
            "dst": nxt_activity[mask],
            "days": (nxt_time[mask] - log.loc[mask, "timestamp"]).dt.total_seconds()
            / SECONDS_PER_DAY,
        }
    )
    if pairs.empty:
        return pd.DataFrame(
            columns=["src", "dst", "count", "mean_days", "median_days", "p90_days", "total_days"]
        )
    stats = pairs.groupby(["src", "dst"])["days"].agg(
        count="count",
        mean_days="mean",
        median_days="median",
        p90_days=lambda s: float(s.quantile(0.9)),
        total_days="sum",
    )
    return stats.reset_index().sort_values("total_days", ascending=False).reset_index(drop=True)


def throughput_summary(durations: pd.Series) -> dict[str, float]:
    """Mean, median, p90 and max case duration in days."""
    return {
        "mean_days": float(durations.mean()),
        "median_days": float(durations.median()),
        "p90_days": float(durations.quantile(0.9)),
        "max_days": float(durations.max()),
    }


def analyze_log(log: pd.DataFrame) -> LogAnalysis:
    """Run every log-only analysis."""
    _require_log(log)
    durations = case_durations(log)
    return LogAnalysis(
        n_cases=int(log["case_id"].nunique()),
        n_events=len(log),
        variants=variant_table(log),
        edges=edge_table(log),
        durations=durations,
        throughput=throughput_summary(durations),
    )
