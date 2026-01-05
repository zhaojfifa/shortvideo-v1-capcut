import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from gateway.app.ports.storage_provider import get_storage_service
from gateway.app.core.workspace import pack_zip_path, relative_to_workspace
from gateway.app.utils.keys import KeyBuilder

README_TEMPLATE = """CapCut pack usage

1. Create a new CapCut project and import the extracted zip files.
2. Place raw/raw.mp4 on the video track.
3. Import subs/mm.srt and adjust styling.
4. Place audio/{audio_filename} on the audio track and align with subtitles.
5. Add transitions or stickers as needed.
"""


class PackError(Exception):
    """Raised when packing fails."""


_SRT_TIME_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}"
)


def srt_to_txt(srt_text: str) -> str:
    blocks = [b for b in srt_text.split("\n\n") if b.strip()]
    lines_out: list[str] = []
    for block in blocks:
        text_lines: list[str] = []
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.isdigit():
                continue
            if "-->" in s or _SRT_TIME_RE.search(s):
                continue
            text_lines.append(s)
        if text_lines:
            lines_out.append(" ".join(text_lines))
    return "\n".join(lines_out).strip() + ("\n" if lines_out else "")


def _ensure_txt_from_srt(dst_txt: Path, src_srt: Path) -> None:
    srt_text = src_srt.read_text(encoding="utf-8")
    dst_txt.write_text(srt_to_txt(srt_text), encoding="utf-8")


def _ensure_silence_audio_ffmpeg(out_path: Path, seconds: int = 1) -> None:
    """Create a silent WAV via ffmpeg."""

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PackError("ffmpeg not found in PATH (required). Please install ffmpeg.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=16000:cl=mono",
        "-t",
        str(seconds),
        "-acodec",
        "pcm_s16le",
        str(out_path),
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        raise PackError(f"ffmpeg silence generation failed: {p.stderr[-800:]}")


def _maybe_fill_missing_for_pack(*, raw_path: Path, audio_path: Path, subs_path: Path) -> None:
    """Allow pack to proceed by generating silence audio if DUB_SKIP=1."""

    dub_skip = os.getenv("DUB_SKIP", "").strip().lower() in ("1", "true", "yes")
    if not dub_skip:
        return

    if audio_path and not audio_path.exists():
        _ensure_silence_audio_ffmpeg(audio_path, seconds=1)


def create_capcut_pack(
    task_id: str,
    raw_path: Path,
    audio_path: Path,
    subs_path: Path,
    txt_path: Path | None = None,
    tenant_id: str = "default",
    project_id: str = "default",
    pack_path: Path | None = None,
) -> dict:
    required = [raw_path, audio_path, subs_path]

    _maybe_fill_missing_for_pack(raw_path=raw_path, audio_path=audio_path, subs_path=subs_path)

    missing = [p for p in required if not p.exists()]
    if missing:
        names = ", ".join(str(p) for p in missing)
        raise PackError(f"missing required files: {names}")

    resolved_pack_path = pack_path or pack_zip_path(task_id)
    resolved_pack_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / f"pack_{task_id}"
        tmp_path.mkdir(parents=True, exist_ok=True)

        raw_dir = tmp_path / "raw"
        audio_dir = tmp_path / "audio"
        subs_dir = tmp_path / "subs"
        scenes_dir = tmp_path / "scenes"
        for d in (raw_dir, audio_dir, subs_dir, scenes_dir):
            d.mkdir(parents=True, exist_ok=True)

        audio_ext = audio_path.suffix if audio_path.suffix else ".wav"
        audio_filename = f"voice_my{audio_ext}"

        shutil.copy(raw_path, raw_dir / "raw.mp4")
        shutil.copy(audio_path, audio_dir / audio_filename)
        shutil.copy(subs_path, subs_dir / "mm.srt")

        mm_txt_path = txt_path or subs_path.with_suffix(".txt")
        if mm_txt_path.exists():
            shutil.copy(mm_txt_path, subs_dir / "mm.txt")
        else:
            _ensure_txt_from_srt(subs_dir / "mm.txt", subs_path)

        (scenes_dir / ".keep").write_text("", encoding="utf-8")

        manifest = {
            "version": "1.8",
            "pack_type": "capcut_v18",
            "task_id": task_id,
            "language": "my",
            "assets": {
                "raw_video": "raw/raw.mp4",
                "voice": f"audio/{audio_filename}",
                "subtitle": "subs/mm.srt",
                "scenes_dir": "scenes/",
            },
        }
        (tmp_path / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            README_TEMPLATE.format(audio_filename=audio_filename),
            encoding="utf-8",
        )

        pack_prefix = Path("deliver") / "packs" / task_id
        with ZipFile(resolved_pack_path, "w", compression=ZIP_DEFLATED) as zf:
            for item in tmp_path.rglob("*"):
                if item.is_file():
                    arcname = (pack_prefix / item.relative_to(tmp_path)).as_posix()
                    zf.write(item, arcname=arcname)

    if not resolved_pack_path.exists():
        raise PackError(f"pack zip not found: {resolved_pack_path}")

    storage = get_storage_service()
    zip_key = KeyBuilder.build(tenant_id, project_id, task_id, "artifacts/capcut_pack.zip")
    storage.upload_file(str(resolved_pack_path), zip_key, content_type="application/zip")

    files = [
        f"deliver/packs/{task_id}/raw/raw.mp4",
        f"deliver/packs/{task_id}/audio/{audio_filename}",
        f"deliver/packs/{task_id}/subs/mm.srt",
        f"deliver/packs/{task_id}/subs/mm.txt",
        f"deliver/packs/{task_id}/scenes/.keep",
        f"deliver/packs/{task_id}/manifest.json",
        f"deliver/packs/{task_id}/README.md",
    ]

    return {
        "zip_key": zip_key,
        "zip_path": relative_to_workspace(resolved_pack_path),
        "files": files,
    }
