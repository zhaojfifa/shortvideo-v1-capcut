from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

from gateway.app.core.workspace import raw_path
from gateway.app.providers.xiongmao import XiongmaoError, parse_with_xiongmao
from gateway.app.services.download import DownloadError, download_raw_video
from gateway.app.services.subtitles import SubtitleError, generate_subtitles

app = FastAPI(title="ShortVideo Gateway", version="v1")


class ParseRequest(BaseModel):
    task_id: str
    platform: str | None = None
    link: HttpUrl


class SubtitlesRequest(BaseModel):
    task_id: str
    target_lang: str = "my"
    force: bool = False
    translate: bool = True


@app.post("/v1/parse")
async def parse(request: ParseRequest):
    try:
        parsed = await parse_with_xiongmao(str(request.link))
        raw_file = await download_raw_video(request.task_id, parsed.get("download_url") or "")
    except XiongmaoError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except DownloadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    relative_raw = Path("raw") / f"{request.task_id}.mp4"

    return {
        "task_id": request.task_id,
        "platform": request.platform,
        "title": parsed.get("title"),
        "type": parsed.get("type") or "VIDEO",
        "download_url": parsed.get("download_url"),
        "cover": parsed.get("cover"),
        "origin_text": parsed.get("origin_text"),
        "raw": parsed.get("raw"),
        "raw_exists": raw_file.exists(),
        "raw_path": str(relative_raw),
    }


@app.get("/v1/tasks/{task_id}/raw")
async def get_raw(task_id: str):
    path = raw_path(task_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="raw video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"{task_id}.mp4")


@app.post("/v1/subtitles")
async def subtitles(request: SubtitlesRequest):
    raw_file = raw_path(request.task_id)
    if not raw_file.exists():
        raise HTTPException(status_code=404, detail="raw video not found")

    try:
        result = generate_subtitles(
            task_id=request.task_id,
            raw_video=raw_file,
            target_lang=request.target_lang,
            force=request.force,
            translate_enabled=request.translate,
        )
    except SubtitleError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "task_id": request.task_id,
        "target_lang": request.target_lang,
        "audio_path": result.get("audio_path"),
        "origin_srt": result.get("origin_srt"),
        "translated_srt": result.get("translated_srt"),
    }
