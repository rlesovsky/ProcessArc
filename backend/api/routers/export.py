"""Export endpoints (UI §2.5) — produce and serve the two deliverables.

Workflow:
  - POST /projects/{id}/export                 render both files; returns metadata
  - GET  /projects/{id}/export                 metadata for existing renders
  - GET  /projects/{id}/export/io-list         download the IO list xlsx
  - GET  /projects/{id}/export/ce              download the C&E draft xlsx

The render is fast (a handful of devices, a few sheets) so we run it
synchronously on POST — no background task needed at Phase 1 volume.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.api.store import get_store
from backend.export.ce import export_ce
from backend.export.io_list import export_io_list
from backend.export.sequence_doc import export_sequence_doc
from backend.model import PipelineStage


router = APIRouter(prefix="/projects/{project_id}/export", tags=["export"])


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ExportFile(BaseModel):
	filename: str
	size_bytes: int
	rendered_at: datetime


class ExportResult(BaseModel):
	io_list: ExportFile | None
	ce: ExportFile | None
	sequence_doc: ExportFile | None


def _project_or_404(project_id: str):
	state = get_store().get(project_id)
	if state is None:
		raise HTTPException(status_code=404, detail="Project not found")
	return state


def _output_dir(state) -> Path:
	return get_store().project_dir(state.project_id) / "output"


def _read_existing(state) -> ExportResult:
	"""If renders are on disk, return their metadata. Used by the GET path
	when the engineer comes back to the screen after a render has finished.
	"""
	out_dir = _output_dir(state)
	result = ExportResult(io_list=None, ce=None, sequence_doc=None)
	if not out_dir.exists():
		return result
	for p in out_dir.iterdir():
		suffix = p.suffix.lower()
		if suffix not in (".xlsx", ".docx"):
			continue
		meta = ExportFile(
			filename=p.name,
			size_bytes=p.stat().st_size,
			rendered_at=datetime.fromtimestamp(p.stat().st_mtime),
		)
		if p.name.endswith("_Ignition_IOList.xlsx"):
			result.io_list = meta
		elif p.name.endswith("_CauseAndEffect_Draft.xlsx"):
			result.ce = meta
		elif p.name.endswith("_TreatingSequence.docx"):
			result.sequence_doc = meta
	return result


@router.post("", response_model=ExportResult, summary="Render both deliverables")
def run_export(project_id: str) -> ExportResult:
	state = _project_or_404(project_id)
	if state.plant_configuration is None or state.device_model is None:
		raise HTTPException(
			status_code=409,
			detail="Plant Configuration and Device Model must exist before export.",
		)
	if state.io_template_path is None or not Path(state.io_template_path).exists():
		raise HTTPException(
			status_code=409,
			detail="IO template is missing on disk — re-upload it on the Configure screen.",
		)

	out_dir = _output_dir(state)

	io_path = export_io_list(
		template_path=state.io_template_path,
		plant=state.plant_configuration,
		model=state.device_model,
		output_dir=out_dir,
	)
	ce_path = export_ce(
		plant=state.plant_configuration,
		model=state.device_model,
		output_dir=out_dir,
		sequence_workbook_path=state.sequence_workbook_path,
	)
	seq_path = export_sequence_doc(
		plant=state.plant_configuration,
		sequence_workbook_path=state.sequence_workbook_path,
		output_dir=out_dir,
		device_model=state.device_model,
	)

	# Keep the project on EXPORT — the engineer may go back to Review and
	# re-export, per UI §4 "Re-export after a correction".
	state.stage = PipelineStage.EXPORT
	get_store().update(state)

	def _meta(p: Path) -> ExportFile:
		return ExportFile(
			filename=p.name,
			size_bytes=p.stat().st_size,
			rendered_at=datetime.fromtimestamp(p.stat().st_mtime),
		)

	return ExportResult(
		io_list=_meta(io_path),
		ce=_meta(ce_path),
		sequence_doc=_meta(seq_path) if seq_path is not None else None,
	)


@router.get("", response_model=ExportResult, summary="Metadata for existing renders")
def get_export_metadata(project_id: str) -> ExportResult:
	state = _project_or_404(project_id)
	return _read_existing(state)


@router.get("/io-list", summary="Download the IO list xlsx")
def download_io_list(project_id: str) -> FileResponse:
	state = _project_or_404(project_id)
	existing = _read_existing(state)
	if existing.io_list is None:
		raise HTTPException(status_code=404, detail="IO list has not been rendered yet.")
	path = _output_dir(state) / existing.io_list.filename
	return FileResponse(path, media_type=XLSX_MIME, filename=existing.io_list.filename)


@router.get("/ce", summary="Download the C&E draft xlsx")
def download_ce(project_id: str) -> FileResponse:
	state = _project_or_404(project_id)
	existing = _read_existing(state)
	if existing.ce is None:
		raise HTTPException(status_code=404, detail="C&E draft has not been rendered yet.")
	path = _output_dir(state) / existing.ce.filename
	return FileResponse(path, media_type=XLSX_MIME, filename=existing.ce.filename)


@router.get("/sequence-doc", summary="Download the Treating Sequence Word doc")
def download_sequence_doc(project_id: str) -> FileResponse:
	state = _project_or_404(project_id)
	existing = _read_existing(state)
	if existing.sequence_doc is None:
		raise HTTPException(status_code=404, detail="Treating Sequence document has not been rendered yet.")
	path = _output_dir(state) / existing.sequence_doc.filename
	return FileResponse(path, media_type=DOCX_MIME, filename=existing.sequence_doc.filename)
