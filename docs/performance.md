# Performance

Measured with `python benchmarks/benchmark.py 10000 50000 100000` on a single run in a Linux
sandbox (Python 3.12, pandas 3.1). Your numbers will differ; the shape (linear scaling) is the point.

| Cases | Events | Generate | Analyze | Findings | Detection equals ground truth | Peak memory |
|---|---|---|---|---|---|---|
| 10,000 | 61,378 | 1.5 s | 0.4 s | 0.002 s | yes | 123 MB |
| 50,000 | 307,294 | 9.9 s | 1.9 s | 0.002 s | yes | 308 MB |
| 100,000 | 614,690 | 19.7 s | 4.3 s | 0.002 s | yes | 580 MB |

Peak memory includes the generator and all tables held in memory. Analysis is vectorised pandas
(group-bys and shifts), so it scales roughly linearly with the number of events.

## Limits

- Everything is in memory. Logs of tens of millions of events need chunking or a database, which is
  out of scope.
- The generator is a Python loop and is meant for tests and demos, not for load testing.
