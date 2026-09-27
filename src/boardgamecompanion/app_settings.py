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
