# Running on a real public event log

`analyze-log` reads IEEE XES (`.xes`, `.xes.gz`) and flat CSV files. XES parsing uses `defusedxml`,
so a hostile file cannot trigger entity-expansion attacks (covered by a test).

## Worked example

The pm4py project ships a real-world log in its test data (activity names match the receipt-phase
log of an environmental-permit process from the CoSeLoG project, as distributed on 4TU.ResearchData).
It is **not** bundled here because redistribution terms should be checked at the source.

```bash
curl -L -o receipt.xes \
  https://raw.githubusercontent.com/pm4py/pm4py-core/release/tests/input_data/receipt.xes
p2p-lens analyze-log --log receipt.xes --out receipt-report
```

Result when run on 2026-11-22: 1,434 cases and 8,577 events. Median case duration is under one
hour, p90 is 14.1 days, the longest case is 275.8 days, and the reference sequence covers 49.7%
of cases. The largest waiting-time contributor is the step from "T05 Print and send confirmation of
receipt" to "T06 Determine necessity of stop advice" (mean 3.1 days, p90 8.0 days).

This is a general process-mining run. The SAP-specific deviation detectors and value model need the
purchasing tables (see data-model.md), so they are not part of `analyze-log`.

## Running the P2P checks on a real log

Real logs name their activities differently. Copy `examples/p2p-map.example.yaml`, list your log's
activity names under each role, and run:

```bash
p2p-lens analyze-log --log yourlog.xes --p2p-map map.yaml --out out
```

The report gains a section with precedence violations (for example invoice before goods receipt) and
a conformance rate over the mapped events. The mechanism is tested by renaming the activities of a
synthetic log and recovering the injected invoice-before-goods-receipt count exactly. Item-level logs
treat each item as a case, so read the rates accordingly.

## BPI Challenge logs

BPI Challenge event logs (for example the 2019 purchase-order log) are distributed as XES on
4TU.ResearchData. Download one there, accept its licence, and pass the file to `analyze-log`.
That specific log has not been run through this tool yet.

## CSV logs

```bash
p2p-lens analyze-log --log my.csv --case-col case --activity-col act --timestamp-col ts --out out
```
