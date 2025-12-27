import json
import logging
import google.generativeai as genai
from gateway.app.config import get_settings
# === 关键修改 1: 引入语言工具 ===
from gateway.app.utils.languages import get_lang_name

logger = logging.getLogger(__name__)

def generate_subtitles_with_gemini(transcript_text: str, target_lang: str = "my") -> str:
    """
    使用 Gemini 生成翻译后的字幕结构 (JSON)。
    :param transcript_text: 源文本/SRT内容
    :param target_lang: 目标语言代码 (如 'my', 'vi', 'id')
    """
    settings = get_settings()
    
    # 配置 Gemini (如果 key 不存在则跳过，防止本地报错)
    if settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
    
    # 获取模型 (优先读取配置，默认 flash)
    model_name = getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")
    model = genai.GenerativeModel(model_name)

    # === 关键修改 2: 获取语言全称 (如 'Indonesian') ===
    target_lang_name = get_lang_name(target_lang)
    
    logger.info(f"Requesting Gemini subtitles for lang: {target_lang} ({target_lang_name})")

    # === 关键修改 3: Prompt 动态化 ===
    prompt = f"""
    You are a professional video subtitle translator.
    Please translate the following transcript text to **{target_lang_name}**.

    Requirements:
    1. Output MUST be valid JSON format only. No markdown ```json``` tags.
    2. Structure: {{"segments": [{{"start": 0.0, "end": 2.0, "text": "Translated text..."}}]}}
    3. Keep the timestamps accurate if provided, or estimate them.
    4. The tone should be natural and suitable for social media (TikTok/Shorts).
    5. Do not include original text, only the translated **{target_lang_name}** text.

    Transcript:
    {transcript_text[:15000]} 
    """
    # 截断以防超长

    try:
        response = model.generate_content(prompt)
        # 清洗可能存在的 markdown 标记
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        
        # 尝试解析以确保是有效 JSON
        json.loads(clean_text) 
        
        return clean_text

    except Exception as e:
        logger.error(f"Gemini generation failed: {e}")
        # 返回一个空结构的 JSON 字符串作为兜底，防止流程崩溃
        return json.dumps({"segments": [], "error": str(e)})

# 辅助函数：如果系统里还有其他调用方式，保持兼容
def translate_text(text: str, target_lang: str) -> str:
    # 简易翻译接口
    return generate_subtitles_with_gemini(text, target_lang)