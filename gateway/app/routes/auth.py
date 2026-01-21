from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from gateway.app.auth import (
    COOKIE_NAME,
    issue_session,
    load_auth_settings,
    verify_op_key,
)

router = APIRouter()
templates = Jinja2Templates(directory="gateway/app/templates")


def role_for_operator(name: str) -> str:
    return "admin" if name.strip().lower() == "admin" else "operator"


@router.get("/auth/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/tasks"):
    return templates.TemplateResponse(
        "auth_login.html",
        {"request": request, "next": next},
    )


@router.post("/auth/login")
def login(
    request: Request,
    operator: str = Form(...),
    key: str = Form(...),
    next: str = Form("/tasks"),
):
    s = load_auth_settings()
    if not verify_op_key(key, s.op_access_key):
        return templates.TemplateResponse(
            "auth_login.html",
            {"request": request, "next": next, "error": "Invalid key"},
            status_code=401,
        )

    role = role_for_operator(operator)
    token = issue_session(operator, role, s.session_ttl_seconds, s.session_secret)

    resp = RedirectResponse(url=next or "/tasks", status_code=302)
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=s.session_ttl_seconds,
    )
    return resp


@router.post("/auth/logout")
def logout():
    resp = RedirectResponse(url="/auth/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp
