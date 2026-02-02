from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gateway.app.web.templates import render_template

router = APIRouter()


@router.get("/tasks/hot-follow", response_class=HTMLResponse)
async def hot_follow_tasks_page(request: Request) -> HTMLResponse:
    return render_template(request=request, name="hot_follow.html")


@router.get("/tasks/hot-follow/new", response_class=HTMLResponse)
async def hot_follow_new_page(request: Request) -> HTMLResponse:
    return render_template(request=request, name="hot_follow_new.html")
