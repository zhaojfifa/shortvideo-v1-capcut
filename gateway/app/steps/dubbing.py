import os
import json
import logging
from pathlib import Path

from gateway.app.config import get_storage_service, get_settings
from gateway.app.utils.keys import KeyBuilder
from gateway.app.utils.languages import get_default_voice
from gateway.app.providers.edge_tts import EdgeTTSError, generate_audio_edge_tts

logger = logging.getLogger(__name__)

def _load_json_compat(path: str):
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return json.loads(text)

async def run_dub_step(task):
    settings = get_settings()
    storage = get_storage_service()

    task_id = getattr(task, "id", None) or getattr(task, "task_id", None)
    tenant = getattr(task, "tenant_id", "default")
    project = getattr(task, "project_id", "default")
    target_lang = getattr(task, "target_lang", "my")

    # ✅ 本地门禁：直接跳过 dubbing（仍写 manifest，保证 pack/链路连通）
    if os.getenv("DUB_SKIP", "0") == "1":
        logger.warning("Dubbing skipped by DUB_SKIP=1 (task=%s)", task_id)
        manifest_key = KeyBuilder.build(tenant, project, task_id, "artifacts/voice/manifest.json")
        local_dir = Path(settings.workspace_root) / tenant / project / task_id
        local_dir.mkdir(parents=True, exist_ok=True)
        manifest_local = local_dir / "voice_manifest.json"
        manifest = {
            "schema_version": "0.1",
            "task_id": task_id,
            "provider": "skipped",
            "voice_id": None,
            "outputs": {},
            "reason": "DUB_SKIP=1"
        }
        manifest_local.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        storage.upload_file(str(manifest_local), manifest_key)
        return

    # 1) download subtitles.json
    sub_key = KeyBuilder.build(tenant, project, task_id, "artifacts/subtitles.json")
    local_dir = Path(settings.workspace_root) / tenant / project / task_id
    local_dir.mkdir(parents=True, exist_ok=True)
    local_sub_path = local_dir / "subtitles.json"

    if not storage.exists(sub_key):
        raise FileNotFoundError(f"Subtitles JSON not found at {sub_key}. SSOT Broken.")

    storage.download_file(sub_key, str(local_sub_path))
    sub_data = _load_json_compat(str(local_sub_path))

    segments = sub_data.get("segments", [])
    if not segments:
        logger.warning("No segments found in subtitles.json")
        return

    full_text = " ".join([(s.get("target") or s.get("text") or "").strip() for s in segments]).strip()
    if not full_text:
        logger.warning("Empty text for dubbing.")
        return

    voice_id = get_default_voice(target_lang)
    voice_manifest = {
        "schema_version": "0.1",
        "task_id": task_id,
        "provider": "edge-tts",
        "voice_id": voice_id,
        "outputs": {},
    }

    local_audio_path = local_dir / "full_audio.mp3"

    try:
        await generate_audio_edge_tts(full_text, voice_id, str(local_audio_path))

        audio_key = KeyBuilder.build(tenant, project, task_id, "artifacts/voice/full.mp3")
        storage.upload_file(str(local_audio_path), audio_key)
        voice_manifest["outputs"]["full_audio"] = audio_key

    except EdgeTTSError as e:
        # ✅ 兜底降级：本地/弱网/无声音时不中断
        if os.getenv("DUB_ALLOW_FALLBACK", "1") == "1":
            logger.warning("Edge-TTS failed, fallback to no-audio mode: %s", e)
            voice_manifest["provider"] = "edge-tts"
            voice_manifest["outputs"] = {}
            voice_manifest["warning"] = f"tts_failed: {str(e)}"
        else:
            raise

    # upload manifest always
    manifest_local = local_dir / "voice_manifest.json"
    manifest_local.write_text(json.dumps(voice_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_key = KeyBuilder.build(tenant, project, task_id, "artifacts/voice/manifest.json")
    storage.upload_file(str(manifest_local), manifest_key)
