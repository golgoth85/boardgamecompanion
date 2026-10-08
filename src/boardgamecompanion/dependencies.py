from __future__ import annotations

from boardgamecompanion.database import Database
from boardgamecompanion.settings import settings


def get_database() -> Database:
    return Database(settings.database_path)
