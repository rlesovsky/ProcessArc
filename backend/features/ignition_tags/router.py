"""FastAPI routes for the Ignition Tag Builder.

POST /api/ignition-tags/build
  multipart/form-data: file=<xlsx>

  → 200: application/json with bundle + validation_report + site + count
  → 400: { "error": str, "validation_report": ValidationReport }

GET  /api/ignition-tags/default-template
  → 200: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
         The committed default Ignition tag-list template. The
         frontend auto-loads this on mount so a fresh visit to the
         Build-from-xlsx tab is already pre-filled — the user can
         click Build right away, or replace the file if they have
         a different template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .builder import build_all
from .packager import build_ignition_tree
from .parser import parse_workbook

router = APIRouter(prefix="/api/ignition-tags", tags=["ignition-tags"])

# Committed default Ignition tag-list template. Bundled into the
# Windows .exe via the `datas` entry in processarc.spec — keep both
# in sync (see docs/windows_build.md for the bundling pattern).
DEFAULT_TEMPLATE_PATH = (
	Path(__file__).parent / "defaults" / "default_template.xlsx"
)
DEFAULT_TEMPLATE_FILENAME = "default_template.xlsx"


@router.get(
	"/default-template",
	summary="Download the committed default Ignition tag-list template",
)
def default_template() -> FileResponse:
	if not DEFAULT_TEMPLATE_PATH.is_file():
		# Shouldn't happen — the file is committed and bundled — but
		# fail with a clear message rather than an opaque 500 if it does.
		raise HTTPException(
			status_code=404,
			detail=(
				f"Default template not found at {DEFAULT_TEMPLATE_PATH}. "
				"If this is the Windows .exe build, the `defaults/` "
				"directory may be missing from the PyInstaller spec."
			),
		)
	return FileResponse(
		DEFAULT_TEMPLATE_PATH,
		media_type=(
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
		),
		filename=DEFAULT_TEMPLATE_FILENAME,
	)


@router.post(
	"/build",
	summary="Build Ignition UDT-instance JSON from an .xlsx template",
)
async def build_ignition_tags(file: UploadFile = File(...)) -> JSONResponse:
	file_bytes = await file.read()
	if not file_bytes:
		raise HTTPException(status_code=400, detail="Uploaded file is empty.")

	try:
		parsed = parse_workbook(file_bytes)
	except Exception as exc:  # pragma: no cover — defensive only
		raise HTTPException(
			status_code=400,
			detail=f"Could not read uploaded workbook: {exc}",
		) from exc

	instances, report = build_all(parsed)

	if report.has_errors:
		# 400 + structured validation report so the UI can show each
		# issue with sheet/row/column context. JSONResponse so the
		# report sits at the top of the body, not nested under `detail`.
		payload: dict[str, Any] = {
			"error": "Workbook failed validation.",
			"validation_report": report.model_dump(),
		}
		return JSONResponse(status_code=400, content=payload)

	return JSONResponse(
		status_code=200,
		content={
			# Single nested folder tree, ready to import in Ignition
			# Designer via Tag Browser → right-click → Import.
			"bundle": build_ignition_tree(instances),
			"validation_report": report.model_dump(),
			"site": parsed.site,
			"instance_count": len(instances),
		},
	)
