import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")

LOVO_API_KEY = os.getenv("LOVO_API_KEY", "")
LOVO_VOICE_ID_MM = os.getenv("LOVO_VOICE_ID_MM", "")

SHORTDL_API_BASE = os.getenv("SHORTDL_API_BASE", "http://127.0.0.1:8000")
