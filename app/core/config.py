from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings."""

    PROJECT_NAME: str = "Traffic Routing Bot"
    TELEGRAM_BOT_TOKEN: str
    INTERNAL_API_KEY: str
    MONGO_URI: str
    VN_PROXY: str
    AI_ENGINE_API_KEY: str
    TELEGRAM_BOT_CALLBACK_URL: str
    JAVA_APP_CALLBACK_URL: str
    HK_TOKEN: str
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
        
settings = Settings()