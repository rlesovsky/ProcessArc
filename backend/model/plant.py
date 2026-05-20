from typing import Optional

from pydantic import BaseModel, Field


class CylinderSystem(BaseModel):
    number: int
    name: str
    sequence_sheet: Optional[str] = None
    is_idle: bool = False
    status_note: str = ""


class MixSystem(BaseModel):
    number: int
    name: str
    sequence_sheet: Optional[str] = None
    chemistry: str = ""  # MCA / ECO / Unified / ...


class TankRecord(BaseModel):
    tank_id: str
    chemical: str = ""
    cylinder_used: Optional[int] = None
    is_idle: bool = False

    diameter_in: Optional[float] = None
    length_in: Optional[float] = None
    target_volume: Optional[float] = None
    min_volume: Optional[float] = None
    max_volume: Optional[float] = None
    density: Optional[float] = None

    source_row: Optional[int] = None
    raw: dict[str, str | float | int | None] = Field(default_factory=dict)


class PlantConfiguration(BaseModel):
    """The discovered shape of a UFP plant. Read from the workbook — never assumed."""

    site_name: str = ""
    # UFP ERP plant number (e.g. "554" for Moneta VA). Used downstream in
    # Ignition tag paths and document fields — kept on the plant, not the
    # device. Not reliably discoverable from the workbook; the engineer fills
    # it in on the Discover screen if it isn't already set.
    erp_number: str = ""
    workbook_filename: str = ""

    cylinders: list[CylinderSystem] = Field(default_factory=list)
    mix_systems: list[MixSystem] = Field(default_factory=list)
    tanks: list[TankRecord] = Field(default_factory=list)

    sequence_sheets: list[str] = Field(default_factory=list)
    all_sheets: list[str] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)
    confirmed: bool = False

    @property
    def active_cylinders(self) -> list[CylinderSystem]:
        return [c for c in self.cylinders if not c.is_idle]

    @property
    def idle_cylinders(self) -> list[CylinderSystem]:
        return [c for c in self.cylinders if c.is_idle]
