from pathlib import Path
from typing import Literal

from pydantic import Field
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
    max_document_bytes: int = 100 * 1024 * 1024
    pdf_parse_timeout_seconds: float = Field(default=60.0, ge=5.0, le=600.0)
    pdf_parse_max_pages: int = Field(default=2000, ge=1, le=10000)
    pdf_parse_max_chars_per_page: int = Field(
        default=500_000, ge=1000, le=5_000_000
    )
    pdf_parse_max_total_chars: int = Field(
        default=20_000_000, ge=10_000, le=100_000_000
    )
    pdf_parse_memory_mb: int = Field(default=768, ge=128, le=4096)
    chunk_max_chars: int = Field(default=1800, ge=200, le=20000)
    chunk_overlap_chars: int = Field(default=240, ge=0, le=5000)
    chunk_min_break_chars: int = Field(default=900, ge=100, le=10000)
    rulebook_fetch_max_bytes: int = Field(
        default=32 * 1024 * 1024,
        ge=1024,
        le=100 * 1024 * 1024,
    )
    rulebook_update_worker_enabled: bool = True
    rulebook_update_poll_seconds: float = Field(default=60.0, ge=5.0, le=86400.0)
    rulebook_update_default_interval_seconds: int = Field(
        default=30 * 24 * 60 * 60,
        ge=3600,
        le=365 * 24 * 60 * 60,
    )
    rulebook_update_retry_base_seconds: int = Field(
        default=6 * 60 * 60,
        ge=60,
        le=30 * 24 * 60 * 60,
    )
    rulebook_update_retry_max_seconds: int = Field(
        default=7 * 24 * 60 * 60,
        ge=60,
        le=365 * 24 * 60 * 60,
    )
    rulebook_update_lease_seconds: int = Field(default=15 * 60, ge=60, le=3600)
    rulebook_update_batch_size: int = Field(default=5, ge=1, le=100)
    floppy_url: str | None = None
    floppy_api_key: str | None = None
    floppy_timeout_seconds: float = 45.0
    floppy_verify_tls: bool = True
    rag_provider: Literal["ollama", "lmstudio"] = "ollama"
    ollama_url: str | None = None
    ollama_embedding_model: str | None = None
    ollama_embedding_dimensions: int | None = Field(default=None, ge=64, le=4096)
    ollama_embedding_batch_size: int = Field(default=16, ge=1, le=128)
    ollama_embedding_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    ollama_generation_model: str | None = None
    ollama_generation_timeout_seconds: float = Field(
        default=120.0, ge=1.0, le=900.0
    )
    ollama_generation_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    ollama_verify_tls: bool = True
    lmstudio_url: str | None = None
    lmstudio_api_key: str | None = None
    lmstudio_embedding_model: str | None = None
    lmstudio_embedding_dimensions: int | None = Field(
        default=None, ge=64, le=4096
    )
    lmstudio_embedding_batch_size: int = Field(default=16, ge=1, le=128)
    lmstudio_embedding_timeout_seconds: float = Field(
        default=60.0, ge=1.0, le=600.0
    )
    lmstudio_generation_model: str | None = None
    lmstudio_generation_timeout_seconds: float = Field(
        default=300.0, ge=1.0, le=900.0
    )
    lmstudio_generation_temperature: float = Field(
        default=0.0, ge=0.0, le=2.0
    )
    lmstudio_verify_tls: bool = True
    retrieval_max_candidates: int = Field(default=10000, ge=100, le=100000)
    answer_max_evidence_chars: int = Field(default=30000, ge=1000, le=200000)
    answer_max_claims: int = Field(default=12, ge=1, le=100)
    qdrant_url: str | None = None

    @property
    def database_path(self) -> Path:
        return self.config_dir / "boardgamecompanion.sqlite3"

    def ensure_directories(self) -> None:
        for path in (self.config_dir, self.import_dir, self.manuals_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
