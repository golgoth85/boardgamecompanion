from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime


MigrationFn = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: MigrationFn


BASELINE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS board_games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bgg_id INTEGER NOT NULL UNIQUE,
        title TEXT NOT NULL,
        original_title TEXT,
        year_published INTEGER,
        item_type TEXT,
        min_players INTEGER,
        max_players INTEGER,
        playing_time INTEGER,
        min_play_time INTEGER,
        max_play_time INTEGER,
        bgg_average REAL,
        bgg_bayes_average REAL,
        bgg_average_weight REAL,
        bgg_rank INTEGER,
        bgg_num_owned INTEGER,
        bgg_best_players TEXT,
        bgg_recommended_players TEXT,
        bgg_recommended_age TEXT,
        bgg_language_dependence TEXT,
        source_metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_board_games_title ON board_games(title COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS idx_board_games_item_type ON board_games(item_type)",
    """
    CREATE TABLE IF NOT EXISTS collection_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        coll_id INTEGER UNIQUE,
        board_game_id INTEGER NOT NULL REFERENCES board_games(id) ON DELETE CASCADE,
        user_rating REAL,
        num_plays INTEGER,
        user_weight REAL,
        own INTEGER NOT NULL DEFAULT 0,
        for_trade INTEGER NOT NULL DEFAULT 0,
        want INTEGER NOT NULL DEFAULT 0,
        want_to_buy INTEGER NOT NULL DEFAULT 0,
        want_to_play INTEGER NOT NULL DEFAULT 0,
        previously_owned INTEGER NOT NULL DEFAULT 0,
        preordered INTEGER NOT NULL DEFAULT 0,
        wishlist INTEGER NOT NULL DEFAULT 0,
        wishlist_priority INTEGER,
        wishlist_comment TEXT,
        public_comment TEXT,
        condition_text TEXT,
        barcode TEXT,
        price_paid REAL,
        price_currency TEXT,
        current_value REAL,
        current_value_currency TEXT,
        acquisition_date TEXT,
        acquired_from TEXT,
        quantity INTEGER,
        private_comment TEXT,
        inventory_location TEXT,
        inventory_date TEXT,
        version_publishers TEXT,
        version_languages TEXT,
        version_year_published INTEGER,
        version_nickname TEXT,
        source_metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_collection_entries_board_game_id ON collection_entries(board_game_id)",
    "CREATE INDEX IF NOT EXISTS idx_collection_entries_owned ON collection_entries(own)",
    """
    CREATE TABLE IF NOT EXISTS import_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_filename TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        row_count INTEGER NOT NULL,
        created_count INTEGER NOT NULL,
        updated_count INTEGER NOT NULL,
        unchanged_count INTEGER NOT NULL,
        imported_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        sensitive INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS floppy_links (
        bgg_id INTEGER PRIMARY KEY,
        source TEXT NOT NULL,
        media_id TEXT NOT NULL,
        item_db_id INTEGER,
        collection_entry_id INTEGER,
        link_method TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_floppy_links_remote ON floppy_links(source, media_id)",
    """
    CREATE TABLE IF NOT EXISTS floppy_sync_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_hash TEXT NOT NULL,
        attempted INTEGER NOT NULL,
        media_created INTEGER NOT NULL,
        collection_created INTEGER NOT NULL,
        skipped INTEGER NOT NULL,
        failed INTEGER NOT NULL,
        result_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
)


def _baseline(connection: sqlite3.Connection) -> None:
    for statement in BASELINE_STATEMENTS:
        connection.execute(statement)


MIGRATIONS = (
    Migration(1, "baseline-existing-schema", _baseline),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version


def migrate(connection: sqlite3.Connection) -> int:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.commit()

    applied = {
        int(row["version"])
        for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }

    for migration in MIGRATIONS:
        if migration.version in applied:
            continue

        connection.execute("BEGIN IMMEDIATE")
        try:
            migration.apply(connection)
            connection.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
    ).fetchone()
    return int(row["version"])
