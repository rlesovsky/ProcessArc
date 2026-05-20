"""Plant Configuration Discovery (Plan §6A).

Reads the workbook's sheet list AND the Chemical & Tank tables to build the
project-specific PlantConfiguration. Nothing here may assume "two cylinders" or
"cylinders numbered 1, 2." All facts come from the file.
"""

from __future__ import annotations

import re
from typing import Optional

from backend.extract import extract_tables, TableExtraction
from backend.ingest import IngestedWorkbook, SheetKind
from backend.model.plant import (
    CylinderSystem,
    MixSystem,
    PlantConfiguration,
)


_SITE_FROM_FILENAME = re.compile(r"^([A-Za-z][A-Za-z ]+?)(?:\s+graphics?|\s+and|_)", re.IGNORECASE)


def _guess_site_name(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    m = _SITE_FROM_FILENAME.match(stem)
    if m:
        return m.group(1).strip().title()
    # fallback: take leading word chunks split by underscore/space
    parts = re.split(r"[_\s]+", stem)
    return " ".join(parts[:2]).title() if parts else stem


def _discover_cylinders(wb: IngestedWorkbook, tables: TableExtraction) -> tuple[list[CylinderSystem], list[str]]:
    warnings: list[str] = []
    by_number: dict[int, CylinderSystem] = {}

    # Sequence sheets -> active cylinders (numbered)
    for s in wb.by_kind(SheetKind.CYLINDER_SEQUENCE):
        n = s.cylinder_number
        if n is None:
            warnings.append(f"Cylinder sequence sheet '{s.name}' has no extractable cylinder number.")
            continue
        by_number[n] = CylinderSystem(
            number=n,
            name=f"Cylinder {n}",
            sequence_sheet=s.name,
            is_idle=False,
        )

    # Cross-check the Cylinder Void table for cylinders without a sequence sheet
    # (Hampton's Cylinder 2 has no sequence but appears in the void/status table.)
    for n, rec in tables.cylinder_voids.items():
        status_text = ""
        for k, v in rec.items():
            if "status" in k and v is not None:
                status_text = str(v).strip()
                break
        if n not in by_number:
            is_idle = bool(status_text) and "idle" in status_text.lower()
            by_number[n] = CylinderSystem(
                number=n,
                name=f"Cylinder {n}",
                sequence_sheet=None,
                is_idle=is_idle or not status_text == "Active",
                status_note=status_text or "Present in Chemical and Tank but no sequence sheet — assumed idle.",
            )
        else:
            # Cylinder has both a sequence sheet AND status data — keep the sequence,
            # but mark idle if the status column explicitly says so.
            if status_text and "idle" in status_text.lower():
                by_number[n].is_idle = True
                by_number[n].status_note = status_text

    cylinders = sorted(by_number.values(), key=lambda c: c.number)
    if not cylinders:
        warnings.append("No cylinders discovered — neither sequence sheets nor void table identified any.")
    return cylinders, warnings


def _discover_mix_systems(wb: IngestedWorkbook) -> tuple[list[MixSystem], list[str]]:
    warnings: list[str] = []
    out: list[MixSystem] = []

    mix_sheets = wb.by_kind(SheetKind.MIX_SEQUENCE)
    for i, s in enumerate(mix_sheets, start=1):
        label = s.mix_label or ""
        # Labelled mix systems get the label as their "name" (ECO, MCA, etc.)
        # Unified single-system plants (Hampton) tend to have no label.
        if label:
            name = f"{label.upper()} Mix"
            chemistry = label.upper()
        else:
            name = "Mix" if len(mix_sheets) == 1 else f"Mix {i}"
            chemistry = "Unified" if len(mix_sheets) == 1 else ""
        out.append(
            MixSystem(
                number=i,
                name=name,
                sequence_sheet=s.name,
                chemistry=chemistry,
            )
        )

    if not out:
        warnings.append("No mix sequencing sheets discovered.")
    return out, warnings


def discover_plant_configuration(wb: IngestedWorkbook) -> PlantConfiguration:
    tables = extract_tables(wb)

    cylinders, w1 = _discover_cylinders(wb, tables)
    mix_systems, w2 = _discover_mix_systems(wb)

    seq_sheets = [s.name for s in wb.sheets if s.kind in (SheetKind.CYLINDER_SEQUENCE, SheetKind.MIX_SEQUENCE)]

    pc = PlantConfiguration(
        site_name=_guess_site_name(wb.filename),
        workbook_filename=wb.filename,
        cylinders=cylinders,
        mix_systems=mix_systems,
        tanks=tables.tanks,
        sequence_sheets=seq_sheets,
        all_sheets=[s.name for s in wb.sheets],
        warnings=[*w1, *w2, *tables.warnings],
    )
    return pc
