"""ProcessArc backend — FastAPI entrypoint.

Run from the ProcessArc/ project root:

	source backend/.venv/bin/activate
	uvicorn backend.api.main:app --reload --port 8000

The React frontend (Vite, port 5173) talks to this over plain HTTP on localhost.

In the bundled desktop build (PyInstaller .exe), the built React assets
in ``frontend/dist/`` are shipped inside the bundle and mounted at ``/``
by this same app, so the entire UI is served from the same origin as
the API. Dev mode (no ``frontend/dist/`` on disk) is unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.features.ignition_tags.plant_router import router as plant_bundle_router
from backend.features.commissioning_workbook.router import router as commissioning_workbook_router
from backend.features.ignition_tags.router import router as ignition_tags_router
from backend.settings import get_settings

from .routers import (
	export as export_router,
	extract as extract_router,
	projects,
	settings as settings_router,
)


def _frontend_dist_dir() -> Path | None:
	"""Locate the built React assets, if present.

	Search order:
	1. PyInstaller bundle: ``<sys._MEIPASS>/frontend/dist`` (the spec file
	   adds the directory under that path).
	2. Source checkout: ``<repo>/frontend/dist`` (created by ``npm run
	   build``). Useful for testing the bundled-static-serve flow without
	   actually building a .exe.

	Returns ``None`` if neither exists — in that case the app behaves
	exactly as the historical dev setup (API only, frontend served by
	Vite on :5173).
	"""
	meipass = getattr(sys, "_MEIPASS", None)
	if meipass:
		bundled = Path(meipass) / "frontend" / "dist"
		if bundled.is_dir():
			return bundled
	# Source checkout fallback. backend/api/main.py → backend/api → backend → <repo>
	repo_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
	if repo_dist.is_dir():
		return repo_dist
	return None


app = FastAPI(
	title="ProcessArc",
	description="UFP wood treatment project automation tool — Phase 1 backend.",
	version="0.1.0",
)

# Local-only frontend — Vite dev server defaults
app.add_middleware(
	CORSMiddleware,
	allow_origins=[
		"http://localhost:5173",
		"http://127.0.0.1:5173",
	],
	allow_credentials=False,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
	s = get_settings()
	return {
		"status": "ok",
		"version": "0.1.0",
		"has_api_key": s.has_api_key,
		"claude_model": s.claude_model,
	}


app.include_router(projects.router)
app.include_router(settings_router.router)
app.include_router(extract_router.router)
app.include_router(export_router.router)
app.include_router(ignition_tags_router)
app.include_router(commissioning_workbook_router)
app.include_router(plant_bundle_router)


# Serve the built React app (desktop / bundled mode). Mounted last so all
# API routes above take precedence. The SPA fallback below ensures any
# unknown non-API path returns index.html, which is the standard pattern
# for client-side routers (React Router, etc.) — harmless even though
# this app currently uses tab-based routing inside a single page.
_dist = _frontend_dist_dir()
if _dist is not None:
	# StaticFiles with html=True will:
	# - serve files under /static/* etc. by filename
	# - return index.html for GET / automatically
	# It does NOT however serve index.html for arbitrary client-side
	# routes like /some/unknown/path — that's what the explicit
	# fallback below handles.
	app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

	# Specific top-level files (favicon, logo, etc.) shipped in dist root,
	# plus a fallback that returns index.html for any unmatched non-API
	# path (standard SPA pattern; harmless for this app since it routes
	# client-side within a single page).
	@app.get("/{filename:path}", include_in_schema=False)
	def _spa_fallback(filename: str) -> FileResponse:
		"""Serve dist/<filename> if it exists, otherwise dist/index.html.

		Runs only for paths that didn't match any earlier API route
		because FastAPI tries registered routes in order.
		"""
		index = _dist / "index.html"
		if not filename:
			return FileResponse(index)
		# Resolve and confirm the target is still inside _dist to block
		# path-traversal attempts (e.g. ../../etc/passwd). On a desktop
		# app served on localhost this is mostly defensive but trivial
		# to enforce.
		try:
			target = (_dist / filename).resolve()
			target.relative_to(_dist.resolve())
		except (ValueError, OSError):
			return FileResponse(index)
		if target.is_file():
			return FileResponse(target)
		return FileResponse(index)
