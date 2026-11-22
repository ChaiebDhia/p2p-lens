# Data model

Six tables, CSV on disk, one row per record. Field names follow SAP where a standard field exists.
This is a **simplified** view, not a full SAP schema.

| Table | Key fields | Notes |
|---|---|---|
| `EKKO` (PO header) | `EBELN`, `LIFNR`, `BEDAT`, `ERNAM`, `BSART`, `REL_DATE`, `ZBD1T`, `WAERS` | `REL_DATE` is the release date; in a real system derive it from release-strategy change documents. `ZBD1T` is payment-term days. |
| `EKPO` (PO items) | `EBELN`, `EBELP`, `MATNR`, `MENGE`, `NETWR` | Order value is the sum of `NETWR` per `EBELN`. |
| `EKBE` (PO history) | `EBELN`, `BELNR`, `VGABE`, `BUDAT`, `DMBTR` | `VGABE` `1` is goods receipt, `2` is invoice receipt. |
| `EBAN` (requisitions) | `BANFN`, `EBELN`, `BADAT`, `ERNAM` | A PO with no `EBAN` row has no requisition. |
| `PO_CHANGES` | `EBELN`, `UDATE`, `FNAME`, `USERNAME` | In SAP, derive from `CDHDR`/`CDPOS` for object class `EINKBELEG`. |
| `PAYMENTS` | `EBELN`, `AUGDT`, `DMBTR` | In SAP, derive from FI clearing (for example `BSAK`) joined to the PO. |

All date columns are timestamps. `EBELN` is unique in `EKKO` and every other table must reference it.
`Dataset.validate()` enforces this and the `VGABE` and `ZBD1T` constraints.

## Event log

| Activity | Source |
|---|---|
| Create Purchase Requisition | `EBAN.BADAT` |
| Create Purchase Order | `EKKO.BEDAT` |
| Release Purchase Order | `EKKO.REL_DATE` |
| Change Purchase Order | `PO_CHANGES.UDATE` |
| Post Goods Receipt | `EKBE.BUDAT` where `VGABE = 1` |
| Post Invoice Receipt | `EKBE.BUDAT` where `VGABE = 2` |
| Clear Invoice (Payment) | `PAYMENTS.AUGDT` |

Columns: `case_id`, `activity`, `timestamp`, `resource`. Ties on identical timestamps are broken by
the canonical activity order.

## Using real extracts

Export the tables to CSV with the column names above and the same file names in lower case
(`ekko.csv`, `ekpo.csv`, `ekbe.csv`, `eban.csv`, `po_changes.csv`, `payments.csv`). Dates must parse
with `pandas.to_datetime`. Keep the key columns as text so leading zeros survive.
