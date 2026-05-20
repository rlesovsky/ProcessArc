"""Project endpoints covering Stage 0 (Configure) and Stage 0A (Discover).

Stages 2 (Extract), 3 (Review), and 5 (Export) will be added in follow-ups.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.config import discover_plant_configuration
from backend.ingest import ingest_workbook
from backend.model import (
	Confidence,
	DeviceModel,
	PipelineStage,
	ProjectState,
	ReviewStatus,
)
from backend.model.plant import PlantConfiguration

from ..store import get_store


router = APIRouter(prefix="/projects", tags=["projects"])


def _save_upload(upload: UploadFile, dest_dir: Path, label: str) -> Path:
	if upload.filename is None or upload.filename == "":
		raise HTTPException(status_code=400, detail=f"{label}: filename missing")
	dest_dir.mkdir(parents=True, exist_ok=True)
	out_path = dest_dir / upload.filename
	with out_path.open("wb") as f:
		shutil.copyfileobj(upload.file, f)
	upload.file.close()
	return out_path


@router.post("", summary="Create project + upload files (Stage 0 Configure + Stage 0A Discover)")
async def create_project(
	sequence_workbook: UploadFile = File(..., description="UFP sequence workbook (.xlsx)"),
	io_template: UploadFile = File(..., description="UFP Ignition IO-list template (.xlsx)"),
	ce_profile: Optional[UploadFile] = File(None, description="Optional UFP C&E profile (.xlsx)"),
	project_name: str = Form(default=""),
) -> dict:
	store = get_store()
	state = store.create(name=project_name or sequence_workbook.filename or "Untitled")

	proj_dir = store.project_dir(state.project_id)

	state.sequence_workbook_path = _save_upload(sequence_workbook, proj_dir / "input", "sequence_workbook")
	state.io_template_path = _save_upload(io_template, proj_dir / "input", "io_template")
	if ce_profile is not None:
		state.ce_profile_path = _save_upload(ce_profile, proj_dir / "input", "ce_profile")

	# Stage 0A — Discover Plant Configuration
	# On failure the project record stays on disk in its just-created
	# empty state; the HTTP 400 detail is what surfaces the cause to the
	# engineer. We no longer persist a separate error log — the response
	# carries the same information.
	try:
		wb = ingest_workbook(state.sequence_workbook_path)
		plant = discover_plant_configuration(wb)
	except Exception as exc:
		raise HTTPException(status_code=400, detail=f"Discovery failed: {exc}") from exc

	if not project_name:
		state.project_name = plant.site_name or state.project_name

	state.plant_configuration = plant
	state.stage = PipelineStage.DISCOVER
	store.update(state)

	return {
		"project_id": state.project_id,
		"project_name": state.project_name,
		"stage": state.stage.value,
		"plant_configuration": plant.model_dump(),
	}


@router.get("/{project_id}", summary="Fetch full project state")
def get_project(project_id: str) -> ProjectState:
	state = get_store().get(project_id)
	if state is None:
		raise HTTPException(status_code=404, detail="Project not found")
	return state


@router.get("/{project_id}/plant-configuration", summary="The discovered Plant Configuration")
def get_plant_configuration(project_id: str) -> PlantConfiguration:
	state = get_store().get(project_id)
	if state is None:
		raise HTTPException(status_code=404, detail="Project not found")
	if state.plant_configuration is None:
		raise HTTPException(status_code=409, detail="Plant Configuration has not been discovered yet")
	return state.plant_configuration


@router.post(
	"/{project_id}/plant-configuration/confirm",
	summary="Confirm (or correct) the Plant Configuration before extraction",
)
def confirm_plant_configuration(project_id: str, plant: PlantConfiguration) -> dict:
	store = get_store()
	state = store.get(project_id)
	if state is None:
		raise HTTPException(status_code=404, detail="Project not found")

	plant.confirmed = True
	state.plant_configuration = plant
	state.stage = PipelineStage.EXTRACT
	store.update(state)
	return {"project_id": state.project_id, "stage": state.stage.value, "confirmed": True}


@router.get(
	"/{project_id}/device-model",
	summary="Current Project Device Model (UI §2.4 — Review screen feed)",
)
def get_device_model(project_id: str) -> DeviceModel:
	state = get_store().get(project_id)
	if state is None:
		raise HTTPException(status_code=404, detail="Project not found")
	if state.device_model is None:
		# An empty model is a valid state — the extract step may have produced
		# zero devices, or the engineer may be on the Review screen for an
		# all-idle plant. Don't 404 here; return an empty model so the screen
		# can render an explanatory empty state.
		return DeviceModel()
	return state.device_model


def _has_unresolved_flags(model: DeviceModel) -> bool:
	"""UI §2.4 Continue gate: a flagged (NEEDS_REVIEW) device is unresolved if
	its review_status is still PENDING. Confirmed / Edited / Excluded all
	count as resolved.
	"""
	return any(
		d.confidence == Confidence.NEEDS_REVIEW and d.review_status == ReviewStatus.PENDING
		for d in model.devices
	)


@router.put(
	"/{project_id}/device-model",
	summary="Save the engineer's corrected Device Model (UI §2.4 Continue)",
)
def save_device_model(project_id: str, model: DeviceModel) -> dict:
	store = get_store()
	state = store.get(project_id)
	if state is None:
		raise HTTPException(status_code=404, detail="Project not found")
	if state.stage not in (PipelineStage.EXTRACT, PipelineStage.REVIEW, PipelineStage.EXPORT):
		raise HTTPException(
			status_code=409,
			detail=f"Cannot edit the device model from stage '{state.stage.value}'.",
		)

	# Auto-promote any still-PENDING high-confidence devices to CONFIRMED on
	# save — high-confidence devices don't require an explicit click per Q5
	# (Phase 1 default: review everything but don't force a click on HIGH).
	for d in model.devices:
		if d.review_status == ReviewStatus.PENDING and d.confidence == Confidence.HIGH:
			d.review_status = ReviewStatus.CONFIRMED

	state.device_model = model

	advanced = False
	if not _has_unresolved_flags(model):
		state.stage = PipelineStage.EXPORT
		advanced = True
	store.update(state)

	return {
		"project_id": state.project_id,
		"stage": state.stage.value,
		"advanced": advanced,
		"device_count": len(model.devices),
		"unresolved_flags": _has_unresolved_flags(model),
	}
