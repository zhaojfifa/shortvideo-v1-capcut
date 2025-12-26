import json
import logging
import google.generativeai as genai
from gateway.app.config import get_settings

logger = logging.getLogger(__name__)

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

    prompt = f"""
    You are a professional video editor and content strategist.
    Analyze the following video transcript (in target language code: {target_lang}).
    
    Output a JSON object with the following fields:
    1. "summary": A 1-sentence summary of the video.
    2. "hook": What is the "Golden 3 Seconds" hook content?
    3. "selling_points": A list of 3 key selling points or interesting facts.
    4. "editing_suggestions": A list of specific advice for editing this into a viral TikTok.
    5. "risk_score": An integer 0-10 (0 = safe, 10 = copyright/policy violation).

    Transcript:
    {transcript_text[:10000]}
    """

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