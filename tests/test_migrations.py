from __future__ import annotations

import sqlite3
from pathlib import Path

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

    assert first_version == LATEST_SCHEMA_VERSION == 6
    assert second_version == 6

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
    assert [row["version"] for row in migrations] == [1, 2, 3, 4, 5, 6]
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

    assert database.schema_version() == 6
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

    assert database.schema_version() == 6
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
