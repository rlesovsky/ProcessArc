"""FastAPI route for the Ignition Tag Builder.

Single endpoint: POST /api/ignition-tags/build
  multipart/form-data: file=<xlsx>

  → 200: application/json
         {
           "bundle":            { "<base_path>": [instance, ...], ... },
           "validation_report": { "errors": [], "warnings": [...] },
           "site":              "<site name, for filename hints>",
           "instance_count":    <int>
         }

         The frontend renders `validation_report` in its panel and
         saves only the `bundle` field when the user downloads. That
         keeps the download a pure Ignition-importable JSON object
         (no metadata wrapping inside the downloaded file).

  → 400: { "error": str, "validation_report": ValidationReport }
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .builder import build_all
from .packager import build_ignition_tree
from .parser import parse_workbook

router = APIRouter(prefix="/api/ignition-tags", tags=["ignition-tags"])


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
