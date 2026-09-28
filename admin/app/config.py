from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ADMIN_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ADMIN_DIR.parent


class Settings(BaseSettings):
    """Process configuration from environment variables or `.env`.

    `.env` is looked up in the admin directory and in the repository root so
    that both `uv run` from `admin/` and docker-compose from the root work.
    """

    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", ADMIN_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Where the back office finds the API (inside docker-compose: http://api:8000).
    api_url: str = "http://localhost:8000"
    # Shared secret presented to /api/admin/*.
    admin_api_token: str = ""
    # The only Google account allowed in. Compared case-insensitively.
    admin_email: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    # Signs the session cookie; generate with `openssl rand -hex 32`.
    admin_session_secret: str = ""
    # Public address of the site; the Google redirect URI is PUBLIC_URL + /admin/login/callback.
    public_url: str = "http://localhost"

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_url.rstrip('/')}/admin/login/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
