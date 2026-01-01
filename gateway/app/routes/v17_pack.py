from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gateway.app.core.pack_v17_youcut import generate_youcut_pack, zip_youcut_pack
from gateway.app.core.tts_edge import EdgeTTSError, generate_edge_tts_wav_from_srt
from gateway.app.config import get_settings
from gateway.app.ports.storage_provider import get_storage_service
from gateway.app.utils.keys import KeyBuilder

router = APIRouter(prefix="/v1.7/pack", tags=["v1.7-pack"])


class YouCutPackRequest(BaseModel):
    task_id: str = Field(..., min_length=1, description="Task id used as pack folder name")
    zip: bool = Field(True, description="Whether to zip the generated pack")
    placeholders: bool = Field(True, description="Create placeholder assets for Day2 acceptance")
    upload: bool = Field(False, description="Whether to upload the zip to R2/local storage")
    expires_in: int = Field(3600, description="Presigned URL expiration in seconds")
    tts: bool = Field(False, description="Whether to generate voice_my.wav via Edge TTS")
    voice: Optional[str] = Field(None, description="Edge TTS voice name")
    rate: Optional[str] = Field(None, description="Edge TTS rate, e.g. +0%")
    pitch: Optional[str] = Field(None, description="Edge TTS pitch, e.g. +0Hz")


@router.post("/youcut")
def create_youcut_pack(req: YouCutPackRequest) -> Dict[str, Any]:
    """
    Day2: generate v1.7 YouCut-ready pack skeleton + (optionally) zip.
    No side-effects beyond filesystem output. No external services.
    """
    task_id = req.task_id.strip()
    if not task_id:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "detail": "task_id is required"},
        )

    # Allow changing output root via env for testing / deployment flexibility.
    # Default remains deliver/packs to match Day1.
    out_root = Path(os.getenv("V17_PACKS_DIR", "deliver/packs"))

    try:
        pack_root = generate_youcut_pack(task_id=task_id, out_root=out_root, placeholders=req.placeholders)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "pack_failed", "detail": f"generate_youcut_pack failed: {type(e).__name__}"},
        )

    if req.tts:
        settings = get_settings()
        voice = req.voice or settings.edge_tts_voice_map.get("mm_female_1") or "my-MM-NilarNeural"
        rate = req.rate or settings.edge_tts_rate or "+0%"
        pitch = req.pitch or "+0Hz"
        srt_path = pack_root / "subs" / "my.srt"
        audio_path = pack_root / "audio" / "voice_my.wav"
        if not srt_path.exists():
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_request", "detail": "subs/my.srt not found for TTS"},
            )
        try:
            generate_edge_tts_wav_from_srt(
                srt_path,
                audio_path,
                voice=voice,
                rate=rate,
                pitch=pitch,
            )
        except EdgeTTSError as e:
            return JSONResponse(
                status_code=500,
                content={"error": "edge_tts_failed", "detail": "Edge TTS failed"},
            )

    zip_path: Optional[Path] = None
    if req.zip or req.upload:
        try:
            zip_path = zip_youcut_pack(pack_root)
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": "pack_failed", "detail": f"zip_youcut_pack failed: {type(e).__name__}"},
            )

    zip_key: Optional[str] = None
    download_url: Optional[str] = None
    if req.upload:
        if zip_path is None:
            return JSONResponse(
                status_code=500,
                content={"error": "pack_failed", "detail": "zip path is required for upload"},
            )
        try:
            storage = get_storage_service()
            zip_key = KeyBuilder.build("default", "default", task_id, "artifacts/youcut_pack_v17.zip")
            storage.upload_file(str(zip_path), zip_key, content_type="application/zip")
            try:
                download_url = storage.generate_presigned_url(
                    zip_key,
                    expiration=req.expires_in,
                    content_type="application/zip",
                    filename=f"{task_id}_youcut_pack_v17.zip",
                    disposition="attachment",
                )
            except TypeError:
                download_url = storage.generate_presigned_url(zip_key, expiration=req.expires_in)
        except Exception:
            return JSONResponse(
                status_code=500,
                content={"error": "r2_upload_failed", "detail": "upload or presign failed"},
            )

    resp: Dict[str, Any] = {
        "task_id": task_id,
        "pack_type": "youcut_ready",
        "pack_root": str(pack_root.as_posix()),
    }
    if zip_path is not None:
        resp["zip_path"] = str(zip_path.as_posix())
    if zip_key is not None:
        resp["zip_key"] = zip_key
    if download_url is not None:
        resp["download_url"] = download_url

    return resp
