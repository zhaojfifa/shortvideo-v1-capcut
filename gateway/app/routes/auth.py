from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gateway.app.auth import (
    COOKIE_NAME,
    issue_session,
    is_admin,
    load_auth_settings,
    scopes_for_role,
    verify_op_key,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    key: str


@router.post("/login")
def login(body: LoginBody):
    s = load_auth_settings()
    if not verify_op_key(body.key, s.op_access_key):
        return JSONResponse(status_code=401, content={"detail": "Invalid key"})

    role = "admin" if body.username.strip().lower() == "admin" else "operator"
    token = issue_session(body.username, role, s.session_ttl_seconds, s.session_secret)

    resp = JSONResponse(content={"ok": True, "username": body.username, "role": role})
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=s.session_ttl_seconds,
    )
    return resp


@router.post("/logout")
def logout():
    resp = JSONResponse(content={"ok": True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/me")
def me(request: Request):
    role = getattr(request.state, "role", None)
    op = getattr(request.state, "op", None)
    scopes = getattr(request.state, "scopes", None)
    if not role:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return {"username": op, "role": role, "scopes": list(scopes or [])}
