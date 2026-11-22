"""Measure generation and analysis time and peak memory at several sizes.

Usage: python benchmarks/benchmark.py 10000 50000 100000
"""

from __future__ import annotations

import resource
import sys
import time

from p2p_lens.analysis import analyze
from p2p_lens.findings import build_findings
from p2p_lens.synth import generate


def main(sizes: list[int]) -> None:
    print("cases | events | generate s | analyze s | findings s | exact ground truth | peak MB")
    for n in sizes:
        t0 = time.perf_counter()
        ds, truth = generate(n, seed=1)
        t1 = time.perf_counter()
        result = analyze(ds)
        t2 = time.perf_counter()
        build_findings(result)
        t3 = time.perf_counter()
        exact = all(
            result.deviation_counts[k] == getattr(truth, k) for k in result.deviation_counts
        )
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        print(
            f"{n} | {result.log.n_events} | {t1 - t0:.1f} | {t2 - t1:.1f} | {t3 - t2:.3f} "
            f"| {exact} | {peak:.0f}"
        )


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [10_000, 50_000, 100_000])
