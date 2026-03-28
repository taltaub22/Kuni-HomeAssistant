"""AWS Cognito USER_SRP_AUTH login and refresh (Kuni / Aroma Republic app flow)."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Final

from aiohttp import ClientSession

from .const import (
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    COGNITO_USER_POOL_ID,
)

_LOGGER = logging.getLogger(__name__)

COGNITO_IDP_URL: Final = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"


class KuniAuthError(Exception):
    """Raised when Cognito rejects credentials or token refresh fails."""


def _strip_bearer(token: str) -> str:
    t = token.strip()
    if t.lower().startswith("bearer "):
        return t[7:].strip()
    return t


def jwt_exp_unix(token: str) -> int | None:
    """Return JWT exp claim (seconds since epoch) without verifying signature."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        pad = "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(payload_b64 + pad)
        payload = json.loads(raw.decode("utf-8"))
        exp = payload.get("exp")
        return int(exp) if exp is not None else None
    except (ValueError, json.JSONDecodeError, OSError):
        return None


def build_cognito_username(organization_id: str, email: str) -> str:
    """Match app format: tenant-{uuid}-{email}."""
    org = organization_id.strip()
    em = email.strip()
    return f"{org}-{em}"


def sync_srp_authenticate(username: str, password: str) -> dict[str, str]:
    """Run Cognito USER_SRP_AUTH (same flow as InitiateAuth → RespondToAuthChallenge)."""
    try:
        from pycognito import Cognito
    except ImportError as err:
        raise RuntimeError(
            "The pycognito package failed to import; check custom component requirements"
        ) from err

    user = Cognito(
        COGNITO_USER_POOL_ID,
        COGNITO_CLIENT_ID,
        user_pool_region=COGNITO_REGION,
        username=username,
    )
    try:
        user.authenticate(password=password)
    except Exception as err:
        err_s = str(err).lower()
        _LOGGER.debug("Cognito authenticate failed: %s", err, exc_info=True)
        if (
            "notauthorized" in err_s
            or "not authorized" in err_s
            or "incorrect username or password" in err_s
            or "incorrect username" in err_s
        ):
            raise KuniAuthError("invalid_credentials") from err
        raise KuniAuthError("auth_failed") from err

    refresh = getattr(user, "refresh_token", None) or ""
    access = user.access_token or ""
    id_tok = user.id_token or ""
    if not access or not id_tok:
        raise KuniAuthError("auth_failed")
    return {
        "access_token": access,
        "id_token": id_tok,
        "refresh_token": refresh,
    }


async def async_refresh_tokens(
    session: ClientSession,
    refresh_token: str,
) -> dict[str, str]:
    """REFRESH_TOKEN_AUTH — returns new access + id tokens."""
    headers = {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
    }
    body: dict[str, Any] = {
        "AuthFlow": "REFRESH_TOKEN_AUTH",
        "ClientId": COGNITO_CLIENT_ID,
        "AuthParameters": {"REFRESH_TOKEN": _strip_bearer(refresh_token)},
    }
    async with session.post(COGNITO_IDP_URL, headers=headers, json=body) as resp:
        text = await resp.text()
        if resp.status >= 400:
            _LOGGER.debug("Cognito refresh HTTP %s: %s", resp.status, text[:400])
            raise KuniAuthError("refresh_failed")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            raise KuniAuthError("refresh_failed") from err

    auth = data.get("AuthenticationResult") or {}
    access = auth.get("AccessToken") or ""
    id_tok = auth.get("IdToken") or ""
    if not access or not id_tok:
        raise KuniAuthError("refresh_failed")
    return {"access_token": access, "id_token": id_tok}


def token_needs_refresh(access_token: str, *, skew_seconds: int = 300) -> bool:
    """True if access token is missing or expires within skew_seconds."""
    if not access_token:
        return True
    exp = jwt_exp_unix(access_token)
    if exp is None:
        return True
    return exp <= int(time.time()) + skew_seconds
