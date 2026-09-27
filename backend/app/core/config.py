from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Process configuration. Values come from environment variables or `.env`.

    `.env` is looked up in the backend directory and in the repository root so
    that both `uv run` from `backend/` and docker-compose from the root work.
    """

    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://mziko:mziko@localhost:5432/mziko"
    content_dir: Path = REPO_DIR / "content"
    media_dir: Path = REPO_DIR / "media"
    public_url: str = "http://localhost"

    bot_token: str = ""
    admin_telegram_ids: list[int] = Field(default_factory=list)

    timezone: str = "Asia/Tbilisi"


@lru_cache
def get_settings() -> Settings:
    return Settings()
