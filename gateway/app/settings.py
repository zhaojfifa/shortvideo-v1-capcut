from pydantic import BaseSettings, Field


# gateway/app/settings.py
from pydantic_settings import BaseSettings  # ← 从这里引 BaseSettings

class Settings(BaseSettings):
    """
    Settings for the shortvideo gateway.
    Values are taken from environment variables with the same names.
    """
    XIONGMAO_API_BASE: str = "https://api.guijianpan.com"
    XIONGMAO_APP_ID: str = "xxmQsyByAk"
    XIONGMAO_API_KEY: str = ""  # 在 Render 的环境变量里覆盖

    # 如果你暂时不需要从 .env 读，这里可以不用任何 Config / model_config

settings = Settings()



settings = get_settings()
