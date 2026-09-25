from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from boardgamecompanion.database import Database
from boardgamecompanion.migrations import (
    BASELINE_STATEMENTS,
    LATEST_SCHEMA_VERSION,
    MIGRATIONS,
)


def test_initialize_records_schema_version_and_is_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")

    database.initialize()
    first_version = database.schema_version()
    database.initialize()
    second_version = database.schema_version()

    assert first_version == LATEST_SCHEMA_VERSION == 8
    assert second_version == 8

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert [(row["version"], row["name"]) for row in rows] == [
        (1, "baseline-existing-schema"),
        (2, "physical-copies"),
        (3, "game-documents"),
        (4, "rulebook-review-queue"),
        (5, "rulebook-scheduled-updates"),
        (6, "pdf-page-ingestion"),
        (7, "document-chunks"),
        (8, "chunk-embeddings"),
    ]
    assert {
        "board_games",
        "collection_entries",
        "import_runs",
        "app_settings",
        "floppy_links",
        "floppy_sync_runs",
        "physical_copies",
        "game_documents",
        "rulebook_review_items",
        "rulebook_update_targets",
        "rulebook_update_runs",
        "document_parse_runs",
        "document_pages",
        "document_chunk_runs",
        "document_chunks",
        "document_embedding_runs",
        "chunk_embeddings",
        "schema_migrations",
    } <= tables


def test_existing_pre_migration_database_is_adopted_without_data_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for statement in BASELINE_STATEMENTS:
            connection.execute(statement)

        connection.execute(
            """
            INSERT INTO board_games (
                bgg_id, title, source_metadata_json, created_at, updated_at
            ) VALUES (12345, 'Legacy Game', '{}', 'before', 'before')
            """
        )
        board_game_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id = 12345"
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO collection_entries (
                coll_id, board_game_id, own, source_metadata_json,
                created_at, updated_at
            ) VALUES (777, ?, 1, '{}', 'before', 'before')
            """,
            (board_game_id,),
        )
        connection.execute(
            """
            INSERT INTO app_settings (key, value, sensitive, updated_at)
            VALUES ('floppy_url', 'http://floppy:8000', 0, 'before')
            """
        )
        connection.commit()
    finally:
        connection.close()

    database = Database(path)
    database.initialize()

    with database.connect() as connection:
        game = connection.execute(
            "SELECT bgg_id, title, created_at FROM board_games WHERE bgg_id = 12345"
        ).fetchone()
        collection = connection.execute(
            "SELECT coll_id, own FROM collection_entries WHERE coll_id = 777"
        ).fetchone()
        setting = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'floppy_url'"
        ).fetchone()
        migrations = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        copies = connection.execute(
            """
            SELECT pc.source_kind, pc.source_copy_index, g.bgg_id
            FROM physical_copies pc
            JOIN board_games g ON g.id = pc.board_game_id
            WHERE g.bgg_id = 12345
            """
        ).fetchall()

    assert dict(game) == {
        "bgg_id": 12345,
        "title": "Legacy Game",
        "created_at": "before",
    }
    assert dict(collection) == {"coll_id": 777, "own": 1}
    assert setting["value"] == "http://floppy:8000"
    assert [row["version"] for row in migrations] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert [dict(row) for row in copies] == [
        {
            "source_kind": "bgg_csv",
            "source_copy_index": 1,
            "bgg_id": 12345,
        }
    ]


def test_v4_database_with_existing_review_upgrades_to_v5_without_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v4.sqlite3"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    for migration in MIGRATIONS[:4]:
        migration.apply(connection)
        connection.execute(
            """
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (?, ?, 'before')
            """,
            (migration.version, migration.name),
        )

    connection.execute(
        """
        INSERT INTO board_games (
            bgg_id, title, source_metadata_json, created_at, updated_at
        ) VALUES (54321, 'Existing Review Game', '{}', 'before', 'before')
        """
    )
    game_id = connection.execute(
        "SELECT id FROM board_games WHERE bgg_id = 54321"
    ).fetchone()["id"]
    connection.execute(
        """
        INSERT INTO rulebook_review_items (
            id, board_game_id, candidate_key, candidate_json,
            provider, source_kind, url, language, document_type,
            official, confidence, policy_action, policy_reasons_json,
            status, decision_source, decision_note,
            created_at, updated_at, decided_at
        ) VALUES (
            'review-existing', ?, ?, ?,
            'publisher-test', 'official_publisher',
            'https://publisher.example/rules.pdf', 'it', 'rulebook',
            1, 100, 'unattended',
            '["source:official","confidence:100","bgg_id:exact","language:it"]',
            'approved', 'policy', NULL,
            'before', 'before', 'before'
        )
        """,
        (
            game_id,
            "a" * 64,
            (
                '{"bgg_id":54321,"confidence":100,"document_type":"rulebook",'
                '"edition":null,"game_title":"Existing Review Game",'
                '"language":"it","metadata":{},"official":true,'
                '"provider":"publisher-test","publisher":null,'
                '"source_kind":"official_publisher","title":null,'
                '"url":"https://publisher.example/rules.pdf",'
                '"version_label":null,"year":null}'
            ),
        ),
    )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()

    with database.connect() as connection:
        review = connection.execute(
            """
            SELECT id, status, decision_source
            FROM rulebook_review_items
            WHERE id = 'review-existing'
            """
        ).fetchone()
        targets = connection.execute(
            "SELECT COUNT(*) AS count FROM rulebook_update_targets"
        ).fetchone()["count"]
        runs = connection.execute(
            "SELECT COUNT(*) AS count FROM rulebook_update_runs"
        ).fetchone()["count"]

    assert database.schema_version() == 8
    assert dict(review) == {
        "id": "review-existing",
        "status": "approved",
        "decision_source": "policy",
    }
    assert targets == 0
    assert runs == 0


def test_v5_database_with_archived_document_upgrades_to_v6_without_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v5.sqlite3"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    for migration in MIGRATIONS[:5]:
        migration.apply(connection)
        connection.execute(
            """
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (?, ?, 'before')
            """,
            (migration.version, migration.name),
        )

    connection.execute(
        """
        INSERT INTO board_games (
            bgg_id, title, source_metadata_json, created_at, updated_at
        ) VALUES (67890, 'Archived Game', '{}', 'before', 'before')
        """
    )
    game_id = connection.execute(
        "SELECT id FROM board_games WHERE bgg_id = 67890"
    ).fetchone()["id"]
    connection.execute(
        """
        INSERT INTO game_documents (
            id, board_game_id, document_type, language, title,
            original_filename, storage_path, sha256, size_bytes,
            mime_type, source_kind, source_provider, source_url,
            is_official, version_label, edition, published_at,
            provenance_json, created_at, updated_at
        ) VALUES (
            'doc-existing', ?, 'rulebook', 'it', 'Regolamento',
            'rules.pdf', '67890/doc-existing.pdf', ?, 123,
            'application/pdf', 'rulebook_fetch', 'publisher-test',
            'https://publisher.example/rules.pdf',
            1, 'v1', 'Retail IT', NULL,
            '{"ingest":"rulebook_fetch"}', 'before', 'before'
        )
        """,
        (game_id, "a" * 64),
    )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()

    with database.connect() as connection:
        document = connection.execute(
            """
            SELECT id, document_type, language, version_label, edition, is_official
            FROM game_documents
            WHERE id = 'doc-existing'
            """
        ).fetchone()
        parse_runs = connection.execute(
            "SELECT COUNT(*) AS count FROM document_parse_runs"
        ).fetchone()["count"]
        pages = connection.execute(
            "SELECT COUNT(*) AS count FROM document_pages"
        ).fetchone()["count"]

    assert database.schema_version() == 8
    assert dict(document) == {
        "id": "doc-existing",
        "document_type": "rulebook",
        "language": "it",
        "version_label": "v1",
        "edition": "Retail IT",
        "is_official": 1,
    }
    assert parse_runs == 0
    assert pages == 0


def test_pdf_page_provenance_cannot_cross_documents(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()

    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO board_games (
                bgg_id, title, source_metadata_json, created_at, updated_at
            ) VALUES (70001, 'Provenance Game', '{}', 'now', 'now')
            """
        )
        game_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id = 70001"
        ).fetchone()["id"]
        for document_id, suffix in (("doc-a", "a"), ("doc-b", "b")):
            connection.execute(
                """
                INSERT INTO game_documents (
                    id, board_game_id, document_type, language, title,
                    original_filename, storage_path, sha256, size_bytes,
                    mime_type, source_kind, is_official, provenance_json,
                    created_at, updated_at
                ) VALUES (
                    ?, ?, 'rulebook', 'en', ?,
                    ?, ?, ?, 10,
                    'application/pdf', 'manual_upload', 0, '{}',
                    'now', 'now'
                )
                """,
                (
                    document_id,
                    game_id,
                    document_id,
                    f"{document_id}.pdf",
                    f"70001/{document_id}.pdf",
                    suffix * 64,
                ),
            )
        connection.execute(
            """
            INSERT INTO document_parse_runs (
                id, document_id, document_sha256,
                parser_name, parser_version, status,
                page_count, text_page_count, empty_page_count,
                error_page_count, total_text_chars, warning_count,
                diagnostics_json, started_at, finished_at
            ) VALUES (
                'run-a', 'doc-a', ?, 'pypdf', '6.19.0', 'succeeded',
                1, 1, 0, 0, 4, 0, '{}', 'now', 'now'
            )
            """,
            ("a" * 64,),
        )

    with database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO document_pages (
                    id, document_id, parse_run_id,
                    page_index, page_number, text, text_sha256,
                    char_count, extraction_status, diagnostics_json, created_at
                ) VALUES (
                    'page-crossed', 'doc-b', 'run-a',
                    0, 1, 'text', ?, 4, 'text', '{}', 'now'
                )
                """,
                ("c" * 64,),
            )


def test_v6_database_with_pages_upgrades_to_v8_without_loss(tmp_path: Path) -> None:
    path = tmp_path / "v6.sqlite3"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    for migration in MIGRATIONS[:6]:
        migration.apply(connection)
        connection.execute(
            """
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (?, ?, 'before')
            """,
            (migration.version, migration.name),
        )

    connection.execute(
        """
        INSERT INTO board_games (
            bgg_id, title, source_metadata_json, created_at, updated_at
        ) VALUES (71234, 'Chunk Migration Game', '{}', 'before', 'before')
        """
    )
    game_id = connection.execute(
        "SELECT id FROM board_games WHERE bgg_id = 71234"
    ).fetchone()["id"]
    connection.execute(
        """
        INSERT INTO game_documents (
            id, board_game_id, document_type, language, title,
            original_filename, storage_path, sha256, size_bytes,
            mime_type, source_kind, is_official, provenance_json,
            created_at, updated_at
        ) VALUES (
            'doc-v6', ?, 'rulebook', 'en', 'Rules',
            'rules.pdf', '71234/doc-v6.pdf', ?, 10,
            'application/pdf', 'manual_upload', 0, '{}',
            'before', 'before'
        )
        """,
        (game_id, "a" * 64),
    )
    connection.execute(
        """
        INSERT INTO document_parse_runs (
            id, document_id, document_sha256,
            parser_name, parser_version, status,
            page_count, text_page_count, empty_page_count,
            error_page_count, total_text_chars, warning_count,
            diagnostics_json, started_at, finished_at
        ) VALUES (
            'run-v6', 'doc-v6', ?, 'pypdf', '6.19.0', 'succeeded',
            1, 1, 0, 0, 4, 0, '{}', 'before', 'before'
        )
        """,
        ("a" * 64,),
    )
    connection.execute(
        """
        INSERT INTO document_pages (
            id, document_id, parse_run_id,
            page_index, page_number, text, text_sha256,
            char_count, extraction_status, diagnostics_json, created_at
        ) VALUES (
            'page-v6', 'doc-v6', 'run-v6',
            0, 1, 'text', ?, 4, 'text', '{}', 'before'
        )
        """,
        (hashlib.sha256(b"text").hexdigest(),),
    )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()

    with database.connect() as connection:
        page = connection.execute(
            """
            SELECT id, document_id, parse_run_id, page_number, text
            FROM document_pages
            WHERE id = 'page-v6'
            """
        ).fetchone()
        runs = connection.execute(
            "SELECT COUNT(*) AS count FROM document_chunk_runs"
        ).fetchone()["count"]
        chunks = connection.execute(
            "SELECT COUNT(*) AS count FROM document_chunks"
        ).fetchone()["count"]

    assert database.schema_version() == 8
    assert dict(page) == {
        "id": "page-v6",
        "document_id": "doc-v6",
        "parse_run_id": "run-v6",
        "page_number": 1,
        "text": "text",
    }
    assert runs == 0
    assert chunks == 0


def test_v7_chunk_foreign_keys_reject_cross_run_provenance(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()

    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO board_games (
                bgg_id, title, source_metadata_json, created_at, updated_at
            ) VALUES (72345, 'Chunk FK Game', '{}', 'now', 'now')
            """
        )
        game_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id = 72345"
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO game_documents (
                id, board_game_id, document_type, language, title,
                original_filename, storage_path, sha256, size_bytes,
                mime_type, source_kind, is_official, provenance_json,
                created_at, updated_at
            ) VALUES (
                'doc-fk', ?, 'rulebook', 'en', 'Rules',
                'rules.pdf', '72345/doc-fk.pdf', ?, 10,
                'application/pdf', 'manual_upload', 0, '{}',
                'now', 'now'
            )
            """,
            (game_id, "a" * 64),
        )
        page_sha = hashlib.sha256(b"text").hexdigest()
        connection.execute(
            """
            INSERT INTO document_parse_runs (
                id, document_id, document_sha256,
                parser_name, parser_version, status,
                page_count, text_page_count, empty_page_count,
                error_page_count, total_text_chars, warning_count,
                diagnostics_json, started_at, finished_at
            ) VALUES (
                'run-fk', 'doc-fk', ?, 'pypdf', '6.19.0', 'succeeded',
                1, 1, 0, 0, 4, 0, '{}', 'now', 'now'
            )
            """,
            ("a" * 64,),
        )
        connection.execute(
            """
            INSERT INTO document_pages (
                id, document_id, parse_run_id,
                page_index, page_number, text, text_sha256,
                char_count, extraction_status, diagnostics_json, created_at
            ) VALUES (
                'page-fk', 'doc-fk', 'run-fk',
                0, 1, 'text', ?, 4, 'text', '{}', 'now'
            )
            """,
            (page_sha,),
        )
        connection.execute(
            """
            INSERT INTO document_chunk_runs (
                id, document_id, board_game_id, parse_run_id,
                document_sha256, document_metadata_sha256,
                source_pages_sha256, chunker_name, chunker_version,
                chunker_config_json, page_count, indexed_page_count,
                chunk_count, total_chunk_chars, created_at
            ) VALUES (
                'chunk-run-fk', 'doc-fk', ?, 'run-fk',
                ?, ?, ?, 'page-char-window', '1',
                '{"max_chars":200,"min_break_chars":100,"overlap_chars":20}',
                1, 1, 1, 4, 'now'
            )
            """,
            (game_id, "a" * 64, "b" * 64, "c" * 64),
        )

    with database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO document_chunks (
                    id, chunk_key, chunk_run_id,
                    board_game_id, document_id, document_sha256,
                    document_metadata_sha256, parse_run_id,
                    page_id, page_number, page_text_sha256,
                    chunk_index, start_char, end_char,
                    text, text_sha256, char_count,
                    language, document_type,
                    source_kind, is_official, document_provenance_json,
                    chunker_name, chunker_version, chunker_config_json,
                    created_at
                ) VALUES (
                    'chunk-fk', ?, 'chunk-run-fk',
                    ?, 'doc-fk', ?,
                    ?, 'run-fk',
                    'page-fk', 1, ?,
                    0, 0, 4,
                    'text', ?, 4,
                    'en', 'rulebook',
                    'manual_upload', 0, '{}',
                    'different-chunker', '1',
                    '{"max_chars":200,"min_break_chars":100,"overlap_chars":20}',
                    'now'
                )
                """,
                (
                    "d" * 64,
                    game_id,
                    "a" * 64,
                    "b" * 64,
                    page_sha,
                    page_sha,
                ),
            )


def test_v7_database_with_chunks_upgrades_to_v8_without_loss(tmp_path: Path) -> None:
    path = tmp_path / "v7.sqlite3"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    for migration in MIGRATIONS[:7]:
        migration.apply(connection)
        connection.execute(
            """
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (?, ?, 'before')
            """,
            (migration.version, migration.name),
        )

    connection.execute(
        """
        INSERT INTO board_games (
            bgg_id, title, source_metadata_json, created_at, updated_at
        ) VALUES (73456, 'Embedding Migration Game', '{}', 'before', 'before')
        """
    )
    game_id = connection.execute(
        "SELECT id FROM board_games WHERE bgg_id = 73456"
    ).fetchone()["id"]
    connection.execute(
        """
        INSERT INTO game_documents (
            id, board_game_id, document_type, language, title,
            original_filename, storage_path, sha256, size_bytes,
            mime_type, source_kind, is_official, provenance_json,
            created_at, updated_at
        ) VALUES (
            'doc-v7', ?, 'rulebook', 'en', 'Rules',
            'rules.pdf', '73456/doc-v7.pdf', ?, 10,
            'application/pdf', 'manual_upload', 0, '{}',
            'before', 'before'
        )
        """,
        (game_id, "a" * 64),
    )
    page_text = "text"
    page_sha = hashlib.sha256(page_text.encode()).hexdigest()
    connection.execute(
        """
        INSERT INTO document_parse_runs (
            id, document_id, document_sha256,
            parser_name, parser_version, status,
            page_count, text_page_count, empty_page_count,
            error_page_count, total_text_chars, warning_count,
            diagnostics_json, started_at, finished_at
        ) VALUES (
            'run-v7', 'doc-v7', ?, 'pypdf', '6.19.0', 'succeeded',
            1, 1, 0, 0, 4, 0, '{}', 'before', 'before'
        )
        """,
        ("a" * 64,),
    )
    connection.execute(
        """
        INSERT INTO document_pages (
            id, document_id, parse_run_id,
            page_index, page_number, text, text_sha256,
            char_count, extraction_status, diagnostics_json, created_at
        ) VALUES (
            'page-v7', 'doc-v7', 'run-v7',
            0, 1, ?, ?, 4, 'text', '{}', 'before'
        )
        """,
        (page_text, page_sha),
    )
    config = '{"max_chars":200,"min_break_chars":100,"overlap_chars":20}'
    connection.execute(
        """
        INSERT INTO document_chunk_runs (
            id, document_id, board_game_id, parse_run_id,
            document_sha256, document_metadata_sha256,
            source_pages_sha256, chunker_name, chunker_version,
            chunker_config_json, page_count, indexed_page_count,
            chunk_count, total_chunk_chars, created_at
        ) VALUES (
            'chunk-run-v7', 'doc-v7', ?, 'run-v7',
            ?, ?, ?, 'page-char-window', '1',
            ?, 1, 1, 1, 4, 'before'
        )
        """,
        (game_id, "a" * 64, "b" * 64, "c" * 64, config),
    )
    connection.execute(
        """
        INSERT INTO document_chunks (
            id, chunk_key, chunk_run_id,
            board_game_id, document_id, document_sha256,
            document_metadata_sha256, parse_run_id,
            page_id, page_number, page_text_sha256,
            chunk_index, start_char, end_char,
            text, text_sha256, char_count,
            language, document_type,
            source_kind, is_official, document_provenance_json,
            chunker_name, chunker_version, chunker_config_json,
            created_at
        ) VALUES (
            'chunk-v7', ?, 'chunk-run-v7',
            ?, 'doc-v7', ?,
            ?, 'run-v7',
            'page-v7', 1, ?,
            0, 0, 4,
            'text', ?, 4,
            'en', 'rulebook',
            'manual_upload', 0, '{}',
            'page-char-window', '1', ?,
            'before'
        )
        """,
        (
            "d" * 64,
            game_id,
            "a" * 64,
            "b" * 64,
            page_sha,
            page_sha,
            config,
        ),
    )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()

    with database.connect() as connection:
        chunk = connection.execute(
            "SELECT id, text FROM document_chunks WHERE id = 'chunk-v7'"
        ).fetchone()
        embedding_runs = connection.execute(
            "SELECT COUNT(*) AS count FROM document_embedding_runs"
        ).fetchone()["count"]
        embeddings = connection.execute(
            "SELECT COUNT(*) AS count FROM chunk_embeddings"
        ).fetchone()["count"]
        fk_check = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert database.schema_version() == 8
    assert dict(chunk) == {"id": "chunk-v7", "text": "text"}
    assert embedding_runs == 0
    assert embeddings == 0
    assert fk_check == []
