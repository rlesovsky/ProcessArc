"""Extract Pipeline (Plan §8 / UI §2.3) — drive the Prose Extractor from the project.

Owns Stage 2:
  - Read the Chemical and Tank tables directly (local; never leaves the machine).
  - For every confirmed cylinder + mix sequencing sheet, send the prose to the
    Prose Extractor and collect DeviceRecords stamped with the right
    System / System Number from the Plant Configuration (Plan §8.2).

The pipeline mutates `state.extract_state` in place and persists after every
status transition so a polling client sees live progress. A `ProseExtractionError`
on one sheet is recorded on that task only — the other tasks continue, and the
engineer can retry the failed task once the underlying issue (network, key,
prose) is fixed.

The Prose Extractor is injectable: in tests and in the browser dry-run path,
a fake extractor is passed in and no network or API key is required.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from backend.ingest import IngestedWorkbook, SheetKind, ingest_workbook
from backend.model import (
	DeviceModel,
	ExtractState,
	ExtractTask,
	ExtractTaskKind,
	ExtractTaskStatus,
	PipelineStage,
	ProjectState,
	SystemKind,
)
from backend.model.plant import PlantConfiguration

from .prose import (
	ProseExtractionError,
	ProseExtractor,
	ProseSource,
)
from .tables import TableExtraction, extract_tables


# =============================================================================
# Build the task list from the confirmed Plant Configuration
# =============================================================================
def _tables_task() -> ExtractTask:
	return ExtractTask(
		id="tables",
		kind=ExtractTaskKind.TABLES,
		label="Tables read directly",
	)


def _prose_task_id(sheet_name: str) -> str:
	# Stable id derived from sheet name — used by /retry/{task_id}.
	return "prose:" + sheet_name


def _prose_tasks_for(plant: PlantConfiguration) -> list[ExtractTask]:
	"""One prose task per non-idle cylinder sheet + per mix-system sheet.

	Idle cylinders are skipped here (their sheet is preserved on disk, but they
	are not commissioned — extracting devices would only create review noise).
	"""
	tasks: list[ExtractTask] = []
	for cyl in plant.cylinders:
		if cyl.is_idle or not cyl.sequence_sheet:
			continue
		tasks.append(
			ExtractTask(
				id=_prose_task_id(cyl.sequence_sheet),
				kind=ExtractTaskKind.PROSE_SHEET,
				label=f"Cylinder {cyl.number} sequence — sent to Claude API",
				sheet_name=cyl.sequence_sheet,
			)
		)
	for mix in plant.mix_systems:
		if not mix.sequence_sheet:
			continue
		tasks.append(
			ExtractTask(
				id=_prose_task_id(mix.sequence_sheet),
				kind=ExtractTaskKind.PROSE_SHEET,
				label=f"{mix.name or 'Mixing'} sequence — sent to Claude API",
				sheet_name=mix.sequence_sheet,
			)
		)
	return tasks


def prepare_extract_state(plant: PlantConfiguration) -> ExtractState:
	"""Build the initial ExtractState for a confirmed Plant Configuration.

	All tasks start QUEUED. Called when a fresh extraction is kicked off.
	"""
	return ExtractState(tasks=[_tables_task(), *_prose_tasks_for(plant)])


# =============================================================================
# Source helpers
# =============================================================================
def _system_context_for_sheet(
	plant: PlantConfiguration, sheet_name: str
) -> tuple[SystemKind, Optional[int]]:
	"""Resolve System / System Number for a sequencing sheet name.

	Stamped from the *confirmed* Plant Configuration (Plan §8.2). The prose
	itself is never asked.
	"""
	for cyl in plant.cylinders:
		if cyl.sequence_sheet == sheet_name:
			return SystemKind.CYLINDERS, cyl.number
	for mix in plant.mix_systems:
		if mix.sequence_sheet == sheet_name:
			return SystemKind.MIXING, mix.number
	# Should never happen if tasks were built from the same plant — be loud if it does.
	raise ProseExtractionError(
		f"Sheet '{sheet_name}' is not in the confirmed Plant Configuration."
	)


def _build_source(wb: IngestedWorkbook, plant: PlantConfiguration, sheet_name: str) -> ProseSource:
	sheet = next((s for s in wb.sheets if s.name == sheet_name), None)
	if sheet is None:
		raise ProseExtractionError(
			f"Sheet '{sheet_name}' was confirmed on the Plant Configuration but is "
			f"not present in the workbook."
		)
	if sheet.kind not in (SheetKind.CYLINDER_SEQUENCE, SheetKind.MIX_SEQUENCE):
		raise ProseExtractionError(
			f"Sheet '{sheet_name}' is classified as {sheet.kind.value}, not a "
			f"sequencing sheet."
		)
	system, number = _system_context_for_sheet(plant, sheet_name)
	return ProseSource.from_ingested_sheet(sheet, system=system, system_number=number)


# =============================================================================
# Per-task runners
# =============================================================================
def _summarize_tables(t: TableExtraction) -> str:
	bits = [f"{len(t.tanks)} tanks"]
	if t.flow_meters:
		bits.append(f"{len(t.flow_meters)} flow meters")
	if t.chemicals:
		bits.append(f"{len(t.chemicals)} chemicals")
	if t.cylinder_voids:
		bits.append(f"{len(t.cylinder_voids)} cylinder voids")
	return ", ".join(bits)


def _start(task: ExtractTask) -> None:
	task.status = ExtractTaskStatus.RUNNING
	task.started_at = datetime.utcnow()
	task.detail = ""


def _finish_done(task: ExtractTask, detail: str) -> None:
	task.status = ExtractTaskStatus.DONE
	task.finished_at = datetime.utcnow()
	task.detail = detail


def _finish_failed(task: ExtractTask, detail: str) -> None:
	task.status = ExtractTaskStatus.FAILED
	task.finished_at = datetime.utcnow()
	task.detail = detail


async def _run_tables(
	task: ExtractTask,
	wb: IngestedWorkbook,
	state: ProjectState,
	persist,
) -> None:
	_start(task)
	persist(state)
	try:
		result = await asyncio.to_thread(extract_tables, wb)
		_finish_done(task, _summarize_tables(result))
	except Exception as exc:  # noqa: BLE001 — surface anything as a task failure
		_finish_failed(task, f"Table extraction failed: {exc}")
	persist(state)


async def _run_prose_task(
	task: ExtractTask,
	wb: IngestedWorkbook,
	plant: PlantConfiguration,
	extractor: ProseExtractor,
	state: ProjectState,
	persist,
) -> None:
	_start(task)
	persist(state)
	try:
		if not task.sheet_name:
			raise ProseExtractionError("Prose task is missing sheet_name.")
		source = _build_source(wb, plant, task.sheet_name)
		extraction = await asyncio.to_thread(extractor.extract_sheet, source)

		# Merge this sheet's devices into the project's DeviceModel. The
		# DeviceModel is the canonical store the Review screen will consume.
		if state.device_model is None:
			state.device_model = DeviceModel()
		# Replace any prior devices from this same sheet so a retry doesn't
		# leave duplicates from the previous attempt.
		state.device_model.devices = [
			d
			for d in state.device_model.devices
			if d.source_reference != source.sheet_name
		]
		# Re-stamp source_reference to the sheet name so the dedupe above is
		# stable across retries.
		for d in extraction.devices:
			if not d.source_reference:
				d.source_reference = source.sheet_name
		state.device_model.devices.extend(extraction.devices)
		state.extract_state.device_count = len(state.device_model.devices)

		count = len(extraction.devices)
		note = f"{count} device{'s' if count != 1 else ''}"
		if extraction.notes:
			note += f" · {len(extraction.notes)} note{'s' if len(extraction.notes) != 1 else ''}"
		_finish_done(task, note)
	except ProseExtractionError as exc:
		_finish_failed(task, str(exc))
	except Exception as exc:  # noqa: BLE001 — unexpected failures still belong on the task
		_finish_failed(task, f"Unexpected error: {exc}")
	persist(state)


# =============================================================================
# Orchestrators
# =============================================================================
def _persist_factory(store):
	def _persist(state: ProjectState) -> None:
		store.update(state)
	return _persist


def _maybe_advance_stage(state: ProjectState) -> None:
	"""When every task is terminal AND at least one succeeded, advance to Review.

	If every task failed, the project stays on EXTRACT so the engineer can fix
	whatever blocked the run and retry without losing position in the pipeline.
	"""
	es = state.extract_state
	if es is None or not es.is_done:
		return
	any_ok = any(t.status == ExtractTaskStatus.DONE for t in es.tasks)
	if any_ok:
		state.stage = PipelineStage.REVIEW


async def run_extract(
	state: ProjectState,
	store,
	extractor: ProseExtractor,
) -> None:
	"""Run the full pipeline. Mutates `state` in place; persists via `store`.

	Assumes:
	  - state.plant_configuration is set and confirmed
	  - state.sequence_workbook_path points to a real .xlsx
	  - state.extract_state has been populated with the initial task list
	"""
	if state.plant_configuration is None or state.sequence_workbook_path is None:
		raise RuntimeError(
			"run_extract called without plant_configuration or sequence_workbook_path."
		)
	if state.extract_state is None:
		state.extract_state = prepare_extract_state(state.plant_configuration)

	persist = _persist_factory(store)
	state.extract_state.started_at = datetime.utcnow()
	state.extract_state.finished_at = None
	persist(state)

	wb = await asyncio.to_thread(ingest_workbook, state.sequence_workbook_path)

	for task in state.extract_state.tasks:
		# Skip tasks that are already terminal (a retry path may pre-mark
		# completed tasks as DONE; the full-run path will not).
		if task.status in (ExtractTaskStatus.DONE, ExtractTaskStatus.FAILED):
			continue
		if task.kind == ExtractTaskKind.TABLES:
			await _run_tables(task, wb, state, persist)
		else:
			await _run_prose_task(
				task,
				wb,
				state.plant_configuration,
				extractor,
				state,
				persist,
			)

	state.extract_state.finished_at = datetime.utcnow()
	_maybe_advance_stage(state)
	persist(state)


async def retry_task(
	state: ProjectState,
	store,
	extractor: ProseExtractor,
	task_id: str,
) -> ExtractTask:
	"""Re-run a single task in place. Returns the updated task."""
	if state.extract_state is None:
		raise RuntimeError("No extract_state on this project.")
	task = next((t for t in state.extract_state.tasks if t.id == task_id), None)
	if task is None:
		raise KeyError(task_id)

	task.status = ExtractTaskStatus.QUEUED
	task.detail = ""
	task.started_at = None
	task.finished_at = None
	state.extract_state.finished_at = None
	persist = _persist_factory(store)
	persist(state)

	wb = await asyncio.to_thread(ingest_workbook, state.sequence_workbook_path)
	if task.kind == ExtractTaskKind.TABLES:
		await _run_tables(task, wb, state, persist)
	else:
		await _run_prose_task(
			task,
			wb,
			state.plant_configuration,
			extractor,
			state,
			persist,
		)

	if state.extract_state.is_done:
		state.extract_state.finished_at = datetime.utcnow()
		_maybe_advance_stage(state)
		persist(state)
	return task
