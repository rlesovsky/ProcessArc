"""Tests for the Review endpoint contract (UI §2.4).

Exercises GET/PUT /projects/{id}/device-model with FastAPI's TestClient.
Validates the Continue-gate logic the frontend depends on:
  - GET on a project with no extracted devices returns an empty model (not 404).
  - PUT replaces the device list wholesale.
  - PUT advances stage to EXPORT iff every NEEDS_REVIEW device has been resolved
    (review_status != PENDING) — UI §2.4 Continue gate.
  - PUT auto-promotes PENDING + HIGH-confidence devices to CONFIRMED (Q5
    default — review everything but don't force a click on HIGH).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.store import get_store
from backend.model import (
	Confidence,
	DeviceClass,
	DeviceModel,
	DeviceRecord,
	PipelineStage,
	ReviewStatus,
	SourceType,
	SystemKind,
)
from backend.model.plant import CylinderSystem, PlantConfiguration


@pytest.fixture()
def client():
	return TestClient(app)


@pytest.fixture()
def project_at_extract():
	"""Build a project state sitting at EXTRACT with a confirmed Plant Config.

	The Review endpoints accept edits while stage is EXTRACT / REVIEW / EXPORT.
	"""
	store = get_store()
	state = store.create(name="Review test")
	state.plant_configuration = PlantConfiguration(
		site_name="Test",
		erp_number="554",
		workbook_filename="test.xlsx",
		cylinders=[CylinderSystem(number=1, name="Cylinder 1", sequence_sheet="Cylinder 1 Sequencing")],
		confirmed=True,
	)
	state.stage = PipelineStage.EXTRACT
	store.update(state)
	yield state
	# Cleanup is best-effort — the store has no delete; subsequent tests get a
	# fresh state via create() and don't share project_id.


def _device(**overrides) -> DeviceRecord:
	defaults = dict(
		canonical_id="CYL1_P1",
		device_class=DeviceClass.PUMP,
		system=SystemKind.CYLINDERS,
		system_number=1,
		base_name="P1",
		description="",
		source_reference="Cylinder 1 Sequencing",
		source_type=SourceType.SEQUENCE_PROSE,
		confidence=Confidence.HIGH,
		review_status=ReviewStatus.PENDING,
	)
	defaults.update(overrides)
	return DeviceRecord(**defaults)


# =============================================================================
# GET
# =============================================================================
def test_get_returns_empty_model_when_extract_produced_nothing(client, project_at_extract):
	r = client.get(f"/projects/{project_at_extract.project_id}/device-model")
	assert r.status_code == 200
	assert r.json() == DeviceModel().model_dump()


def test_get_returns_existing_model(client, project_at_extract):
	project_at_extract.device_model = DeviceModel(devices=[_device()])
	get_store().update(project_at_extract)
	r = client.get(f"/projects/{project_at_extract.project_id}/device-model")
	assert r.status_code == 200
	assert len(r.json()["devices"]) == 1


def test_get_404_for_unknown_project(client):
	r = client.get("/projects/does-not-exist/device-model")
	assert r.status_code == 404


# =============================================================================
# PUT — replace model + Continue gate + auto-promote HIGH PENDING
# =============================================================================
def test_put_replaces_device_list(client, project_at_extract):
	project_at_extract.device_model = DeviceModel(devices=[_device(canonical_id="CYL1_OLD", base_name="OLD")])
	get_store().update(project_at_extract)

	new_model = DeviceModel(devices=[_device(canonical_id="CYL1_NEW", base_name="NEW")])
	r = client.put(
		f"/projects/{project_at_extract.project_id}/device-model",
		json=new_model.model_dump(mode="json"),
	)
	assert r.status_code == 200
	state = get_store().get(project_at_extract.project_id)
	names = [d.base_name for d in state.device_model.devices]
	assert names == ["NEW"]


def test_put_advances_to_export_when_no_unresolved_flags(client, project_at_extract):
	model = DeviceModel(devices=[_device(confidence=Confidence.HIGH)])
	r = client.put(
		f"/projects/{project_at_extract.project_id}/device-model",
		json=model.model_dump(mode="json"),
	)
	body = r.json()
	assert body["advanced"] is True
	assert body["stage"] == "export"
	state = get_store().get(project_at_extract.project_id)
	assert state.stage == PipelineStage.EXPORT


def test_put_keeps_stage_when_flagged_device_unresolved(client, project_at_extract):
	model = DeviceModel(devices=[
		_device(canonical_id="A", confidence=Confidence.NEEDS_REVIEW, review_status=ReviewStatus.PENDING),
		_device(canonical_id="B", confidence=Confidence.HIGH),
	])
	r = client.put(
		f"/projects/{project_at_extract.project_id}/device-model",
		json=model.model_dump(mode="json"),
	)
	body = r.json()
	assert body["advanced"] is False
	assert body["unresolved_flags"] is True
	assert get_store().get(project_at_extract.project_id).stage == PipelineStage.EXTRACT


def test_put_advances_when_all_flags_resolved(client, project_at_extract):
	# A NEEDS_REVIEW device that's been Confirmed or Excluded by the engineer
	# counts as resolved.
	model = DeviceModel(devices=[
		_device(canonical_id="A", confidence=Confidence.NEEDS_REVIEW, review_status=ReviewStatus.CONFIRMED),
		_device(canonical_id="B", confidence=Confidence.NEEDS_REVIEW, review_status=ReviewStatus.EXCLUDED),
	])
	r = client.put(
		f"/projects/{project_at_extract.project_id}/device-model",
		json=model.model_dump(mode="json"),
	)
	assert r.json()["advanced"] is True
	assert get_store().get(project_at_extract.project_id).stage == PipelineStage.EXPORT


def test_put_auto_promotes_high_pending_to_confirmed(client, project_at_extract):
	model = DeviceModel(devices=[_device(confidence=Confidence.HIGH, review_status=ReviewStatus.PENDING)])
	client.put(
		f"/projects/{project_at_extract.project_id}/device-model",
		json=model.model_dump(mode="json"),
	)
	persisted = get_store().get(project_at_extract.project_id).device_model.devices[0]
	assert persisted.review_status == ReviewStatus.CONFIRMED


def test_put_does_not_auto_promote_needs_review_pending(client, project_at_extract):
	model = DeviceModel(devices=[_device(confidence=Confidence.NEEDS_REVIEW, review_status=ReviewStatus.PENDING)])
	client.put(
		f"/projects/{project_at_extract.project_id}/device-model",
		json=model.model_dump(mode="json"),
	)
	persisted = get_store().get(project_at_extract.project_id).device_model.devices[0]
	assert persisted.review_status == ReviewStatus.PENDING  # the engineer must act
