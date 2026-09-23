from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

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


def _normalize_barcode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = "".join(char for char in value.upper() if char.isalnum())
    return normalized or None


def _physical_copies(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS physical_copies (
            id TEXT PRIMARY KEY,
            board_game_id INTEGER NOT NULL
                REFERENCES board_games(id) ON DELETE CASCADE,
            source_collection_entry_id INTEGER
                REFERENCES collection_entries(id) ON DELETE SET NULL,
            source_copy_index INTEGER,
            source_kind TEXT NOT NULL DEFAULT 'manual',
            barcode TEXT,
            barcode_normalized TEXT,
            language TEXT,
            edition TEXT,
            publishers TEXT,
            version_year_published INTEGER,
            acquisition_date TEXT,
            acquired_from TEXT,
            price_paid REAL,
            price_currency TEXT,
            condition_text TEXT,
            inventory_location TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_collection_entry_id, source_copy_index)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_physical_copies_board_game_id
        ON physical_copies(board_game_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_physical_copies_barcode
        ON physical_copies(barcode_normalized)
        """
    )

    now = datetime.now(UTC).isoformat()
    rows = connection.execute(
        """
        SELECT id, board_game_id, barcode, version_languages,
               version_nickname, version_publishers,
               version_year_published, acquisition_date, acquired_from,
               price_paid, price_currency, condition_text,
               inventory_location, private_comment, quantity
        FROM collection_entries
        WHERE own = 1
        ORDER BY id
        """
    ).fetchall()

    for row in rows:
        quantity = row["quantity"]
        expected = int(quantity) if quantity is not None and int(quantity) > 0 else 1
        for copy_index in range(1, expected + 1):
            existing = connection.execute(
                """
                SELECT 1
                FROM physical_copies
                WHERE source_collection_entry_id = ?
                  AND source_copy_index = ?
                """,
                (row["id"], copy_index),
            ).fetchone()
            if existing:
                continue

            connection.execute(
                """
                INSERT INTO physical_copies (
                    id, board_game_id, source_collection_entry_id,
                    source_copy_index, source_kind, barcode,
                    barcode_normalized, language, edition, publishers,
                    version_year_published, acquisition_date, acquired_from,
                    price_paid, price_currency, condition_text,
                    inventory_location, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    row["board_game_id"],
                    row["id"],
                    copy_index,
                    "bgg_csv",
                    row["barcode"],
                    _normalize_barcode(row["barcode"]),
                    row["version_languages"],
                    row["version_nickname"],
                    row["version_publishers"],
                    row["version_year_published"],
                    row["acquisition_date"],
                    row["acquired_from"],
                    row["price_paid"],
                    row["price_currency"],
                    row["condition_text"],
                    row["inventory_location"],
                    row["private_comment"],
                    now,
                    now,
                ),
            )


def _game_documents(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS game_documents (
            id TEXT PRIMARY KEY,
            board_game_id INTEGER NOT NULL
                REFERENCES board_games(id) ON DELETE CASCADE,
            document_type TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'und',
            title TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            storage_path TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'application/pdf',
            source_kind TEXT NOT NULL,
            source_provider TEXT,
            source_url TEXT,
            is_official INTEGER NOT NULL DEFAULT 0,
            version_label TEXT,
            edition TEXT,
            published_at TEXT,
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(board_game_id, sha256)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_documents_board_game
        ON game_documents(board_game_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_documents_type_language
        ON game_documents(document_type, language)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_documents_sha256
        ON game_documents(sha256)
        """
    )


def _rulebook_reviews(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rulebook_review_items (
            id TEXT PRIMARY KEY,
            board_game_id INTEGER NOT NULL
                REFERENCES board_games(id) ON DELETE CASCADE,
            candidate_key TEXT NOT NULL,
            candidate_json TEXT NOT NULL,
            provider TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            url TEXT NOT NULL,
            language TEXT NOT NULL,
            document_type TEXT NOT NULL,
            official INTEGER NOT NULL DEFAULT 0,
            confidence INTEGER NOT NULL,
            policy_action TEXT NOT NULL
                CHECK(policy_action IN ('review', 'unattended')),
            policy_reasons_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL
                CHECK(status IN ('pending', 'approved', 'rejected')),
            decision_source TEXT
                CHECK(decision_source IS NULL OR decision_source IN ('policy', 'user')),
            decision_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decided_at TEXT,
            UNIQUE(board_game_id, candidate_key)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rulebook_review_status
        ON rulebook_review_items(status, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rulebook_review_game
        ON rulebook_review_items(board_game_id, created_at)
        """
    )


MIGRATIONS = (
    Migration(1, "baseline-existing-schema", _baseline),
    Migration(2, "physical-copies", _physical_copies),
    Migration(3, "game-documents", _game_documents),
    Migration(4, "rulebook-review-queue", _rulebook_reviews),
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
