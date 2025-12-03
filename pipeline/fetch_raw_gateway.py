from pathlib import Path
from typing import Optional

import requests
from tqdm import tqdm

from pipeline import config
from pipeline.workspace import raw_path


def fetch_raw_via_gateway(task_id: str, platform: str, link: str) -> Path:
    """
    Call SHORTDL_API_BASE /v1/parse, get download_url, download to raw/<task_id>.mp4,
    and return the Path.
    """

    payload = {"task_id": task_id, "platform": platform, "link": link}
    url = f"{config.SHORTDL_API_BASE.rstrip('/')}/v1/parse"
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    download_url: Optional[str] = data.get("download_url")
    if not download_url:
        raise ValueError("no download_url returned from gateway")

    out_path = raw_path(task_id)

    with requests.get(download_url, stream=True, timeout=60) as stream:
        stream.raise_for_status()
        total = int(stream.headers.get("content-length", 0))
        with open(out_path, "wb") as f:
            progress = tqdm(total=total, unit="B", unit_scale=True, desc=f"downloading {task_id}")
            for chunk in stream.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    progress.update(len(chunk))
            progress.close()

    return out_path
