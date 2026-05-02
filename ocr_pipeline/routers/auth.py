"""HuggingFace OAuth routes. Mounted only when OAuth is configured.

When OAuth is disabled the `/api/auth/me` endpoint still works and reports
`enabled: false` so the frontend can hide the sign-in button cleanly.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ocr_pipeline.services.auth_session import (
    SESS_OAUTH_STATE,
    build_authorize_url,
    clear_session,
    exchange_code,
    is_oauth_enabled,
    new_state,
    session_user,
    store_session,
)

logger = logging.getLogger("ocr_pipeline.auth")
router = APIRouter()


@router.get("/api/auth/me")
async def auth_me(request: Request):
    user = session_user(request.session) if hasattr(request, "session") else None
    return {
        "enabled": is_oauth_enabled(),
        "authenticated": user is not None,
        "user": (
            {
                "name": user.name,
                "picture": user.picture,
                "profile": user.profile,
            }
            if user
            else None
        ),
    }


@router.get("/api/auth/login")
async def auth_login(request: Request):
    if not is_oauth_enabled():
        raise HTTPException(status_code=501, detail="HuggingFace OAuth is not configured.")
    state = new_state()
    request.session[SESS_OAUTH_STATE] = state
    return RedirectResponse(build_authorize_url(state))


@router.get("/api/auth/callback")
async def auth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        raise HTTPException(status_code=400, detail=f"HuggingFace returned error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    expected_state = request.session.pop(SESS_OAUTH_STATE, None)
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=400, detail="OAuth state mismatch — request rejected.")

    try:
        token_payload = await exchange_code(code)
    except Exception as exc:
        logger.exception("HF OAuth exchange failed")
        raise HTTPException(status_code=502, detail=f"OAuth exchange failed: {exc}")

    store_session(
        request.session,
        access_token=token_payload["access_token"],
        expires_in=token_payload.get("expires_in"),
        userinfo=token_payload.get("userinfo") or {},
    )
    return RedirectResponse("/")


@router.post("/api/auth/logout")
async def auth_logout(request: Request):
    clear_session(request.session)
    return {"ok": True}
