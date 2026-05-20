"""Table Extractor (Plan §9.2 Step E).

Reads the Chemical and Tank sheet directly — no Claude API call. Produces:
  - the work tank inventory  -> list[TankRecord]
  - the flow meter table     -> list of meter dicts
  - the chemical info table  -> dict keyed by chemical name (for descriptions)
  - the cylinder void table  -> dict keyed by cylinder number (active set)

The sheet stacks several tables vertically. We locate each by its header row
rather than by absolute coordinates, because the layout drifts between plants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from backend.ingest import IngestedWorkbook, SheetKind
from backend.model.plant import TankRecord


# ---- header signatures we look for on the Chemical & Tank sheet --------------
_TANK_INV_HEADERS = {"#", "tank name", "preservative", "cylinder used"}
_FLOW_METER_HEADERS = {"chem", "meter description", "k-factor"}
_CHEMICAL_HEADERS = {"chemical", "billed by", "cost", "lbs/gal"}
_CYL_VOID_HEADERS = {"cylinder", "void gallons"}
# Hampton has a "Cylinder Status" column on the void table; Fairless Hills does not.
_CYL_STATUS_TOKENS = {"cylinder status", "status"}


@dataclass
class TableExtraction:
    tanks: list[TankRecord] = field(default_factory=list)
    flow_meters: list[dict] = field(default_factory=list)
    chemicals: dict[str, dict] = field(default_factory=dict)
    cylinder_voids: dict[int, dict] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _norm(v) -> str:
    if v is None:
        return ""
    return str(v).strip().lower()


def _looks_like_header(row: tuple, required: set[str]) -> Optional[dict[str, int]]:
    """If `row` contains all `required` headers (case-insensitive substring),
    return a dict mapping the lowered header text -> column index.
    """
    cells = [_norm(c) for c in row]
    found_cols: dict[str, int] = {}
    for needle in required:
        for idx, txt in enumerate(cells):
            if needle in txt:
                found_cols[needle] = idx
                break
        else:
            return None
    # Also capture every non-empty cell as a column name -> idx for downstream use
    full: dict[str, int] = {}
    for idx, txt in enumerate(cells):
        if txt:
            full[txt] = idx
    return full


def _to_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None


def _to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _extract_tank_inventory(rows: list[tuple], header_idx: int, cols: dict[str, int]) -> list[TankRecord]:
    out: list[TankRecord] = []

    def col(*candidates: str) -> Optional[int]:
        for c in candidates:
            if c in cols:
                return cols[c]
        for c in candidates:
            for k, v in cols.items():
                if c in k:
                    return v
        return None

    c_num = col("#")
    c_name = col("tank name")
    c_pres = col("preservative")
    c_add = col("additives")
    c_dia = col("diameter (in)", "diameter")
    c_len = col("height (in)", "length (in)", "height", "length")
    c_cyl = col("cylinder used")
    c_min = col("min")
    c_max = col("max")
    c_target = col("target")

    for r_idx in range(header_idx + 1, len(rows)):
        row = rows[r_idx]
        if not row:
            continue
        num_val = row[c_num] if c_num is not None and c_num < len(row) else None
        n = _to_int(num_val)
        if n is None:
            # blank line ends the table
            if not any(c is not None and str(c).strip() for c in row):
                break
            # row with text but no number — likely a new section header — stop
            continue

        def get(idx):
            return row[idx] if idx is not None and idx < len(row) else None

        chem = (get(c_pres) or "").__str__().strip() if get(c_pres) is not None else ""
        name_cell = get(c_name)
        # "Tank Name" column may be a number (matches #) or a text label like "MCA Conc"
        tank_id = str(name_cell).strip() if name_cell not in (None, "") else str(n)

        is_idle = "idle" in chem.lower() or "idle" in tank_id.lower()

        tr = TankRecord(
            tank_id=tank_id,
            chemical=chem,
            cylinder_used=_to_int(get(c_cyl)),
            is_idle=is_idle,
            diameter_in=_to_float(get(c_dia)),
            length_in=_to_float(get(c_len)),
            min_volume=_to_float(get(c_min)),
            max_volume=_to_float(get(c_max)),
            target_volume=_to_float(get(c_target)),
            source_row=r_idx + 1,
            raw={
                "number": n,
                "additives": (get(c_add) or "") if get(c_add) is not None else "",
            },
        )
        out.append(tr)

    return out


def _extract_simple_block(rows: list[tuple], header_idx: int, cols: dict[str, int], key_col_name: str) -> list[dict]:
    """Generic block extractor: read every following row until a fully blank row,
    keyed by the first non-empty column. Returns each row as {col_name: value}.
    """
    out: list[dict] = []
    key_idx = cols.get(key_col_name)
    if key_idx is None:
        for k, v in cols.items():
            if key_col_name in k:
                key_idx = v
                break
    for r_idx in range(header_idx + 1, len(rows)):
        row = rows[r_idx]
        if not row or not any(c is not None and str(c).strip() for c in row):
            break
        key_val = row[key_idx] if key_idx is not None and key_idx < len(row) else None
        if key_val is None or str(key_val).strip() == "":
            # row exists but key column empty -> end of block
            break
        rec: dict = {}
        for cname, cidx in cols.items():
            rec[cname] = row[cidx] if cidx < len(row) else None
        out.append(rec)
    return out


def extract_tables(wb: IngestedWorkbook) -> TableExtraction:
    out = TableExtraction()
    sheet = wb.find(SheetKind.CHEMICAL_AND_TANK)
    if sheet is None:
        out.warnings.append("Chemical and Tank sheet not found — table extraction skipped.")
        return out

    rows = sheet.rows
    for i, row in enumerate(rows):
        cols = _looks_like_header(row, _TANK_INV_HEADERS)
        if cols is not None:
            out.tanks = _extract_tank_inventory(rows, i, cols)
            continue
        cols = _looks_like_header(row, _FLOW_METER_HEADERS)
        if cols is not None:
            out.flow_meters = _extract_simple_block(rows, i, cols, "chem")
            continue
        cols = _looks_like_header(row, _CHEMICAL_HEADERS)
        if cols is not None:
            for rec in _extract_simple_block(rows, i, cols, "chemical"):
                chem = str(rec.get("chemical", "")).strip()
                if chem:
                    out.chemicals[chem] = rec
            continue
        cols = _looks_like_header(row, _CYL_VOID_HEADERS)
        if cols is not None:
            for rec in _extract_simple_block(rows, i, cols, "cylinder"):
                cyl_n = _to_int(rec.get("cylinder"))
                if cyl_n is not None:
                    out.cylinder_voids[cyl_n] = rec

    if not out.tanks:
        out.warnings.append("Tank inventory header not found on Chemical and Tank sheet.")

    return out
