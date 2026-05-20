from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .device import DeviceModel
from .plant import PlantConfiguration


class PipelineStage(str, Enum):
    CONFIGURE = "configure"
    DISCOVER = "discover"
    EXTRACT = "extract"
    REVIEW = "review"
    EXPORT = "export"


class ExtractTaskKind(str, Enum):
    TABLES = "tables"
    PROSE_SHEET = "prose_sheet"


class ExtractTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ExtractTask(BaseModel):
    """One row in the Extract screen checklist (UI §2.3).

    `kind` distinguishes the local data path (tables, never leaves the machine)
    from prose sent to the Claude API. The frontend uses this to render the
    Plan §8.3 data-boundary visibly.
    """

    id: str
    kind: ExtractTaskKind
    label: str
    status: ExtractTaskStatus = ExtractTaskStatus.QUEUED
    detail: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # For prose tasks only — carried through so retry can rebuild the source.
    sheet_name: Optional[str] = None


class ExtractState(BaseModel):
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    tasks: list[ExtractTask] = Field(default_factory=list)
    device_count: int = 0

    @property
    def is_done(self) -> bool:
        return bool(self.tasks) and all(
            t.status in (ExtractTaskStatus.DONE, ExtractTaskStatus.FAILED) for t in self.tasks
        )

    @property
    def is_running(self) -> bool:
        return any(
            t.status in (ExtractTaskStatus.QUEUED, ExtractTaskStatus.RUNNING)
            for t in self.tasks
        )


class ProjectState(BaseModel):
    """Per-project state held in memory and persisted to disk."""

    project_id: str
    project_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    stage: PipelineStage = PipelineStage.CONFIGURE

    sequence_workbook_path: Optional[Path] = None
    io_template_path: Optional[Path] = None
    ce_profile_path: Optional[Path] = None

    plant_configuration: Optional[PlantConfiguration] = None
    device_model: Optional[DeviceModel] = None
    extract_state: Optional[ExtractState] = None

    # Pydantic v2 ignores unknown fields by default. Existing state.json files
    # written before this cleanup may still carry `extraction_log` / `errors`
    # — those load cleanly and the fields are simply dropped on rewrite.
