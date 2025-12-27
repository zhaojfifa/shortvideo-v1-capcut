import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import os
import wave
import shutil
import subprocess



from gateway.app.core.workspace import pack_zip_path, relative_to_workspace

def _ensure_silence_wav(path: Path, seconds: int = 1, fr: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nframes = fr * seconds
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(fr)
        w.writeframes(b"\x00\x00" * nframes)

def _maybe_fill_missing_for_pack(raw_mp4: Path, mm_srt: Path, mm_wav: Path) -> None:
    dub_skip = os.getenv("DUB_SKIP", "").lower() in ("1", "true", "yes")
    if dub_skip and not mm_wav.exists():
        _ensure_silence_wav(mm_wav)

README_TEMPLATE = """CapCut 剪辑包使用说明

1. 在 CapCut 新建项目，导入 zip 解压后的文件。
2. 将 raw.mp4 放入视频轨道。
3. 导入 subs_mm.srt（或 subs_origin.srt），调整字体样式。
4. 将 {audio_filename} 放入音频轨道，与字幕对齐。
5. 如需纯文本字幕，可使用 subs_mm.txt（不含时间轴）。
6. 根据需要添加转场、贴纸等二次创作。
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
    """
    Create a silent WAV via ffmpeg (keeps ffmpeg as a first-class dependency).
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PackError("ffmpeg not found in PATH (required). Please install ffmpeg.")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 16kHz mono PCM wav (safe for most pipelines)
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=16000:cl=mono",
        "-t", str(seconds),
        "-acodec", "pcm_s16le",
        str(out_path),
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        raise PackError(f"ffmpeg silence generation failed: {p.stderr[-800:]}")


def _maybe_fill_missing_for_pack(*, raw_path: Path, audio_path: Path, subs_path: Path) -> None:
    """
    Gatekeeper: when DUB_SKIP=1, allow pack to proceed by generating silence audio if missing.
    DO NOT fake raw/subs; those should exist for a meaningful pack.
    """
    dub_skip = os.getenv("DUB_SKIP", "").strip().lower() in ("1", "true", "yes")
    if not dub_skip:
        return

    # Only fill audio; keep raw/subs strict
    if audio_path and not audio_path.exists():
        _ensure_silence_audio_ffmpeg(audio_path, seconds=1)

from pathlib import Path
import tempfile
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

from gateway.app.config import get_storage_service
from gateway.app.utils.keys import KeyBuilder

def create_capcut_pack(
    task_id: str,
    raw_path: Path,
    audio_path: Path,
    subs_path: Path,
    txt_path: Path | None = None,
    tenant_id: str = "default",
    project_id: str = "default",
) -> dict:
    required = [raw_path, audio_path, subs_path]

    # B 方案门禁：DUB_SKIP=1 时自动补齐静音 wav（用 ffmpeg）
    _maybe_fill_missing_for_pack(raw_path=raw_path, audio_path=audio_path, subs_path=subs_path)

    missing = [p for p in required if not p.exists()]
    if missing:
        names = ", ".join(str(p) for p in missing)
        raise PackError(f"missing required files: {names}")

    pack_path = pack_zip_path(task_id)
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[pack] output path: {pack_path}")
    print(f"[pack] zip size: {pack_path.stat().st_size} bytes")


    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / f"pack_{task_id}"
        tmp_path.mkdir(parents=True, exist_ok=True)

        audio_filename = audio_path.name

        shutil.copy(raw_path, tmp_path / "raw.mp4")
        shutil.copy(audio_path, tmp_path / audio_filename)
        shutil.copy(subs_path, tmp_path / "subs_mm.srt")

        txt_dst = tmp_path / "subs_mm.txt"
        resolved_txt = txt_path if txt_path and txt_path.exists() else subs_path.with_suffix(".txt")
        if resolved_txt.exists():
            shutil.copy(resolved_txt, txt_dst)
        else:
            _ensure_txt_from_srt(txt_dst, subs_path)

        (tmp_path / "README.txt").write_text(
            README_TEMPLATE.format(audio_filename=audio_filename),
            encoding="utf-8",
        )

        with ZipFile(pack_path, "w", compression=ZIP_DEFLATED) as zf:
            for item in tmp_path.iterdir():
                zf.write(item, arcname=item.name)

    # ✅ 关键：把 zip 上传到 SSOT key（local storage 会落到 data_debug/...）
    storage = get_storage_service()
    zip_key = KeyBuilder.build(tenant_id, project_id, task_id, "artifacts/capcut_pack.zip")
    storage.upload_file(str(pack_path), zip_key)

    files = [
        "raw.mp4",
        audio_filename,
        "subs_mm.srt",
        "subs_mm.txt",
        "README.txt",
    ]

    return {
        "zip_key": zip_key,                          # ✅ 给 /files 用
        "zip_path": relative_to_workspace(pack_path),# ✅ 你原来前端/调试展示用
        "files": files,
    }

