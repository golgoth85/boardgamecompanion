from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;

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
);

CREATE INDEX IF NOT EXISTS idx_board_games_title ON board_games(title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_board_games_item_type ON board_games(item_type);

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
);

CREATE INDEX IF NOT EXISTS idx_collection_entries_board_game_id ON collection_entries(board_game_id);
CREATE INDEX IF NOT EXISTS idx_collection_entries_owned ON collection_entries(own);

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
);

CREATE TABLE IF NOT EXISTS external_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_game_id INTEGER NOT NULL REFERENCES board_games(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    external_source TEXT NOT NULL,
    external_media_id TEXT NOT NULL,
    external_item_id TEXT,
    external_collection_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(board_game_id, provider),
    UNIQUE(provider, external_source, external_media_id)
);

CREATE INDEX IF NOT EXISTS idx_external_links_provider
ON external_links(provider);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
