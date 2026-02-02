from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


def ffmpeg_concat_videos(inputs: List[Path], output: Path) -> None:
    """
    Deterministic concat using ffmpeg concat demuxer.
    Assumes inputs are same codec/container.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    lst = output.parent / "concat_list.txt"
    with lst.open("w", encoding="utf-8") as f:
        for p in inputs:
            f.write(f"file '{p.as_posix()}'\n")

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lst),
        "-c",
        "copy",
        str(output),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {proc.stderr[-2000:]}")
