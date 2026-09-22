from __future__ import annotations

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
class ResolvedFloppySettings:
    url: str | None
    api_key: str | None
    timeout_seconds: float
    verify_tls: bool
    url_source: str | None
    api_key_source: str | None
    timeout_source: str
    verify_tls_source: str
    stored_url: str | None
    stored_api_key_configured: bool

    @property
    def configured(self) -> bool:
        return bool(self.url and self.api_key)

    def public_dict(self) -> dict[str, object]:
        return {
            "url": self.url or "",
            "api_key_configured": bool(self.api_key),
            "url_source": self.url_source,
            "api_key_source": self.api_key_source,
            "timeout_seconds": self.timeout_seconds,
            "verify_tls": self.verify_tls,
            "overrides": {
                "url": self.url_source == "environment",
                "api_key": self.api_key_source == "environment",
                "timeout_seconds": self.timeout_source == "environment",
                "verify_tls": self.verify_tls_source == "environment",
            },
        }


def resolve_floppy_settings(database: Database) -> ResolvedFloppySettings:
    store = AppSettingsStore(database)
    stored = store.get_many(
        (
            "floppy_url",
            "floppy_api_key",
            "floppy_timeout_seconds",
            "floppy_verify_tls",
        )
    )

    env_url = os.environ.get("BGC_FLOPPY_URL")
    env_token = os.environ.get("BGC_FLOPPY_API_KEY")
    has_env_timeout = "BGC_FLOPPY_TIMEOUT_SECONDS" in os.environ
    has_env_tls = "BGC_FLOPPY_VERIFY_TLS" in os.environ

    stored_url = stored["floppy_url"]
    stored_token = stored["floppy_api_key"]

    url = env_url if env_url else stored_url
    token = env_token if env_token else stored_token

    stored_timeout = _to_float(stored["floppy_timeout_seconds"])
    timeout = (
        float(settings.floppy_timeout_seconds)
        if has_env_timeout
        else stored_timeout if stored_timeout is not None else 8.0
    )

    stored_tls = _to_bool(stored["floppy_verify_tls"])
    verify_tls = (
        bool(settings.floppy_verify_tls)
        if has_env_tls
        else stored_tls if stored_tls is not None else True
    )

    return ResolvedFloppySettings(
        url=url,
        api_key=token,
        timeout_seconds=timeout,
        verify_tls=verify_tls,
        url_source="environment" if env_url else "stored" if stored_url else None,
        api_key_source="environment" if env_token else "stored" if stored_token else None,
        timeout_source="environment" if has_env_timeout else "stored" if stored_timeout is not None else "default",
        verify_tls_source="environment" if has_env_tls else "stored" if stored_tls is not None else "default",
        stored_url=stored_url,
        stored_api_key_configured=bool(stored_token),
    )


def save_floppy_settings(
    database: Database,
    *,
    url: str,
    api_key: str | None,
    clear_api_key: bool,
    timeout_seconds: float,
    verify_tls: bool,
) -> ResolvedFloppySettings:
    store = AppSettingsStore(database)
    normalized_url = url.strip().rstrip("/")
    store.set("floppy_url", normalized_url or None)

    if clear_api_key:
        store.set("floppy_api_key", None, sensitive=True)
    elif api_key is not None and api_key.strip():
        store.set("floppy_api_key", api_key.strip(), sensitive=True)

    store.set("floppy_timeout_seconds", str(float(timeout_seconds)))
    store.set("floppy_verify_tls", "true" if verify_tls else "false")
    return resolve_floppy_settings(database)


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None
