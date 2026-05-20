"""Extract endpoints (UI §2.3) — drive Stage 2 from the frontend.

Workflow:
  - POST /projects/{id}/extract               start (or resume) a run
  - GET  /projects/{id}/extract               current ExtractState — for polling
  - POST /projects/{id}/extract/retry/{tid}   retry one failed task

The actual orchestration lives in `backend/extract/pipeline.py`. This module
is a thin HTTP/async wrapper around it, plus the per-project concurrency
discipline (one extraction in flight per project at a time).

Extractor selection:
  - Default: `ClaudeProseExtractor`. Requires a saved API key (Settings UI).
  - `?dry_run=true`: `DryRunProseExtractor`. No network, no key — for the
    browser demo path and as a safe default while Open Q 6 is open.
  - `?simulate_failure_sheet=<name>` (dry-run only): the first attempt for
    that sheet fails so retry recovery is visible in the UI.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.extract.dry_run import DryRunProseExtractor
from backend.extract.pipeline import prepare_extract_state, retry_task, run_extract
from backend.extract.prose import ClaudeProseExtractor, ProseExtractor
from backend.model import (
	ExtractState,
	ExtractTaskStatus,
	PipelineStage,
)

from ..store import get_store


router = APIRouter(prefix="/projects/{project_id}/extract", tags=["extract"])


# Per-project running task. Bare dict keyed by project_id. Phase 1 is single-
# user local; if the server restarts mid-run, stale RUNNING tasks on disk are
# self-healed by `_repair_orphaned_running()` the next time GET is called.
_running_tasks: dict[str, asyncio.Task] = {}
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(project_id: str) -> asyncio.Lock:
	lock = _locks.get(project_id)
	if lock is None:
		lock = asyncio.Lock()
		_locks[project_id] = lock
	return lock


def _is_running(project_id: str) -> bool:
	t = _running_tasks.get(project_id)
	return t is not None and not t.done()


def _make_extractor(
	dry_run: bool, simulate_failure_sheet: Optional[str]
) -> ProseExtractor:
	if dry_run:
		fail = {simulate_failure_sheet} if simulate_failure_sheet else None
		return DryRunProseExtractor(fail_first_attempt=fail)
	return ClaudeProseExtractor()


def _repair_orphaned_running(project_id: str, state) -> None:
	"""Self-heal RUNNING tasks left behind by a server restart.

	If no in-memory asyncio.Task is alive for this project but the persisted
	state still has RUNNING tasks, mark them FAILED with a clear note so the
	engineer can retry. Without this, a restarted server would leave the
	progress UI spinning forever.
	"""
	if state.extract_state is None or _is_running(project_id):
		return
	repaired = False
	for t in state.extract_state.tasks:
		if t.status == ExtractTaskStatus.RUNNING:
			t.status = ExtractTaskStatus.FAILED
			t.finished_at = datetime.utcnow()
			t.detail = "Server restarted mid-run. Retry to continue."
			repaired = True
	if repaired:
		get_store().update(state)


def _get_state_or_404(project_id: str):
	state = get_store().get(project_id)
	if state is None:
		raise HTTPException(status_code=404, detail="Project not found")
	return state


# =============================================================================
# Endpoints
# =============================================================================
@router.post("", response_model=ExtractState, summary="Start (or resume) extraction")
async def start_extract(
	project_id: str,
	dry_run: bool = Query(False, description="Use the dry-run extractor — no API call."),
	simulate_failure_sheet: Optional[str] = Query(
		None,
		description="Dry-run only — make this sheet fail on the first attempt.",
	),
) -> ExtractState:
	state = _get_state_or_404(project_id)
	if state.plant_configuration is None or not state.plant_configuration.confirmed:
		raise HTTPException(
			status_code=409,
			detail="Confirm the Plant Configuration before extracting.",
		)
	if state.sequence_workbook_path is None:
		raise HTTPException(
			status_code=409,
			detail="Project is missing the sequence workbook on disk.",
		)

	_repair_orphaned_running(project_id, state)

	if _is_running(project_id):
		# Idempotent: a re-POST while a run is in flight just returns current state.
		return state.extract_state  # type: ignore[return-value]

	# Fresh run: rebuild task list. This drops prior results so a re-run starts
	# from a clean slate — the engineer asked for a new run.
	state.extract_state = prepare_extract_state(state.plant_configuration)
	state.device_model = None
	state.stage = PipelineStage.EXTRACT
	get_store().update(state)

	extractor = _make_extractor(dry_run, simulate_failure_sheet)
	lock = _lock_for(project_id)

	async def _runner():
		async with lock:
			await run_extract(state, get_store(), extractor)

	_running_tasks[project_id] = asyncio.create_task(_runner())
	return state.extract_state


@router.get("", response_model=ExtractState, summary="Current extraction status")
def get_extract_state(project_id: str) -> ExtractState:
	state = _get_state_or_404(project_id)
	_repair_orphaned_running(project_id, state)
	if state.extract_state is None:
		raise HTTPException(status_code=404, detail="Extraction has not been started for this project.")
	return state.extract_state


@router.post(
	"/retry/{task_id}",
	response_model=ExtractState,
	summary="Retry one failed task",
)
async def retry_extract_task(
	project_id: str,
	task_id: str,
	dry_run: bool = Query(False),
	simulate_failure_sheet: Optional[str] = Query(None),
) -> ExtractState:
	state = _get_state_or_404(project_id)
	if state.extract_state is None:
		raise HTTPException(status_code=404, detail="Extraction has not been started for this project.")
	if _is_running(project_id):
		raise HTTPException(status_code=409, detail="A run is already in progress.")

	extractor = _make_extractor(dry_run, simulate_failure_sheet)
	lock = _lock_for(project_id)

	async def _runner():
		async with lock:
			await retry_task(state, get_store(), extractor, task_id)

	try:
		_running_tasks[project_id] = asyncio.create_task(_runner())
		await _running_tasks[project_id]
	except KeyError:
		raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
	return state.extract_state
