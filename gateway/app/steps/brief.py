import os
import json
import logging
from gateway.app.config import get_settings
from gateway.app.ports.storage_provider import get_storage_service
from gateway.app.utils.keys import KeyBuilder
from gateway.app.services.gemini_brief import generate_brief

logger = logging.getLogger(__name__)

async def run_brief_step(task):
    """
    Step: Generate Brief from Subtitles
    Input: artifacts/subtitles.json
    Output: artifacts/brief.json
    """
    settings = get_settings()
    storage = get_storage_service()
    
    task_id = task.id
    tenant = getattr(task, "tenant_id", "default")
    project = getattr(task, "project_id", "default")
    target_lang = getattr(task, "target_lang", "my")

    logger.info(f"Running Brief Step for {task_id}")

    # 1. 下载字幕 (作为输入源)
    sub_key = KeyBuilder.build(tenant, project, task_id, "artifacts/subtitles.json")
    local_dir = os.path.join(settings.WORKSPACE_ROOT, tenant, project, task_id)
    os.makedirs(local_dir, exist_ok=True)
    
    local_sub_path = os.path.join(local_dir, "subtitles.json")
    
    # 下载字幕
    if not storage.exists(sub_key):
        logger.warning(f"Subtitles not found at {sub_key}, skipping Brief generation.")
        return

    storage.download_file(sub_key, local_sub_path)
    
    # 2. 提取文本
    full_text = ""
    with open(local_sub_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        # 拼接所有文本用于分析
        full_text = "\n".join([s.get("text", "") for s in data.get("segments", [])])

    # 3. 调用 AI 生成 Brief
    brief_data = generate_brief(full_text, target_lang)
    
    # 4. 保存结果
    local_brief_path = os.path.join(local_dir, "brief.json")
    with open(local_brief_path, "w", encoding="utf-8") as f:
        json.dump(brief_data, f, indent=2, ensure_ascii=False)
        
    brief_key = KeyBuilder.build(tenant, project, task_id, "artifacts/brief.json")
    storage.upload_file(local_brief_path, brief_key)
    
    logger.info(f"Brief generated and uploaded to {brief_key}")
