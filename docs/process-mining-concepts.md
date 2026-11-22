# Concept map: p2p-lens and commercial process-mining platforms

Commercial platforms and this project share the same ideas. This table is a conceptual map written
from public documentation of common process-mining terms, not a statement about any vendor's exact
feature set or syntax.

| Concept | In p2p-lens |
|---|---|
| Event log (case, activity, timestamp) | `eventlog.build_event_log` |
| Variant explorer | `mining.variant_table` |
| Throughput time | `mining.case_durations`, finding F01 |
| Bottleneck between steps | `mining.edge_table`, finding F09 |
| Conformance checking | `conformance.check_precedence`, `detect_deviations` |
| Automation or touchless rate | Share of cases on the reference path, finding F02 |
| Value realisation | `value.compute_value` with explicit assumptions |
| Data model from source tables | `schema.Dataset` and docs/data-model.md |
| Data ingestion (activity table + case table) | `export.export_tables` (`p2p-lens export`) |
| Mapping a source system's activities to a reference process | `conformance.load_activity_map` (`--p2p-map`) |
| Business case / opportunity sizing | Executive summary in the report, `value.compute_value` |
