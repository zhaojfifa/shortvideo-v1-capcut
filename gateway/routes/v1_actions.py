"""Thin v1 action routes for Pipeline Lab (POST only)."""

from fastapi import APIRouter

from gateway.app.schemas import DubRequest, PackRequest, ParseRequest, SubtitlesRequest
from gateway.app.services.steps_v1 import (
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)

router = APIRouter()


@router.post("/parse")
async def parse(request: ParseRequest):
    return await run_parse_step(request)


@router.post("/subtitles")
async def subtitles(request: SubtitlesRequest):
    return await run_subtitles_step(request)


@router.post("/dub")
async def dub(request: DubRequest):
    return await run_dub_step(request)


@router.post("/pack")
async def pack(request: PackRequest):
    return await run_pack_step(request)
