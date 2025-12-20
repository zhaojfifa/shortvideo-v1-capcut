import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from gateway.app.core.workspace import pack_zip_path, relative_to_workspace

README_TEMPLATE = """CapCut 剪辑包使用说明

1. 在 CapCut 新建项目，导入 zip 解压后的文件。
2. 将 raw.mp4 放入视频轨道。
3. 导入 subs_mm.srt，调整字体样式。
4. 将 {audio_filename} 放入音频轨道，与字幕对齐。
5. 根据需要添加转场、贴纸等二次创作。
"""


class PackError(Exception):
    """Raised when packing fails."""


def create_capcut_pack(task_id: str, raw_path: Path, audio_path: Path, subs_path: Path) -> dict:
    missing = [p for p in [raw_path, audio_path, subs_path] if not p.exists()]
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
        (tmp_path / "README.txt").write_text(
            README_TEMPLATE.format(audio_filename=audio_filename),
            encoding="utf-8",
        )

        with ZipFile(pack_path, "w", compression=ZIP_DEFLATED) as zf:
            for item in tmp_path.iterdir():
                zf.write(item, arcname=item.name)

    files = ["raw.mp4", audio_filename, "subs_mm.srt", "README.txt"]
    return {"zip_path": relative_to_workspace(pack_path), "files": files}
