"""In-memory project store with on-disk persistence per project_id.

Phase 1 is single-user local; no database. Each project gets a folder under
PROJECTS_DIR holding its uploads + a state.json snapshot.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.model import ProjectState
from backend.settings import get_settings


class ProjectStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._projects: dict[str, ProjectState] = {}

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex[:12]

    def create(self, name: str) -> ProjectState:
        project_id = self._new_id()
        settings = get_settings()
        proj_dir = settings.projects_dir / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        state = ProjectState(project_id=project_id, project_name=name or project_id)
        with self._lock:
            self._projects[project_id] = state
        self._persist(state)
        return state

    def get(self, project_id: str) -> Optional[ProjectState]:
        with self._lock:
            state = self._projects.get(project_id)
        if state is not None:
            return state
        return self._load_from_disk(project_id)

    def update(self, state: ProjectState) -> ProjectState:
        with self._lock:
            self._projects[state.project_id] = state
        self._persist(state)
        return state

    def project_dir(self, project_id: str) -> Path:
        return get_settings().projects_dir / project_id

    def _persist(self, state: ProjectState) -> None:
        path = self.project_dir(state.project_id) / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(state.model_dump_json(indent=2, exclude_none=False))

    def _load_from_disk(self, project_id: str) -> Optional[ProjectState]:
        path = self.project_dir(project_id) / "state.json"
        if not path.exists():
            return None
        raw = json.loads(path.read_text())
        state = ProjectState.model_validate(raw)
        with self._lock:
            self._projects[project_id] = state
        return state


_store = ProjectStore()


def get_store() -> ProjectStore:
    return _store
