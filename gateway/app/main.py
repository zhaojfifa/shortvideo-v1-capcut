from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

from gateway.app.providers.xiongmao import XiongmaoError, parse_with_xiongmao

app = FastAPI(title="ShortVideo Gateway", version="v1")


class ParseRequest(BaseModel):
    task_id: str | None = None
    platform: str | None = None
    link: HttpUrl


@app.post("/v1/parse")
async def parse(request: ParseRequest):
    try:
        parsed = await parse_with_xiongmao(str(request.link))
    except XiongmaoError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "task_id": request.task_id,
        "platform": request.platform,
        "title": parsed.get("title"),
        "type": parsed.get("type") or "VIDEO",
        "download_url": parsed.get("download_url"),
        "cover": parsed.get("cover"),
        "origin_text": parsed.get("origin_text"),
        "raw": parsed.get("raw"),
    }
