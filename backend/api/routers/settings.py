"""Settings endpoints — let the engineer manage the Anthropic API key from the UI.

The raw key is only ever read by the backend (Plan §3 boundary). The frontend
sees a `configured` flag and a masked tail; the secret itself never leaves the
server after it has been saved.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.settings import get_settings, reload_settings, upsert_env_var


router = APIRouter(prefix="/settings", tags=["settings"])


def _mask(key: str) -> str | None:
    if not key or key.startswith("sk-ant-replace"):
        return None
    tail = key[-4:] if len(key) >= 4 else key
    return f"sk-ant-…{tail}"


class ApiKeyStatus(BaseModel):
    configured: bool
    masked: str | None
    model: str


class ApiKeyUpdate(BaseModel):
    api_key: str = Field(..., min_length=1)


@router.get("/api-key", response_model=ApiKeyStatus, summary="Anthropic API key status (masked)")
def get_api_key_status() -> ApiKeyStatus:
    s = get_settings()
    return ApiKeyStatus(
        configured=s.has_api_key,
        masked=_mask(s.anthropic_api_key),
        model=s.claude_model,
    )


@router.put("/api-key", response_model=ApiKeyStatus, summary="Save the Anthropic API key")
def put_api_key(body: ApiKeyUpdate) -> ApiKeyStatus:
    key = body.api_key.strip()
    if not key.startswith("sk-ant-"):
        raise HTTPException(status_code=400, detail="API key must start with 'sk-ant-'.")
    if key.startswith("sk-ant-replace"):
        raise HTTPException(status_code=400, detail="That's the placeholder value, not a real key.")
    if len(key) < 20:
        raise HTTPException(status_code=400, detail="API key looks too short to be valid.")

    upsert_env_var("ANTHROPIC_API_KEY", key)
    s = reload_settings()
    return ApiKeyStatus(
        configured=s.has_api_key,
        masked=_mask(s.anthropic_api_key),
        model=s.claude_model,
    )


@router.delete("/api-key", response_model=ApiKeyStatus, summary="Clear the saved Anthropic API key")
def delete_api_key() -> ApiKeyStatus:
    upsert_env_var("ANTHROPIC_API_KEY", "")
    s = reload_settings()
    return ApiKeyStatus(
        configured=s.has_api_key,
        masked=_mask(s.anthropic_api_key),
        model=s.claude_model,
    )
