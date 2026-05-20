"""Tests for the extract pipeline orchestrator.

Drives `run_extract` / `retry_task` with a scripted ProseExtractor — no real
workbook is opened (ingest is patched) and no API call is made. Validates the
contract the Extract screen depends on:
  - happy path → all tasks DONE, stage advances to REVIEW
  - one sheet fails → other sheets still complete, stage advances iff at least one succeeded
  - retry recovers a failed sheet and replaces (not duplicates) its devices
  - persistence happens during the run, not only at the end (so polling works)
"""

from __future__ import annotations

import pytest

from backend.extract.pipeline import prepare_extract_state, retry_task, run_extract
from backend.extract.prose import (
	ProseExtractionError,
	ProseExtractor,
	ProseSource,
	SheetExtraction,
)
from backend.ingest import SheetKind
from backend.model import (
	ExtractTaskStatus,
	PipelineStage,
	ProjectState,
)
from backend.model.device import (
	Confidence,
	DeviceClass,
	DeviceRecord,
	SourceType,
)
from backend.model.plant import (
	CylinderSystem,
	MixSystem,
	PlantConfiguration,
)


# =============================================================================
# Fakes
# =============================================================================
class _FakeStore:
	def __init__(self) -> None:
		self.updates: list[ProjectState] = []

	def update(self, state: ProjectState) -> ProjectState:
		# Deep copy so successive mutations don't rewrite history.
		self.updates.append(state.model_copy(deep=True))
		return state


class _ScriptedExtractor(ProseExtractor):
	"""Returns canned results per sheet name.

	scripts[sheet_name] is one of:
	  - list[(base_name, DeviceClass)]   → success
	  - Exception                        → failure on every attempt
	  - callable(attempt:int) -> one of the above → conditional per attempt
	"""

	def __init__(self, scripts: dict) -> None:
		self._scripts = scripts
		self._attempts: dict[str, int] = {}

	def extract_sheet(self, source: ProseSource) -> SheetExtraction:
		n = self._attempts.get(source.sheet_name, 0) + 1
		self._attempts[source.sheet_name] = n
		action = self._scripts.get(source.sheet_name)
		if action is None:
			raise ProseExtractionError(f"no script for {source.sheet_name}")
		if callable(action) and not isinstance(action, Exception):
			action = action(n)
		if isinstance(action, Exception):
			raise action
		devices = [
			DeviceRecord(
				canonical_id=f"{source.system.value}-{source.system_number}-{name}",
				device_class=cls,
				system=source.system,
				system_number=source.system_number,
				base_name=name,
				description="",
				source_reference=source.sheet_name,
				source_type=SourceType.SEQUENCE_PROSE,
				confidence=Confidence.HIGH,
			)
			for name, cls in action
		]
		return SheetExtraction(
			sheet_name=source.sheet_name,
			system=source.system,
			system_number=source.system_number,
			devices=devices,
		)


class _FakeIngestedSheet:
	def __init__(self, name: str, kind: SheetKind, lines: list[str]) -> None:
		self.name = name
		self.kind = kind
		self._lines = lines

	def text_lines(self, max_cols: int = 4) -> list[str]:
		return list(self._lines)


class _FakeIngestedWorkbook:
	def __init__(self) -> None:
		self.sheets = [
			_FakeIngestedSheet("Cylinder 1 Sequencing", SheetKind.CYLINDER_SEQUENCE, ["step 1"]),
			_FakeIngestedSheet("Cylinder 3 Sequencing", SheetKind.CYLINDER_SEQUENCE, ["step 1"]),
			_FakeIngestedSheet("ECO Mix Sequencing", SheetKind.MIX_SEQUENCE, ["step 1"]),
		]


class _FakeTables:
	tanks = [object(), object(), object()]
	flow_meters: list = []
	chemicals: dict = {}
	cylinder_voids: dict = {}
	warnings: list = []


def _patch_ingest(monkeypatch, *, fail_tables: bool = False) -> None:
	monkeypatch.setattr(
		"backend.extract.pipeline.ingest_workbook",
		lambda path: _FakeIngestedWorkbook(),
	)
	if fail_tables:
		def _boom(_):
			raise RuntimeError("table boom")
		monkeypatch.setattr("backend.extract.pipeline.extract_tables", _boom)
	else:
		monkeypatch.setattr(
			"backend.extract.pipeline.extract_tables", lambda wb: _FakeTables()
		)


def _make_plant() -> PlantConfiguration:
	return PlantConfiguration(
		site_name="Test",
		erp_number="554",
		workbook_filename="test.xlsx",
		cylinders=[
			CylinderSystem(number=1, name="Cylinder 1", sequence_sheet="Cylinder 1 Sequencing"),
			CylinderSystem(number=2, name="Cylinder 2", sequence_sheet=None, is_idle=True),
			CylinderSystem(number=3, name="Cylinder 3", sequence_sheet="Cylinder 3 Sequencing"),
		],
		mix_systems=[
			MixSystem(number=1, name="ECO Mix", sequence_sheet="ECO Mix Sequencing", chemistry="ECO"),
		],
		sequence_sheets=["Cylinder 1 Sequencing", "Cylinder 3 Sequencing", "ECO Mix Sequencing"],
		confirmed=True,
	)


def _make_state(tmp_path) -> ProjectState:
	wb_path = tmp_path / "test.xlsx"
	wb_path.write_bytes(b"")
	state = ProjectState(
		project_id="p1",
		project_name="Test",
		stage=PipelineStage.EXTRACT,
		sequence_workbook_path=wb_path,
		plant_configuration=_make_plant(),
	)
	state.extract_state = prepare_extract_state(state.plant_configuration)
	return state


# =============================================================================
# prepare_extract_state
# =============================================================================
def test_prepare_includes_tables_task_first():
	es = prepare_extract_state(_make_plant())
	assert es.tasks[0].id == "tables"
	assert es.tasks[0].kind.value == "tables"


def test_prepare_one_prose_task_per_active_cylinder():
	es = prepare_extract_state(_make_plant())
	sheets = [t.sheet_name for t in es.tasks if t.kind.value == "prose_sheet"]
	assert "Cylinder 1 Sequencing" in sheets
	assert "Cylinder 3 Sequencing" in sheets


def test_prepare_skips_idle_cylinders():
	es = prepare_extract_state(_make_plant())
	assert all("Cylinder 2" not in t.label for t in es.tasks)


def test_prepare_includes_mix_systems():
	es = prepare_extract_state(_make_plant())
	assert any("ECO Mix" in t.label for t in es.tasks)


# =============================================================================
# run_extract — happy path + failure handling
# =============================================================================
@pytest.mark.asyncio
async def test_happy_path(tmp_path, monkeypatch):
	_patch_ingest(monkeypatch)
	state = _make_state(tmp_path)
	extractor = _ScriptedExtractor({
		"Cylinder 1 Sequencing": [("P1", DeviceClass.PUMP)],
		"Cylinder 3 Sequencing": [("VPD", DeviceClass.VALVE)],
		"ECO Mix Sequencing": [("MP1", DeviceClass.PUMP)],
	})
	await run_extract(state, _FakeStore(), extractor)
	assert all(t.status == ExtractTaskStatus.DONE for t in state.extract_state.tasks)
	assert state.stage == PipelineStage.REVIEW
	assert state.device_model is not None
	assert len(state.device_model.devices) == 3


@pytest.mark.asyncio
async def test_one_sheet_fails_others_succeed(tmp_path, monkeypatch):
	_patch_ingest(monkeypatch)
	state = _make_state(tmp_path)
	extractor = _ScriptedExtractor({
		"Cylinder 1 Sequencing": ProseExtractionError("network down"),
		"Cylinder 3 Sequencing": [("VPD", DeviceClass.VALVE)],
		"ECO Mix Sequencing": [("MP1", DeviceClass.PUMP)],
	})
	await run_extract(state, _FakeStore(), extractor)
	failed = next(t for t in state.extract_state.tasks if t.sheet_name == "Cylinder 1 Sequencing")
	assert failed.status == ExtractTaskStatus.FAILED
	assert "network down" in failed.detail
	for t in state.extract_state.tasks:
		if t.sheet_name in ("Cylinder 3 Sequencing", "ECO Mix Sequencing"):
			assert t.status == ExtractTaskStatus.DONE
	# Stage still advances because at least one succeeded:
	assert state.stage == PipelineStage.REVIEW


@pytest.mark.asyncio
async def test_every_task_failing_keeps_stage_at_extract(tmp_path, monkeypatch):
	_patch_ingest(monkeypatch, fail_tables=True)
	state = _make_state(tmp_path)
	extractor = _ScriptedExtractor({
		sheet: ProseExtractionError("nope")
		for sheet in ("Cylinder 1 Sequencing", "Cylinder 3 Sequencing", "ECO Mix Sequencing")
	})
	await run_extract(state, _FakeStore(), extractor)
	assert state.stage == PipelineStage.EXTRACT
	assert all(t.status == ExtractTaskStatus.FAILED for t in state.extract_state.tasks)


@pytest.mark.asyncio
async def test_table_failure_isolated_to_its_task(tmp_path, monkeypatch):
	"""A table-extraction failure must not cascade into the prose tasks."""
	_patch_ingest(monkeypatch, fail_tables=True)
	state = _make_state(tmp_path)
	extractor = _ScriptedExtractor({
		"Cylinder 1 Sequencing": [("P1", DeviceClass.PUMP)],
		"Cylinder 3 Sequencing": [("VPD", DeviceClass.VALVE)],
		"ECO Mix Sequencing": [("MP1", DeviceClass.PUMP)],
	})
	await run_extract(state, _FakeStore(), extractor)
	tables = next(t for t in state.extract_state.tasks if t.id == "tables")
	assert tables.status == ExtractTaskStatus.FAILED
	for t in state.extract_state.tasks:
		if t.id != "tables":
			assert t.status == ExtractTaskStatus.DONE


# =============================================================================
# retry_task
# =============================================================================
@pytest.mark.asyncio
async def test_retry_recovers_failed_task(tmp_path, monkeypatch):
	_patch_ingest(monkeypatch)
	state = _make_state(tmp_path)

	def cyl1(attempt: int):
		if attempt == 1:
			return ProseExtractionError("first try fails")
		return [("P1", DeviceClass.PUMP)]

	extractor = _ScriptedExtractor({
		"Cylinder 1 Sequencing": cyl1,
		"Cylinder 3 Sequencing": [("VPD", DeviceClass.VALVE)],
		"ECO Mix Sequencing": [("MP1", DeviceClass.PUMP)],
	})
	await run_extract(state, _FakeStore(), extractor)
	cyl1_task = next(t for t in state.extract_state.tasks if t.sheet_name == "Cylinder 1 Sequencing")
	assert cyl1_task.status == ExtractTaskStatus.FAILED

	await retry_task(state, _FakeStore(), extractor, cyl1_task.id)
	assert cyl1_task.status == ExtractTaskStatus.DONE
	assert any(d.base_name == "P1" for d in state.device_model.devices)


@pytest.mark.asyncio
async def test_retry_replaces_prior_devices_from_same_sheet(tmp_path, monkeypatch):
	"""A retry must not double-add devices from the prior attempt."""
	_patch_ingest(monkeypatch)
	state = _make_state(tmp_path)
	store = _FakeStore()
	extractor = _ScriptedExtractor({
		"Cylinder 1 Sequencing": [("P1", DeviceClass.PUMP)],
		"Cylinder 3 Sequencing": [("V1", DeviceClass.VALVE)],
		"ECO Mix Sequencing": [("MP1", DeviceClass.PUMP)],
	})
	await run_extract(state, store, extractor)
	before = len(state.device_model.devices)

	# Change the script and retry just cyl1 — should replace, not append.
	extractor._scripts["Cylinder 1 Sequencing"] = [
		("P1", DeviceClass.PUMP), ("P2", DeviceClass.PUMP),
	]
	cyl1_id = next(t.id for t in state.extract_state.tasks if t.sheet_name == "Cylinder 1 Sequencing")
	await retry_task(state, store, extractor, cyl1_id)

	cyl1_devices = sorted(
		d.base_name for d in state.device_model.devices
		if d.source_reference == "Cylinder 1 Sequencing"
	)
	assert cyl1_devices == ["P1", "P2"]
	assert len(state.device_model.devices) == before + 1


# =============================================================================
# Persistence — store sees progress, not just the final state
# =============================================================================
@pytest.mark.asyncio
async def test_store_updated_during_run(tmp_path, monkeypatch):
	_patch_ingest(monkeypatch)
	state = _make_state(tmp_path)
	store = _FakeStore()
	extractor = _ScriptedExtractor({
		sheet: [("D", DeviceClass.VALVE)]
		for sheet in ("Cylinder 1 Sequencing", "Cylinder 3 Sequencing", "ECO Mix Sequencing")
	})
	await run_extract(state, store, extractor)
	# There should be many persists, not just one — RUNNING transitions must be visible.
	assert len(store.updates) >= 4
	any_running = any(
		any(t.status == ExtractTaskStatus.RUNNING for t in u.extract_state.tasks)
		for u in store.updates
		if u.extract_state is not None
	)
	assert any_running
