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
            CHECK(
                (
                    status = 'pending'
                    AND policy_action = 'review'
                    AND decision_source IS NULL
                    AND decision_note IS NULL
                    AND decided_at IS NULL
                )
                OR (
                    status = 'approved'
                    AND policy_action = 'unattended'
                    AND decision_source = 'policy'
                    AND decision_note IS NULL
                    AND decided_at IS NOT NULL
                )
                OR (
                    status = 'approved'
                    AND policy_action = 'review'
                    AND decision_source = 'user'
                    AND decided_at IS NOT NULL
                )
                OR (
                    status = 'rejected'
                    AND policy_action = 'review'
                    AND decision_source = 'user'
                    AND decided_at IS NOT NULL
                )
            ),
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


def _rulebook_updates(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rulebook_update_targets (
            id TEXT PRIMARY KEY,
            review_item_id TEXT NOT NULL UNIQUE
                REFERENCES rulebook_review_items(id) ON DELETE CASCADE,
            board_game_id INTEGER NOT NULL
                REFERENCES board_games(id) ON DELETE CASCADE,
            enabled INTEGER NOT NULL DEFAULT 1
                CHECK(enabled IN (0, 1)),
            interval_seconds INTEGER NOT NULL
                CHECK(interval_seconds BETWEEN 3600 AND 31536000),
            next_check_at TEXT NOT NULL,
            last_checked_at TEXT,
            last_success_at TEXT,
            last_document_id TEXT
                REFERENCES game_documents(id) ON DELETE RESTRICT,
            last_sha256 TEXT,
            consecutive_failures INTEGER NOT NULL DEFAULT 0
                CHECK(consecutive_failures >= 0),
            last_outcome TEXT
                CHECK(last_outcome IS NULL OR last_outcome IN ('created', 'unchanged', 'failed')),
            last_failure_code TEXT,
            last_failure_message TEXT,
            lease_owner TEXT,
            lease_until TEXT,
            lease_generation INTEGER NOT NULL DEFAULT 0
                CHECK(lease_generation >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK(
                (lease_owner IS NULL AND lease_until IS NULL)
                OR (lease_owner IS NOT NULL AND lease_until IS NOT NULL)
            ),
            CHECK(
                (
                    last_outcome IS NULL
                    AND last_checked_at IS NULL
                    AND last_success_at IS NULL
                    AND last_document_id IS NULL
                    AND last_sha256 IS NULL
                    AND consecutive_failures = 0
                    AND last_failure_code IS NULL
                    AND last_failure_message IS NULL
                )
                OR (
                    last_outcome = 'failed'
                    AND last_checked_at IS NOT NULL
                    AND consecutive_failures > 0
                    AND last_failure_code IS NOT NULL
                    AND (
                        (
                            last_success_at IS NULL
                            AND last_document_id IS NULL
                            AND last_sha256 IS NULL
                        )
                        OR (
                            last_success_at IS NOT NULL
                            AND last_document_id IS NOT NULL
                            AND last_sha256 IS NOT NULL
                        )
                    )
                )
                OR (
                    last_outcome IN ('created', 'unchanged')
                    AND last_checked_at IS NOT NULL
                    AND last_success_at IS NOT NULL
                    AND last_document_id IS NOT NULL
                    AND last_sha256 IS NOT NULL
                    AND consecutive_failures = 0
                    AND last_failure_code IS NULL
                    AND last_failure_message IS NULL
                )
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rulebook_update_due
        ON rulebook_update_targets(enabled, next_check_at, lease_until)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rulebook_update_game
        ON rulebook_update_targets(board_game_id, next_check_at)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rulebook_update_runs (
            id TEXT PRIMARY KEY,
            target_id TEXT NOT NULL
                REFERENCES rulebook_update_targets(id) ON DELETE CASCADE,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            outcome TEXT NOT NULL
                CHECK(outcome IN ('created', 'unchanged', 'failed')),
            document_id TEXT
                REFERENCES game_documents(id) ON DELETE RESTRICT,
            sha256 TEXT,
            requested_url TEXT,
            final_url TEXT,
            status_code INTEGER,
            byte_size INTEGER NOT NULL DEFAULT 0
                CHECK(byte_size >= 0),
            failure_code TEXT,
            failure_message TEXT,
            http_metadata_json TEXT NOT NULL DEFAULT '{}',
            redirect_chain_json TEXT NOT NULL DEFAULT '[]',
            CHECK(
                (
                    outcome = 'failed'
                    AND document_id IS NULL
                    AND failure_code IS NOT NULL
                )
                OR (
                    outcome IN ('created', 'unchanged')
                    AND document_id IS NOT NULL
                    AND sha256 IS NOT NULL
                    AND requested_url IS NOT NULL
                    AND failure_code IS NULL
                    AND failure_message IS NULL
                )
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rulebook_update_runs_target
        ON rulebook_update_runs(target_id, started_at DESC)
        """
    )


def _pdf_page_ingestion(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_parse_runs (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL
                REFERENCES game_documents(id) ON DELETE CASCADE,
            document_sha256 TEXT NOT NULL
                CHECK(
                    length(document_sha256) = 64
                    AND document_sha256 NOT GLOB '*[^0-9a-f]*'
                ),
            parser_name TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK(status IN ('succeeded', 'failed')),
            page_count INTEGER CHECK(page_count IS NULL OR page_count >= 0),
            text_page_count INTEGER
                CHECK(text_page_count IS NULL OR text_page_count >= 0),
            empty_page_count INTEGER
                CHECK(empty_page_count IS NULL OR empty_page_count >= 0),
            error_page_count INTEGER
                CHECK(error_page_count IS NULL OR error_page_count >= 0),
            total_text_chars INTEGER
                CHECK(total_text_chars IS NULL OR total_text_chars >= 0),
            warning_count INTEGER NOT NULL DEFAULT 0
                CHECK(warning_count >= 0),
            diagnostics_json TEXT NOT NULL DEFAULT '{}',
            error_code TEXT,
            error_message TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            UNIQUE(id, document_id),
            CHECK(
                (
                    status = 'succeeded'
                    AND page_count IS NOT NULL
                    AND text_page_count IS NOT NULL
                    AND empty_page_count IS NOT NULL
                    AND error_page_count IS NOT NULL
                    AND total_text_chars IS NOT NULL
                    AND page_count =
                        text_page_count + empty_page_count + error_page_count
                    AND error_code IS NULL
                    AND error_message IS NULL
                )
                OR (
                    status = 'failed'
                    AND page_count IS NULL
                    AND text_page_count IS NULL
                    AND empty_page_count IS NULL
                    AND error_page_count IS NULL
                    AND total_text_chars IS NULL
                    AND error_code IS NOT NULL
                    AND error_message IS NOT NULL
                )
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_parse_runs_document
        ON document_parse_runs(document_id, finished_at DESC)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_pages (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL
                REFERENCES game_documents(id) ON DELETE CASCADE,
            parse_run_id TEXT NOT NULL,
            page_index INTEGER NOT NULL CHECK(page_index >= 0),
            page_number INTEGER NOT NULL CHECK(page_number >= 1),
            text TEXT NOT NULL,
            text_sha256 TEXT NOT NULL
                CHECK(
                    length(text_sha256) = 64
                    AND text_sha256 NOT GLOB '*[^0-9a-f]*'
                ),
            char_count INTEGER NOT NULL CHECK(char_count >= 0),
            extraction_status TEXT NOT NULL
                CHECK(extraction_status IN ('text', 'empty', 'error')),
            diagnostics_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(parse_run_id, document_id)
                REFERENCES document_parse_runs(id, document_id)
                ON DELETE CASCADE,
            CHECK(page_number = page_index + 1),
            UNIQUE(document_id, page_index),
            UNIQUE(document_id, page_number)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_pages_run
        ON document_pages(parse_run_id, page_number)
        """
    )


def _document_chunks(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_game_documents_id_board_game
        ON game_documents(id, board_game_id)
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_document_pages_chunk_parent
        ON document_pages(
            id, document_id, parse_run_id, page_number, text_sha256
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunk_runs (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            board_game_id INTEGER NOT NULL,
            parse_run_id TEXT NOT NULL,
            document_sha256 TEXT NOT NULL
                CHECK(
                    length(document_sha256) = 64
                    AND document_sha256 NOT GLOB '*[^0-9a-f]*'
                ),
            document_metadata_sha256 TEXT NOT NULL
                CHECK(
                    length(document_metadata_sha256) = 64
                    AND document_metadata_sha256 NOT GLOB '*[^0-9a-f]*'
                ),
            source_pages_sha256 TEXT NOT NULL
                CHECK(
                    length(source_pages_sha256) = 64
                    AND source_pages_sha256 NOT GLOB '*[^0-9a-f]*'
                ),
            chunker_name TEXT NOT NULL,
            chunker_version TEXT NOT NULL,
            chunker_config_json TEXT NOT NULL,
            page_count INTEGER NOT NULL CHECK(page_count >= 0),
            indexed_page_count INTEGER NOT NULL
                CHECK(indexed_page_count >= 0 AND indexed_page_count <= page_count),
            chunk_count INTEGER NOT NULL CHECK(chunk_count >= 0),
            total_chunk_chars INTEGER NOT NULL CHECK(total_chunk_chars >= 0),
            created_at TEXT NOT NULL,
            UNIQUE(
                id, document_id, parse_run_id, board_game_id,
                document_sha256, document_metadata_sha256,
                chunker_name, chunker_version, chunker_config_json
            ),
            FOREIGN KEY(document_id, board_game_id)
                REFERENCES game_documents(id, board_game_id)
                ON DELETE CASCADE,
            FOREIGN KEY(parse_run_id, document_id)
                REFERENCES document_parse_runs(id, document_id)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_chunk_runs_document
        ON document_chunk_runs(document_id, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunks (
            id TEXT PRIMARY KEY,
            chunk_key TEXT NOT NULL UNIQUE
                CHECK(
                    length(chunk_key) = 64
                    AND chunk_key NOT GLOB '*[^0-9a-f]*'
                ),
            chunk_run_id TEXT NOT NULL,
            board_game_id INTEGER NOT NULL,
            document_id TEXT NOT NULL,
            document_sha256 TEXT NOT NULL
                CHECK(
                    length(document_sha256) = 64
                    AND document_sha256 NOT GLOB '*[^0-9a-f]*'
                ),
            document_metadata_sha256 TEXT NOT NULL
                CHECK(
                    length(document_metadata_sha256) = 64
                    AND document_metadata_sha256 NOT GLOB '*[^0-9a-f]*'
                ),
            parse_run_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            page_number INTEGER NOT NULL CHECK(page_number >= 1),
            page_text_sha256 TEXT NOT NULL
                CHECK(
                    length(page_text_sha256) = 64
                    AND page_text_sha256 NOT GLOB '*[^0-9a-f]*'
                ),
            chunk_index INTEGER NOT NULL CHECK(chunk_index >= 0),
            start_char INTEGER NOT NULL CHECK(start_char >= 0),
            end_char INTEGER NOT NULL CHECK(end_char > start_char),
            text TEXT NOT NULL,
            text_sha256 TEXT NOT NULL
                CHECK(
                    length(text_sha256) = 64
                    AND text_sha256 NOT GLOB '*[^0-9a-f]*'
                ),
            char_count INTEGER NOT NULL CHECK(char_count > 0),
            language TEXT NOT NULL,
            document_type TEXT NOT NULL,
            version_label TEXT,
            edition TEXT,
            source_kind TEXT NOT NULL,
            source_provider TEXT,
            source_url TEXT,
            is_official INTEGER NOT NULL CHECK(is_official IN (0, 1)),
            document_provenance_json TEXT NOT NULL DEFAULT '{}',
            chunker_name TEXT NOT NULL,
            chunker_version TEXT NOT NULL,
            chunker_config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(
                chunk_run_id, document_id, parse_run_id, board_game_id,
                document_sha256, document_metadata_sha256,
                chunker_name, chunker_version, chunker_config_json
            ) REFERENCES document_chunk_runs(
                id, document_id, parse_run_id, board_game_id,
                document_sha256, document_metadata_sha256,
                chunker_name, chunker_version, chunker_config_json
            ) ON DELETE CASCADE,
            FOREIGN KEY(
                page_id, document_id, parse_run_id,
                page_number, page_text_sha256
            ) REFERENCES document_pages(
                id, document_id, parse_run_id,
                page_number, text_sha256
            ) ON DELETE CASCADE,
            CHECK(char_count = end_char - start_char),
            UNIQUE(document_id, page_id, chunk_index)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_chunks_document
        ON document_chunks(document_id, page_number, chunk_index)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_chunks_game
        ON document_chunks(board_game_id, document_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_chunks_page
        ON document_chunks(page_id, chunk_index)
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_game_documents_invalidate_chunks
        AFTER UPDATE OF
            board_game_id, sha256, document_type, language,
            version_label, edition, source_kind, source_provider,
            source_url, is_official, provenance_json
        ON game_documents
        WHEN
            OLD.board_game_id IS NOT NEW.board_game_id
            OR OLD.sha256 IS NOT NEW.sha256
            OR OLD.document_type IS NOT NEW.document_type
            OR OLD.language IS NOT NEW.language
            OR OLD.version_label IS NOT NEW.version_label
            OR OLD.edition IS NOT NEW.edition
            OR OLD.source_kind IS NOT NEW.source_kind
            OR OLD.source_provider IS NOT NEW.source_provider
            OR OLD.source_url IS NOT NEW.source_url
            OR OLD.is_official IS NOT NEW.is_official
            OR OLD.provenance_json IS NOT NEW.provenance_json
        BEGIN
            DELETE FROM document_chunks WHERE document_id = NEW.id;
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_document_pages_invalidate_chunks
        AFTER UPDATE OF text, char_count, extraction_status, diagnostics_json
        ON document_pages
        WHEN
            OLD.text IS NOT NEW.text
            OR OLD.char_count IS NOT NEW.char_count
            OR OLD.extraction_status IS NOT NEW.extraction_status
            OR OLD.diagnostics_json IS NOT NEW.diagnostics_json
        BEGIN
            DELETE FROM document_chunks WHERE page_id = NEW.id;
        END
        """
    )



MIGRATIONS = (
    Migration(1, "baseline-existing-schema", _baseline),
    Migration(2, "physical-copies", _physical_copies),
    Migration(3, "game-documents", _game_documents),
    Migration(4, "rulebook-review-queue", _rulebook_reviews),
    Migration(5, "rulebook-scheduled-updates", _rulebook_updates),
    Migration(6, "pdf-page-ingestion", _pdf_page_ingestion),
    Migration(7, "document-chunks", _document_chunks),
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
