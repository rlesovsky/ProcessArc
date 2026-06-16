"""Data models for the Commissioning Workbook Builder.

Two main shapes:
  - ``ParsedSource``: what the parser extracts from the customer-supplied
    write-up workbook (the Graphics-and-Tables-style xlsx).
  - ``BuildReport``: returned to the frontend alongside the populated
    workbook bytes. Contains the change log (every cell touched, with
    before/after and reason) so the UI can render a review panel.

We keep these dataclass-flavoured pydantic models because the rest of
the backend already standardizes on pydantic v2 (see
backend.features.ignition_tags.schema).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FlowMeter(BaseModel):
    """A flow-meter entry from the source Chemical sheet."""
    chemical: str
    meter_description: str = ""
    k_factor: float | int | None = None
    make_model: str = ""


class SequenceNote(BaseModel):
    """A free-text note keyed to a sequence step (used for the
    sequence-narrative → COMMENTS mapping)."""
    cylinder: int | None = None      # 1 / 2 for Cyl1/Cyl2; None for shared
    step_name: str                    # e.g. "Initial Vacuum", "Fill", "Empty"
    notes: list[str] = Field(default_factory=list)


class PlantInfo(BaseModel):
    """Loose plant-level facts pulled from the source's Plant Info / Operators /
    Tank Info sheets. Most plants will populate only a subset."""
    plant_facts: list[str] = Field(default_factory=list)
    operator_names: list[str] = Field(default_factory=list)
    tank_notes: list[str] = Field(default_factory=list)


class GraphicNote(BaseModel):
    """A note that comes off a *Graphic* sheet (Cyl1 Treat, Cyl2 Treat, Mix).
    These are usually deviations from the canonical graphic
    ('Tank 6 is not a color work tank', etc.) — useful as COMMENTS on
    the relevant sign-off section."""
    section: str        # 'Cylinder 1' / 'Cylinder 2' / 'Mix'
    notes: list[str] = Field(default_factory=list)


class ParsedSource(BaseModel):
    """The full extracted shape of a customer write-up workbook."""
    flow_meters: list[FlowMeter] = Field(default_factory=list)
    sequence_notes: list[SequenceNote] = Field(default_factory=list)
    graphic_notes: list[GraphicNote] = Field(default_factory=list)
    plant_info: PlantInfo = Field(default_factory=PlantInfo)
    # Any sheets we encountered but didn't recognize — surfaced as
    # warnings so the user can see what we ignored.
    unknown_sheets: list[str] = Field(default_factory=list)


class ChangeLogEntry(BaseModel):
    """One cell touch. `conflict=True` means we found existing content
    and refused to overwrite — the new value is reported but not
    written."""
    sheet: str
    cell: str
    before: str = ""
    after: str = ""
    reason: str = ""
    conflict: bool = False


class BuildReport(BaseModel):
    """Returned alongside the populated xlsx bytes."""
    template_name: str
    source_sheets_seen: list[str] = Field(default_factory=list)
    changes: list[ChangeLogEntry] = Field(default_factory=list)
    flow_meters_matched: int = 0
    sequence_notes_attached: int = 0
    graphic_notes_attached: int = 0
    plant_facts_attached: int = 0
    warnings: list[str] = Field(default_factory=list)

    def conflict_count(self) -> int:
        return sum(1 for c in self.changes if c.conflict)

    def to_text_log(self) -> str:
        """Plain-text rendering used by the UI download button."""
        lines = [
            f"Template: {self.template_name}",
            f"Source sheets seen: {', '.join(self.source_sheets_seen) or '(none)'}",
            f"Cells touched: {len(self.changes)}",
            f"Conflicts (not overwritten): {self.conflict_count()}",
            f"Flow meters matched: {self.flow_meters_matched}",
            f"Sequence notes attached: {self.sequence_notes_attached}",
            f"Graphic notes attached: {self.graphic_notes_attached}",
            f"Plant facts attached: {self.plant_facts_attached}",
            "",
            "Sheet | Cell | Before | After | Reason",
            "-" * 72,
        ]
        for c in self.changes:
            tag = " [CONFLICT]" if c.conflict else ""
            lines.append(
                f"{c.sheet!r} | {c.cell} | {c.before!r} | {c.after!r} | {c.reason}{tag}"
            )
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)


def _coerce_str(v: Any) -> str:
    """Safe stringification — None → '', preserves trimmed content."""
    if v is None:
        return ""
    return str(v).strip()
