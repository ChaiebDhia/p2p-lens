"""SAP-style table schema, activity names, the Dataset container and validation.

The tables are a simplified view of the real SAP purchasing tables (EKKO, EKPO,
EKBE, EBAN) plus two helper tables that, in a real system, are derived from
change documents (CDHDR/CDPOS) and FI clearing (BSAK). See docs/data-model.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ACT_PR = "Create Purchase Requisition"
ACT_PO = "Create Purchase Order"
ACT_REL = "Release Purchase Order"
ACT_CHG = "Change Purchase Order"
ACT_GR = "Post Goods Receipt"
ACT_IR = "Post Invoice Receipt"
ACT_PAY = "Clear Invoice (Payment)"

ACTIVITY_ORDER: tuple[str, ...] = (ACT_PR, ACT_PO, ACT_REL, ACT_CHG, ACT_GR, ACT_IR, ACT_PAY)
HAPPY_PATH: tuple[str, ...] = (ACT_PR, ACT_PO, ACT_REL, ACT_GR, ACT_IR, ACT_PAY)
MANDATORY: tuple[str, ...] = (ACT_PO, ACT_REL, ACT_GR, ACT_IR, ACT_PAY)

TABLE_COLUMNS: dict[str, list[str]] = {
    "EKKO": ["EBELN", "LIFNR", "BEDAT", "ERNAM", "BSART", "REL_DATE", "ZBD1T", "WAERS"],
    "EKPO": ["EBELN", "EBELP", "MATNR", "MENGE", "NETWR"],
    "EKBE": ["EBELN", "BELNR", "VGABE", "BUDAT", "DMBTR"],
    "EBAN": ["BANFN", "EBELN", "BADAT", "ERNAM"],
    "PO_CHANGES": ["EBELN", "UDATE", "FNAME", "USERNAME"],
    "PAYMENTS": ["EBELN", "AUGDT", "DMBTR"],
}
DATE_COLUMNS: dict[str, list[str]] = {
    "EKKO": ["BEDAT", "REL_DATE"],
    "EKBE": ["BUDAT"],
    "EBAN": ["BADAT"],
    "PO_CHANGES": ["UDATE"],
    "PAYMENTS": ["AUGDT"],
}
STRING_COLUMNS = {"EBELN", "EBELP", "LIFNR", "ERNAM", "BSART", "MATNR", "BELNR", "VGABE", "BANFN"}
STRING_COLUMNS |= {"FNAME", "USERNAME", "WAERS"}

LOG_COLUMNS = ["case_id", "activity", "timestamp", "resource"]


class SchemaError(ValueError):
    """Raised when input tables do not match the expected schema."""


@dataclass
class Dataset:
    """The six SAP-style tables that make up one extract."""

    ekko: pd.DataFrame
    ekpo: pd.DataFrame
    ekbe: pd.DataFrame
    eban: pd.DataFrame
    po_changes: pd.DataFrame
    payments: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "EKKO": self.ekko,
            "EKPO": self.ekpo,
            "EKBE": self.ekbe,
            "EBAN": self.eban,
            "PO_CHANGES": self.po_changes,
            "PAYMENTS": self.payments,
        }

    def validate(self) -> None:
        """Raise SchemaError if the tables are not internally consistent."""
        for name, frame in self.tables().items():
            missing = [c for c in TABLE_COLUMNS[name] if c not in frame.columns]
            if missing:
                raise SchemaError(f"{name} is missing columns: {missing}")
            for col in DATE_COLUMNS.get(name, []):
                if not pd.api.types.is_datetime64_any_dtype(frame[col]):
                    raise SchemaError(f"{name}.{col} must be a datetime column")
        if self.ekko["EBELN"].duplicated().any():
            raise SchemaError("EKKO.EBELN must be unique")
        known = set(self.ekko["EBELN"])
        for name in ("EKPO", "EKBE", "EBAN", "PO_CHANGES", "PAYMENTS"):
            orphans = set(self.tables()[name]["EBELN"]) - known
            if orphans:
                raise SchemaError(f"{name} has {len(orphans)} EBELN values not present in EKKO")
        bad = set(self.ekbe["VGABE"]) - {"1", "2"}
        if bad:
            raise SchemaError(f"EKBE.VGABE must be '1' (goods receipt) or '2' (invoice): {bad}")
        if (self.ekko["ZBD1T"] <= 0).any():
            raise SchemaError("EKKO.ZBD1T (payment term days) must be positive")

    def save(self, directory: str | Path) -> None:
        """Write each table to <directory>/<table>.csv."""
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        for name, frame in self.tables().items():
            frame.to_csv(out / f"{name.lower()}.csv", index=False)

    @classmethod
    def load(cls, directory: str | Path) -> Dataset:
        """Read the six CSV files written by :meth:`save` and validate them."""
        src = Path(directory)
        frames: dict[str, pd.DataFrame] = {}
        for name, columns in TABLE_COLUMNS.items():
            path = src / f"{name.lower()}.csv"
            if not path.exists():
                raise SchemaError(f"missing file: {path}")
            dtypes = {c: "string" for c in columns if c in STRING_COLUMNS}
            frame = pd.read_csv(path, dtype=dtypes)
            for col in DATE_COLUMNS.get(name, []):
                if col in frame.columns:
                    frame[col] = pd.to_datetime(frame[col])
            frames[name] = frame
        ds = cls(
            ekko=frames["EKKO"],
            ekpo=frames["EKPO"],
            ekbe=frames["EKBE"],
            eban=frames["EBAN"],
            po_changes=frames["PO_CHANGES"],
            payments=frames["PAYMENTS"],
        )
        ds.validate()
        return ds
