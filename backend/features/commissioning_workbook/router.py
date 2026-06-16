"""FastAPI routes for the Commissioning Workbook Builder.

POST /api/commissioning-workbook/build
  multipart/form-data:  source=<source xlsx>
                        template=<optional override xlsx>
  Headers in response:  X-Build-Report: base64(json(BuildReport))
  → 200: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
         (the populated workbook as a download)
  → 400: { "error": str }
  → 500: server-side bug

GET /api/commissioning-workbook/default-template
  → 200: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
         (the bundled canonical template)

The build endpoint hands back the BuildReport in a custom header so
the frontend can render the change log alongside the download button
without a second round-trip.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from .builder import build_workbook
from .parser import parse_source

router = APIRouter(
    prefix="/api/commissioning-workbook",
    tags=["commissioning-workbook"],
)

TEMPLATE_DIR = Path(__file__).parent / "templates"
DEFAULT_TEMPLATE_PATH = TEMPLATE_DIR / "default_commissioning_workbook.xlsx"
DEFAULT_TEMPLATE_FILENAME = "default_commissioning_workbook.xlsx"

# A spreadsheetml MIME type long enough that we centralize it.
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/default-template",
    summary="Download the bundled CommWKBK template (the multi-sheet sign-off doc)",
)
def default_template() -> FileResponse:
    if not DEFAULT_TEMPLATE_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                f"CommWKBK template not found at {DEFAULT_TEMPLATE_PATH}. "
                "If this is the bundled .exe, the templates/ directory "
                "may be missing from the PyInstaller spec."
            ),
        )
    return FileResponse(
        DEFAULT_TEMPLATE_PATH,
        media_type=XLSX_MIME,
        filename=DEFAULT_TEMPLATE_FILENAME,
    )


@router.post(
    "/build",
    summary="Populate the CommWKBK from a customer write-up workbook",
)
async def build(
    source: UploadFile = File(..., description="Customer write-up xlsx (Graphics and Tables style)"),
    template: UploadFile | None = File(
        None,
        description="Optional CommWKBK template override. If omitted, the bundled default is used.",
    ),
) -> StreamingResponse:
    source_bytes = await source.read()
    if not source_bytes:
        raise HTTPException(status_code=400, detail="Source workbook is empty.")

    # Template: explicit upload wins; otherwise read from disk.
    if template is not None:
        template_bytes = await template.read()
        if not template_bytes:
            raise HTTPException(status_code=400, detail="Template override is empty.")
        template_name = template.filename or "uploaded_template.xlsx"
    else:
        if not DEFAULT_TEMPLATE_PATH.is_file():
            raise HTTPException(
                status_code=500,
                detail="Bundled CommWKBK template is missing on the server.",
            )
        template_bytes = DEFAULT_TEMPLATE_PATH.read_bytes()
        template_name = DEFAULT_TEMPLATE_FILENAME

    try:
        parsed = parse_source(source_bytes)
    except Exception as exc:  # pragma: no cover — defensive
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse source workbook: {exc}",
        ) from exc

    try:
        new_bytes, report = build_workbook(parsed, template_bytes, template_name)
    except Exception as exc:  # pragma: no cover — defensive
        raise HTTPException(
            status_code=500,
            detail=f"Builder crashed: {exc}",
        ) from exc

    # Encode the BuildReport as base64-JSON in a response header so the
    # frontend can render the change-log panel without a second request.
    # base64 because headers must be ASCII and the change log may have
    # unicode quotes.
    report_json = json.dumps(report.model_dump(), ensure_ascii=False)
    report_b64 = base64.b64encode(report_json.encode("utf-8")).decode("ascii")

    out_filename = _derive_filename(source.filename or "workbook.xlsx")
    return StreamingResponse(
        io.BytesIO(new_bytes),
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{out_filename}"',
            "X-Build-Report": report_b64,
            # Expose the custom header to the browser fetch client.
            "Access-Control-Expose-Headers": "X-Build-Report, Content-Disposition",
        },
    )


def _derive_filename(source_name: str) -> str:
    """Pick a friendly output filename based on the source filename.

    'Union City Graphics and Tables.xlsx' → 'Union City CommWKBK_filled.xlsx'.
    Falls back to a generic name if we can't recognize the pattern.
    """
    base = Path(source_name).stem
    # Strip the trailing "Graphics and Tables" / "Graphics+Tables" suffix
    # if present.
    for suffix in (" Graphics and Tables", " Graphics+Tables", " Graphics"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base} CommWKBK_filled.xlsx"
