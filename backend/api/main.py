"""ProcessArc backend — FastAPI entrypoint.

Run from the ProcessArc/ project root:

	source backend/.venv/bin/activate
	uvicorn backend.api.main:app --reload --port 8000

The React frontend (Vite, port 5173) talks to this over plain HTTP on localhost.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.settings import get_settings

from .routers import (
	export as export_router,
	extract as extract_router,
	projects,
	settings as settings_router,
)


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
