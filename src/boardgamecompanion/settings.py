from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BGC_",
        case_sensitive=False,
        extra="ignore",
    )

    config_dir: Path = Path("/config")
    import_dir: Path = Path("/data/import")
    manuals_dir: Path = Path("/data/manuals")
    floppy_url: str | None = None
    floppy_api_key: str | None = None
    ollama_url: str | None = None
    qdrant_url: str | None = None

    @property
    def database_path(self) -> Path:
        return self.config_dir / "boardgamecompanion.sqlite3"

    def ensure_directories(self) -> None:
        for path in (self.config_dir, self.import_dir, self.manuals_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
