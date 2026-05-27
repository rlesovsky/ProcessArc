"""FastAPI route for the Plant Bundle Builder.

Single endpoint: POST /api/ignition-tags/build-plant
  multipart/form-data:
    plant_config: JSON string with site identity + cylinder/mix counts
    xlsx_file:    (optional) the populated PLC-team xlsx

  → 200: application/json
         {
           "bundle":            { "<site>": <nested-folder-tree> },
           "validation_report": { "errors": [], "warnings": [...] },
           "site":              "<long site name>",
           "instance_count":    <int>
         }

  → 400: { "error": str, "validation_report": ValidationReport }

Same response envelope as the existing /build endpoint so the frontend
can render the validation panel and tree preview with the same
components.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .plant_builder import build_plant_bundle


router = APIRouter(prefix="/api/ignition-tags", tags=["ignition-tags"])


@router.post(
	"/build-plant",
	summary="Build a complete Ignition tag bundle for a new UFP plant",
)
async def build_plant_route(
	plant_config: str = Form(..., description="JSON string of the plant config object."),
	xlsx_file: UploadFile | None = File(default=None),
) -> JSONResponse:
	# Decode the plant_config form part. The frontend sends it as a JSON
	# string inside a multipart field rather than splitting every field
	# into its own form key — that keeps cylinder/mix nesting structured
	# and matches the request body shape in the design doc.
	try:
		config: dict[str, Any] = json.loads(plant_config)
	except json.JSONDecodeError as exc:
		raise HTTPException(
			status_code=400,
			detail=f"plant_config is not valid JSON: {exc}",
		) from exc

	if not isinstance(config, dict):
		raise HTTPException(
			status_code=400,
			detail="plant_config must be a JSON object, not a list or scalar.",
		)

	xlsx_bytes: bytes | None = None
	if xlsx_file is not None:
		# UploadFile with no file selected on the form still arrives as
		# an UploadFile, but its `filename` is empty and `read()` returns
		# zero bytes. Treat that as "no xlsx supplied" rather than as a
		# zero-byte upload error.
		raw = await xlsx_file.read()
		if raw:
			xlsx_bytes = raw

	bundle, report, site, instance_count = build_plant_bundle(config, xlsx_bytes)

	if report.has_errors:
		return JSONResponse(
			status_code=400,
			content={
				"error": "Plant config validation failed.",
				"validation_report": report.model_dump(),
			},
		)

	return JSONResponse(
		status_code=200,
		content={
			"bundle": bundle,
			"validation_report": report.model_dump(),
			"site": site,
			"instance_count": instance_count,
		},
	)
