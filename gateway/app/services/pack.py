import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from gateway.app.core.workspace import pack_zip_path, relative_to_workspace

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
    out_lines: list[str] = []
    for line in srt_text.splitlines():
        s = line.strip()
        if not s:
            if out_lines and out_lines[-1] != "":
                out_lines.append("")
            continue
        if s.isdigit():
            continue
        if "-->" in s or _SRT_TIME_RE.search(s):
            continue
        out_lines.append(s)
    while out_lines and out_lines[-1] == "":
        out_lines.pop()
    return "\n".join(out_lines) + "\n" if out_lines else ""


def _ensure_txt_from_srt(dst_txt: Path, src_srt: Path) -> None:
    srt_text = src_srt.read_text(encoding="utf-8")
    dst_txt.write_text(srt_to_txt(srt_text), encoding="utf-8")


def create_capcut_pack(
    task_id: str,
    raw_path: Path,
    audio_path: Path,
    subs_path: Path,
    txt_path: Path | None = None,
) -> dict:
    required = [raw_path, audio_path, subs_path]
    missing = [p for p in required if not p.exists()]
    if missing:
        names = ", ".join(str(p) for p in missing)
        raise PackError(f"missing required files: {names}")

    pack_path = pack_zip_path(task_id)

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

    files = [
        "raw.mp4",
        audio_filename,
        "subs_mm.srt",
        "subs_mm.txt",
        "README.txt",
    ]
    return {"zip_path": relative_to_workspace(pack_path), "files": files}
