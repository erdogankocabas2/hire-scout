from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    tavily_api_key: str = ""
    hunter_api_key: str = ""

    scout_geo: str = "Turkey"
    scout_role_families: str = "gtm,product,bd"
    scout_cron_hour: int = 7
    scout_cron_minute: int = 0
    scout_max_companies_per_run: int = 15

    database_url: str = f"sqlite:///{ROOT / 'data' / 'hire_scout.db'}"

    @property
    def role_families(self) -> List[str]:
        return [r.strip().lower() for r in self.scout_role_families.split(",") if r.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
