import json
import logging
import os
from pathlib import Path

import google.generativeai as genai
from gateway.app.config import get_settings

logger = logging.getLogger(__name__)


def _load_review_brief_prompt() -> str:
    base_dir = Path(__file__).resolve().parents[1] / "prompts"
    version = os.getenv("REVIEW_BRIEF_PROMPT_VERSION", "v1").strip() or "v1"
    candidate = base_dir / f"review_brief_{version}.txt"
    if not candidate.exists():
        candidate = base_dir / "review_brief_v1.txt"
    return candidate.read_text(encoding="utf-8")


def generate_brief(transcript_text: str, target_lang: str) -> dict:
    """
    调用 Gemini 生成视频 Brief (摘要、卖点、剪辑建议)
    """
    settings = get_settings()
    
    if not transcript_text:
        return {"error": "Empty transcript"}

    # 属性名必须与 config.py 中定义的一致（小写）
    if settings.gemini_api_key:
        genai.configure(api_key=settings.gemini_api_key)
    
    model = genai.GenerativeModel("gemini-1.5-flash") # 使用 Flash 降低成本

    prompt_template = _load_review_brief_prompt()
    prompt = prompt_template.format(
        target_lang=target_lang,
        transcript=transcript_text[:10000],
    )

    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        logger.error(f"Brief generation failed: {e}")
        # 兜底返回，防止流程中断
        return {
            "summary": "Brief generation failed",
            "error": str(e),
            "selling_points": [],
            "editing_suggestions": []
        }
