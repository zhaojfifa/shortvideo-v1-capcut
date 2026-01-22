import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional, Set

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

DEFAULT_HEADER_NAME = "X-OP-KEY"
COOKIE_NAME = "op_session"

ROLE_SCOPES = {
    "admin": {"admin:write", "tools:read", "tasks:read", "tasks:write", "publish:read"},
    "operator": {"tools:read", "tasks:read", "tasks:write", "publish:read"},
    "viewer": {"tools:read", "tasks:read", "publish:read"},
}


@dataclass
class AuthSettings:
    auth_mode: str
    op_access_key: str
    session_secret: str
    session_ttl_seconds: int
    header_name: str


def load_auth_settings() -> AuthSettings:
    auth_mode = os.getenv("AUTH_MODE", "both").strip().lower()
    op_access_key = os.getenv("OP_ACCESS_KEY", "").strip()
    session_secret = os.getenv("SESSION_SECRET", "").strip()
    ttl = int(os.getenv("SESSION_TTL_SECONDS", "43200"))
    header_name = os.getenv("OP_KEY_HEADER", DEFAULT_HEADER_NAME).strip() or DEFAULT_HEADER_NAME

    if auth_mode in ("header", "both") and not op_access_key:
        raise RuntimeError("AUTH misconfigured: OP_ACCESS_KEY is required for AUTH_MODE=header|both")
    if auth_mode in ("session", "both") and not session_secret:
        raise RuntimeError("AUTH misconfigured: SESSION_SECRET is required for AUTH_MODE=session|both")

    return AuthSettings(
        auth_mode=auth_mode,
        op_access_key=op_access_key,
        session_secret=session_secret,
        session_ttl_seconds=ttl,
        header_name=header_name,
    )


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def sign_session(payload: dict[str, Any], secret: str) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), data, hashlib.sha256).digest()
    return f"{_b64url_encode(data)}.{_b64url_encode(sig)}"


def verify_session(token: str, secret: str) -> Optional[dict[str, Any]]:
    try:
        data_b64, sig_b64 = token.split(".", 1)
        data = _b64url_decode(data_b64)
        sig = _b64url_decode(sig_b64)
        expected = hmac.new(secret.encode("utf-8"), data, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(data.decode("utf-8"))
        exp = int(payload.get("exp", 0))
        if exp and time.time() > exp:
            return None
        return payload
    except Exception:
        return None


def issue_session(op_name: str, role: str, ttl_seconds: int, secret: str) -> str:
    now = int(time.time())
    payload = {
        "op": op_name,
        "role": role,
        "exp": now + ttl_seconds,
        "iat": now,
        "v": 1,
    }
    return sign_session(payload, secret)


def scopes_for_role(role: str) -> Set[str]:
    return set(ROLE_SCOPES.get(role, set()))


def verify_op_key(header_value: Optional[str], expected_key: str) -> bool:
    if not header_value or not expected_key:
        return False
    return hmac.compare_digest(header_value.strip(), expected_key)


def is_admin(role: str | None) -> bool:
    return (role or "").strip().lower() == "admin"


def deny_admin(request: Request):
    if request.url.path.startswith("/api/") or request.url.path.startswith("/v1/"):
        return JSONResponse(status_code=403, content={"detail": "Admin only"})
    return JSONResponse(status_code=403, content={"detail": "Admin only"})


def require_admin(request: Request):
    role = getattr(request.state, "role", None)
    if not is_admin(role):
        raise RuntimeError("ADMIN_ONLY")


def require_operator_session(request: Request) -> None:
    role = getattr(request.state, "role", None)
    if not role:
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_admin_session(request: Request) -> None:
    role = getattr(request.state, "role", None)
    if not is_admin(role):
        raise HTTPException(status_code=403, detail="Admin only")
