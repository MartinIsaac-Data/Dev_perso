"""Application configuration.

Everything that differs between a laptop, a container and a future Postgres
deployment lives here and nowhere else. No module reads os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root, resolved from this file: app/ -> backend/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_prefix="TOS_",
        extra="ignore",
    )

    # --- Storage -----------------------------------------------------------
    # SQLite by default (local-first). Point this at a postgresql+psycopg://
    # URL and nothing else in the codebase has to change: the schema is
    # deliberately free of SQLite-specific constructs.
    database_url: str = f"sqlite+pysqlite:///{REPO_ROOT / 'data' / 'transformation_os.db'}"

    # Echo every SQL statement. Useful while learning; noisy in tests.
    sql_echo: bool = False

    # --- Agents ------------------------------------------------------------
    # Read from ANTHROPIC_API_KEY too, so the standard variable works as-is.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    # --- Paths -------------------------------------------------------------
    seeds_dir: Path = REPO_ROOT / "backend" / "seeds"
    sql_dir: Path = REPO_ROOT / "sql"
    exports_dir: Path = REPO_ROOT / "exports"
    prompts_dir: Path = REPO_ROOT / "backend" / "app" / "services" / "agents" / "prompts"

    # --- Business rules ----------------------------------------------------
    # A skill not practised for this long is flagged at risk. Overridable per
    # skill in the taxonomy; this is only the fallback.
    default_skill_decay_months: int = 9

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_sqlite:
        # Create the directory holding the SQLite file; SQLite will not.
        db_path = settings.database_url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return settings
