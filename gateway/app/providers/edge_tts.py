import logging
import edge_tts
from gateway.app.config import get_settings

logger = logging.getLogger(__name__)

class EdgeTTSError(RuntimeError):
    """Raised when Edge-TTS synthesis fails."""

async def generate_audio_edge_tts(text: str, voice: str, output_path: str) -> None:
    """
    使用 Edge TTS 生成音频并保存到指定路径。
    这是一个无状态的纯函数，不再依赖 Workspace 对象。
    
    :param text: 要朗读的文本
    :param voice: Edge-TTS 的 voice name (例如 "ms-MY-YasminNeural")
    :param output_path: 本地保存路径
    """
    if not text or not text.strip():
        logger.warning("Edge-TTS received empty text, skipping generation.")
        return

    settings = get_settings()
    
    # 从配置读取语速和音量，如果没有则使用默认值
    rate = getattr(settings, "edge_tts_rate", "+0%")
    volume = getattr(settings, "edge_tts_volume", "+0%")

    logger.info(
        f"Calling Edge-TTS",
        extra={
            "voice": voice,
            "output": output_path,
            "text_len": len(text),
            "rate": rate
        }
    )

    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            volume=volume,
        )
        
        # 直接保存到指定路径
        await communicate.save(output_path)
        
    except Exception as e:
        logger.error(f"Edge-TTS generation failed: {e}")
        raise EdgeTTSError(f"Edge-TTS failed: {str(e)}") from e

# ==========================================
# Legacy Adapter (可选：保留旧类以兼容尚未重构的代码)
# ==========================================
class EdgeTTSProvider:
    def __init__(self, workspace):
        self.workspace = workspace

    async def synthesize_mm(self, *, task_id: str, voice_id: str | None, lines: list[str]) -> str:
        # 这是一个适配器，将旧调用转发给新函数
        # 注意：这里的 voice_id 需要是实际的 edge voice name，或者需要查表
        # 为了简单起见，假设传入的是实际 voice 或由调用者处理映射
        text = "\n".join(lines)
        # 临时路径，旧逻辑通常由 workspace 处理，这里简化处理
        output_path = f"/tmp/{task_id}_legacy.mp3" 
        await generate_audio_edge_tts(text, voice_id or "en-US-ChristopherNeural", output_path)
        return output_path