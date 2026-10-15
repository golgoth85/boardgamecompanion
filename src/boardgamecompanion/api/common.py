from boardgamecompanion.database import Database
from boardgamecompanion.settings import settings


def database() -> Database:
    db = Database(settings.database_path)
    db.initialize()
    return db
