import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: list[str]
    zotero_user_id: str
    zotero_api_key: str

    @property
    def zotero_configured(self) -> bool:
        return bool(self.zotero_user_id and self.zotero_api_key)


def load_settings() -> Settings:
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/workbench.db"),
        cors_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        zotero_user_id=os.getenv("ZOTERO_USER_ID", "").strip(),
        zotero_api_key=os.getenv("ZOTERO_API_KEY", "").strip(),
    )


settings = load_settings()
