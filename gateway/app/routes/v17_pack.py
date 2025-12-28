from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gateway.app.core.pack_v17_youcut import generate_youcut_pack, zip_youcut_pack

router = APIRouter(prefix="/v1.7/pack", tags=["v1.7-pack"])


class YouCutPackRequest(BaseModel):
    task_id: str = Field(..., min_length=1, description="Task id used as pack folder name")
    zip: bool = Field(True, description="Whether to zip the generated pack")
    placeholders: bool = Field(True, description="Create placeholder assets for Day2 acceptance")


@router.post("/youcut")
def create_youcut_pack(req: YouCutPackRequest) -> Dict[str, Any]:
    """
    Day2: generate v1.7 YouCut-ready pack skeleton + (optionally) zip.
    No side-effects beyond filesystem output. No external services.
    """
    task_id = req.task_id.strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id is required")

    # Allow changing output root via env for testing / deployment flexibility.
    # Default remains deliver/packs to match Day1.
    out_root = Path(os.getenv("V17_PACKS_DIR", "deliver/packs"))

    try:
        pack_root = generate_youcut_pack(task_id=task_id, out_root=out_root, placeholders=req.placeholders)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"generate_youcut_pack failed: {type(e).__name__}: {e}")

    zip_path: Optional[Path] = None
    if req.zip:
        try:
            zip_path = zip_youcut_pack(pack_root)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"zip_youcut_pack failed: {type(e).__name__}: {e}")

    resp: Dict[str, Any] = {
        "task_id": task_id,
        "pack_type": "youcut_ready",
        "pack_root": str(pack_root.as_posix()),
    }
    if zip_path is not None:
        resp["zip_path"] = str(zip_path.as_posix())

    return resp
