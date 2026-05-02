"""HuggingFace OAuth helpers.

Optional. When `HF_OAUTH_CLIENT_ID` is set, OpenCR enables a "Sign in with
HuggingFace" flow whose tokens drive the publish UI. When unset, the publish
flow falls back to the paste-token form (and `/api/auth/me` reports
`enabled: false`).

Why OAuth and not just env-token-everywhere:
- Multi-user deployments shouldn't share one long-lived token.
- The token's repo permissions match the signed-in user, so users can only
  push to repos they actually own.
- It's the basis for "gating" the panel — anonymous visitors see read-only.
"""
from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ocr_pipeline.config import settings

logger = logging.getLogger("ocr_pipeline.auth")

HF_AUTHORIZE_URL = "https://huggingface.co/oauth/authorize"
HF_TOKEN_URL = "https://huggingface.co/oauth/token"
HF_USERINFO_URL = "https://huggingface.co/oauth/userinfo"

# Session cookie keys — kept short to fit the cookie size budget.
SESS_USER = "u"           # dict: {name, picture, ...}
SESS_TOKEN = "t"          # str: HF access token
SESS_EXPIRES_AT = "e"     # float: epoch seconds
SESS_OAUTH_STATE = "s"    # str: CSRF state during the redirect dance


@dataclass
class HFUser:
    name: str
    picture: str | None = None
    profile: str | None = None
    email: str | None = None


def is_oauth_enabled() -> bool:
    return bool(settings.hf_oauth_client_id and settings.hf_oauth_client_secret)


def build_authorize_url(state: str) -> str:
    from urllib.parse import urlencode
    params = {
        "client_id": settings.hf_oauth_client_id,
        "redirect_uri": settings.hf_oauth_redirect_uri,
        "response_type": "code",
        "scope": settings.hf_oauth_scopes,
        "state": state,
    }
    return f"{HF_AUTHORIZE_URL}?{urlencode(params)}"


def new_state() -> str:
    return secrets.token_urlsafe(24)


async def exchange_code(code: str) -> dict[str, Any]:
    """Trade an auth code for an access token + userinfo."""
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            HF_TOKEN_URL,
            data={
                "client_id": settings.hf_oauth_client_id,
                "client_secret": settings.hf_oauth_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.hf_oauth_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError("HF token endpoint returned no access_token")

        info_resp = await client.get(
            HF_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info_resp.raise_for_status()
        userinfo = info_resp.json()

    return {
        "access_token": access_token,
        "expires_in": token_data.get("expires_in"),
        "userinfo": userinfo,
    }


def store_session(session: dict, *, access_token: str, expires_in: int | None, userinfo: dict) -> None:
    """Persist auth state on the request's session dict."""
    session[SESS_TOKEN] = access_token
    session[SESS_USER] = {
        "name": userinfo.get("preferred_username") or userinfo.get("name") or "anonymous",
        "picture": userinfo.get("picture"),
        "profile": userinfo.get("profile"),
        "email": userinfo.get("email"),
        "orgs": [o.get("name") for o in (userinfo.get("orgs") or []) if o.get("name")],
    }
    if expires_in:
        session[SESS_EXPIRES_AT] = time.time() + int(expires_in)


def clear_session(session: dict) -> None:
    for key in (SESS_USER, SESS_TOKEN, SESS_EXPIRES_AT, SESS_OAUTH_STATE):
        session.pop(key, None)


def session_user(session: dict) -> HFUser | None:
    if not session.get(SESS_TOKEN):
        return None
    expires_at = session.get(SESS_EXPIRES_AT)
    if expires_at and time.time() > float(expires_at):
        clear_session(session)
        return None
    user = session.get(SESS_USER) or {}
    return HFUser(
        name=user.get("name", "anonymous"),
        picture=user.get("picture"),
        profile=user.get("profile"),
        email=user.get("email"),
    )


def session_token(session: dict) -> str | None:
    if session_user(session) is None:
        return None
    return session.get(SESS_TOKEN)
