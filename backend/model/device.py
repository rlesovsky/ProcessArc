from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DeviceClass(str, Enum):
    PUMP = "Pump"
    VALVE = "Valve"
    VFD_PUMP = "VFD Pump"
    CONTROL_VALVE = "Control Valve"
    TANK = "Tank"


class SystemKind(str, Enum):
    CYLINDERS = "Cylinders"
    MIXING = "Mixing"


class SourceType(str, Enum):
    SEQUENCE_PROSE = "Sequence Prose"
    TABLE = "Table"
    MANUAL = "Manual"
    PID = "P&ID"  # reserved for future Phase (Plan §15)


class Confidence(str, Enum):
    HIGH = "High"
    NEEDS_REVIEW = "Needs Review"


class ReviewStatus(str, Enum):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    EXCLUDED = "Excluded"


class DeviceRecord(BaseModel):
    """One canonical device. Source-agnostic; carries the *actual* System Number."""

    canonical_id: str
    device_class: DeviceClass
    system: SystemKind
    system_number: Optional[int] = None  # the *real* number — 3, not a sequential index
    base_name: str
    description: str = ""

    source_reference: str = ""
    source_type: SourceType = SourceType.SEQUENCE_PROSE
    confidence: Confidence = Confidence.HIGH

    ignition_udt_type: str = ""
    ignition_folder: str = ""
    ce_output_tag: str = ""

    register_values: dict[str, str | int | float] = Field(default_factory=dict)
    notes: str = ""

    review_status: ReviewStatus = ReviewStatus.PENDING


class DeviceModel(BaseModel):
    """The full Project Device Model — every confirmed and pending device."""

    devices: list[DeviceRecord] = Field(default_factory=list)

    def by_system(self, system: SystemKind, number: Optional[int] = None) -> list[DeviceRecord]:
        out = [d for d in self.devices if d.system == system]
        if number is not None:
            out = [d for d in out if d.system_number == number]
        return out

    def by_class(self, device_class: DeviceClass) -> list[DeviceRecord]:
        return [d for d in self.devices if d.device_class == device_class]

    def needs_review(self) -> list[DeviceRecord]:
        return [d for d in self.devices if d.confidence == Confidence.NEEDS_REVIEW]
