from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from boardgamecompanion.database import Database
from boardgamecompanion.settings import settings


class AppSettingsStore:
    def __init__(self, database: Database):
        self.database = database

    def get(self, key: str) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str | None, *, sensitive: bool = False) -> None:
        now = datetime.now(UTC).isoformat()
        with self.database.transaction() as connection:
            if value is None or value == "":
                connection.execute("DELETE FROM app_settings WHERE key = ?", (key,))
                return
            connection.execute(
                """
                INSERT INTO app_settings (key, value, sensitive, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    sensitive = excluded.sensitive,
                    updated_at = excluded.updated_at
                """,
                (key, value, 1 if sensitive else 0, now),
            )

    def get_many(self, keys: tuple[str, ...]) -> dict[str, str | None]:
        placeholders = ",".join("?" for _ in keys)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
                keys,
            ).fetchall()
        values = {key: None for key in keys}
        values.update({row["key"]: row["value"] for row in rows})
        return values


@dataclass(frozen=True)
class ResolvedBggSettings:
    application_token: str | None
    token_source: str | None
    stored_token_configured: bool
    timeout_seconds: float
    min_interval_seconds: float

    @property
    def configured(self) -> bool:
        return bool(self.application_token)

    def public_dict(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "application_token_configured": self.configured,
            "application_token_source": self.token_source,
            "stored_application_token_configured": self.stored_token_configured,
            "timeout_seconds": self.timeout_seconds,
            "min_interval_seconds": self.min_interval_seconds,
            "overrides": {
                "application_token": self.token_source == "environment",
            },
        }


def resolve_bgg_settings(database: Database) -> ResolvedBggSettings:
    store = AppSettingsStore(database)
    stored_token = store.get("bgg_application_token")
    env_token = os.environ.get("BGC_BGG_APPLICATION_TOKEN")
    token = env_token.strip() if env_token and env_token.strip() else stored_token
    source = "environment" if env_token and env_token.strip() else "stored" if stored_token else None

    return ResolvedBggSettings(
        application_token=token,
        token_source=source,
        stored_token_configured=bool(stored_token),
        timeout_seconds=float(settings.bgg_timeout_seconds),
        min_interval_seconds=float(settings.bgg_min_interval_seconds),
    )


def save_bgg_settings(
    database: Database,
    *,
    application_token: str | None,
    clear_application_token: bool,
) -> ResolvedBggSettings:
    store = AppSettingsStore(database)
    if clear_application_token:
        store.set("bgg_application_token", None, sensitive=True)
    elif application_token is not None and application_token.strip():
        store.set(
            "bgg_application_token",
            application_token.strip(),
            sensitive=True,
        )
    return resolve_bgg_settings(database)


RAG_PROVIDERS = ("ollama", "lmstudio", "gemini")


def _normalize_provider_order(
    value: object,
    *,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    if value is None:
        return default
    raw = value
    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid persisted RAG provider order") from exc
    if not isinstance(raw, (list, tuple)):
        raise ValueError("RAG provider order must be a list")
    result = tuple(str(item).strip().lower() for item in raw)
    if not result or len(result) > len(RAG_PROVIDERS):
        raise ValueError("RAG provider order must contain between 1 and 3 providers")
    if len(set(result)) != len(result) or any(item not in RAG_PROVIDERS for item in result):
        raise ValueError("RAG provider order contains duplicates or unsupported providers")
    return result


@dataclass(frozen=True)
class ResolvedRagSettings:
    embedding_provider_order: tuple[str, ...]
    generation_provider_order: tuple[str, ...]
    ollama_url: str | None
    ollama_embedding_model: str | None
    ollama_generation_model: str | None
    lmstudio_url: str | None
    lmstudio_api_key: str | None
    lmstudio_api_key_source: str | None
    lmstudio_embedding_model: str | None
    lmstudio_generation_model: str | None
    lmstudio_generation_timeout_seconds: float
    lmstudio_generation_max_tokens: int
    lmstudio_generation_disable_thinking: bool
    gemini_url: str
    gemini_api_key: str | None
    gemini_api_key_source: str | None
    gemini_embedding_model: str
    gemini_generation_model: str

    @property
    def embedding_provider(self) -> str:
        return self.embedding_provider_order[0]

    @property
    def generation_provider(self) -> str:
        return self.generation_provider_order[0]

    def public_dict(self) -> dict[str, object]:
        return {
            "embedding_provider_order": list(self.embedding_provider_order),
            "generation_provider_order": list(self.generation_provider_order),
            "effective_embedding_provider": self.embedding_provider,
            "effective_generation_provider": self.generation_provider,
            "automatic_fallback": False,
            "providers": {
                "ollama": {
                    "url": self.ollama_url,
                    "embedding_model": self.ollama_embedding_model,
                    "generation_model": self.ollama_generation_model,
                },
                "lmstudio": {
                    "url": self.lmstudio_url,
                    "api_key_configured": bool(self.lmstudio_api_key),
                    "api_key_source": self.lmstudio_api_key_source,
                    "embedding_model": self.lmstudio_embedding_model,
                    "generation_model": self.lmstudio_generation_model,
                    "generation_timeout_seconds": self.lmstudio_generation_timeout_seconds,
                    "generation_max_tokens": self.lmstudio_generation_max_tokens,
                    "generation_disable_thinking": self.lmstudio_generation_disable_thinking,
                },
                "gemini": {
                    "url": self.gemini_url,
                    "api_key_configured": bool(self.gemini_api_key),
                    "api_key_source": self.gemini_api_key_source,
                    "embedding_model": self.gemini_embedding_model,
                    "generation_model": self.gemini_generation_model,
                },
            },
        }


def resolve_rag_settings(database: Database) -> ResolvedRagSettings:
    store = AppSettingsStore(database)
    keys = (
        "rag_embedding_provider_order",
        "rag_generation_provider_order",
        "rag_ollama_url",
        "rag_ollama_embedding_model",
        "rag_ollama_generation_model",
        "rag_lmstudio_url",
        "rag_lmstudio_api_key",
        "rag_lmstudio_embedding_model",
        "rag_lmstudio_generation_model",
        "rag_lmstudio_generation_timeout_seconds",
        "rag_lmstudio_generation_max_tokens",
        "rag_lmstudio_generation_disable_thinking",
        "rag_gemini_url",
        "rag_gemini_api_key",
        "rag_gemini_embedding_model",
        "rag_gemini_generation_model",
    )
    values = store.get_many(keys)

    stored_lmstudio_key = values["rag_lmstudio_api_key"]
    stored_gemini_key = values["rag_gemini_api_key"]
    lmstudio_api_key = stored_lmstudio_key or settings.lmstudio_api_key
    gemini_api_key = stored_gemini_key or settings.gemini_api_key

    return ResolvedRagSettings(
        embedding_provider_order=_normalize_provider_order(
            values["rag_embedding_provider_order"],
            default=(settings.effective_embedding_provider,),
        ),
        generation_provider_order=_normalize_provider_order(
            values["rag_generation_provider_order"],
            default=(settings.effective_generation_provider,),
        ),
        ollama_url=values["rag_ollama_url"] or settings.ollama_url,
        ollama_embedding_model=(
            values["rag_ollama_embedding_model"] or settings.ollama_embedding_model
        ),
        ollama_generation_model=(
            values["rag_ollama_generation_model"] or settings.ollama_generation_model
        ),
        lmstudio_url=values["rag_lmstudio_url"] or settings.lmstudio_url,
        lmstudio_api_key=lmstudio_api_key,
        lmstudio_api_key_source=(
            "stored"
            if stored_lmstudio_key
            else "environment"
            if settings.lmstudio_api_key
            else None
        ),
        lmstudio_embedding_model=(
            values["rag_lmstudio_embedding_model"] or settings.lmstudio_embedding_model
        ),
        lmstudio_generation_model=(
            values["rag_lmstudio_generation_model"] or settings.lmstudio_generation_model
        ),
        lmstudio_generation_timeout_seconds=float(
            values["rag_lmstudio_generation_timeout_seconds"]
            or settings.lmstudio_generation_timeout_seconds
        ),
        lmstudio_generation_max_tokens=int(
            values["rag_lmstudio_generation_max_tokens"]
            or settings.lmstudio_generation_max_tokens
        ),
        lmstudio_generation_disable_thinking=(
            values["rag_lmstudio_generation_disable_thinking"] != "false"
            if values["rag_lmstudio_generation_disable_thinking"] is not None
            else settings.lmstudio_generation_disable_thinking
        ),
        gemini_url=values["rag_gemini_url"] or settings.gemini_url,
        gemini_api_key=gemini_api_key,
        gemini_api_key_source=(
            "stored"
            if stored_gemini_key
            else "environment"
            if settings.gemini_api_key
            else None
        ),
        gemini_embedding_model=(
            values["rag_gemini_embedding_model"] or settings.gemini_embedding_model
        ),
        gemini_generation_model=(
            values["rag_gemini_generation_model"] or settings.gemini_generation_model
        ),
    )


def save_rag_settings(
    database: Database,
    *,
    embedding_provider_order: tuple[str, ...],
    generation_provider_order: tuple[str, ...],
    ollama_url: str | None,
    ollama_embedding_model: str | None,
    ollama_generation_model: str | None,
    lmstudio_url: str | None,
    lmstudio_api_key: str | None,
    clear_lmstudio_api_key: bool,
    lmstudio_embedding_model: str | None,
    lmstudio_generation_model: str | None,
    lmstudio_generation_timeout_seconds: float,
    lmstudio_generation_max_tokens: int,
    lmstudio_generation_disable_thinking: bool,
    gemini_url: str | None,
    gemini_api_key: str | None,
    clear_gemini_api_key: bool,
    gemini_embedding_model: str | None,
    gemini_generation_model: str | None,
) -> ResolvedRagSettings:
    embedding_order = _normalize_provider_order(
        embedding_provider_order,
        default=(settings.effective_embedding_provider,),
    )
    generation_order = _normalize_provider_order(
        generation_provider_order,
        default=(settings.effective_generation_provider,),
    )
    store = AppSettingsStore(database)
    values = {
        "rag_embedding_provider_order": json.dumps(list(embedding_order)),
        "rag_generation_provider_order": json.dumps(list(generation_order)),
        "rag_ollama_url": (ollama_url or "").strip() or None,
        "rag_ollama_embedding_model": (ollama_embedding_model or "").strip() or None,
        "rag_ollama_generation_model": (ollama_generation_model or "").strip() or None,
        "rag_lmstudio_url": (lmstudio_url or "").strip() or None,
        "rag_lmstudio_embedding_model": (lmstudio_embedding_model or "").strip() or None,
        "rag_lmstudio_generation_model": (lmstudio_generation_model or "").strip() or None,
        "rag_lmstudio_generation_timeout_seconds": str(lmstudio_generation_timeout_seconds),
        "rag_lmstudio_generation_max_tokens": str(lmstudio_generation_max_tokens),
        "rag_lmstudio_generation_disable_thinking": (
            "true" if lmstudio_generation_disable_thinking else "false"
        ),
        "rag_gemini_url": (gemini_url or "").strip() or None,
        "rag_gemini_embedding_model": (gemini_embedding_model or "").strip() or None,
        "rag_gemini_generation_model": (gemini_generation_model or "").strip() or None,
    }
    for key, value in values.items():
        store.set(key, value)

    if clear_lmstudio_api_key:
        store.set("rag_lmstudio_api_key", None, sensitive=True)
    elif lmstudio_api_key is not None and lmstudio_api_key.strip():
        store.set("rag_lmstudio_api_key", lmstudio_api_key.strip(), sensitive=True)

    if clear_gemini_api_key:
        store.set("rag_gemini_api_key", None, sensitive=True)
    elif gemini_api_key is not None and gemini_api_key.strip():
        store.set("rag_gemini_api_key", gemini_api_key.strip(), sensitive=True)

    return resolve_rag_settings(database)
