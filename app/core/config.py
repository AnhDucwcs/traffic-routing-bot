from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings."""

    PROJECT_NAME: str = "Traffic Routing Bot"
    TELEGRAM_BOT_TOKEN: str
    MONGO_URI: str
    VN_PROXY: str
    US_PROXY: str
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
        
settings = Settings()