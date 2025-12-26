# gateway/app/utils/languages.py

LANGUAGE_CONFIG = {
    "my": {"name": "Burmese", "voice_id": "my-MM-TularWinNeural"},
    "vi": {"name": "Vietnamese", "voice_id": "vi-VN-HoaiMyNeural"},
    "th": {"name": "Thai", "voice_id": "th-TH-PremwadeeNeural"},
    "en": {"name": "English", "voice_id": "en-US-ChristopherNeural"},
    "zh": {"name": "Chinese", "voice_id": "zh-CN-XiaoxiaoNeural"},
    # === 新增支持 ===
    "id": {"name": "Indonesian", "voice_id": "id-ID-GadisNeural"},
    "ms": {"name": "Malay", "voice_id": "ms-MY-YasminNeural"},
}

def get_lang_name(code: str) -> str:
    """
    根据语言代码获取英文全称 (用于 Prompt)
    例如: 'my' -> 'Burmese', 'id' -> 'Indonesian'
    """
    cfg = LANGUAGE_CONFIG.get(code)
    if cfg:
        return cfg["name"]
    # Fallback: 如果没配置，直接返回代码本身，防止报错
    return code

def get_default_voice(code: str) -> str:
    """
    根据语言代码获取默认 Edge-TTS 语音包
    """
    cfg = LANGUAGE_CONFIG.get(code)
    if cfg:
        return cfg["voice_id"]
    # Fallback: 默认用英语，或者抛出异常
    return "en-US-ChristopherNeural"