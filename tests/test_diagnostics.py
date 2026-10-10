from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from boardgamecompanion.database import Database
from boardgamecompanion.routers.diagnostics import _rulebook_discovery_counts
from boardgamecompanion.rulebook_discovery import RulebookDiscoveryService


def test_rulebook_diagnostics_separates_resolved_from_unresolved(
    tmp_path: Path,
) -> None:
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    now = datetime.now(UTC).isoformat()
    with db.transaction() as connection:
        games = (
            (100001, "Unresolved Game"),
            (100002, "Archived Game"),
            (312509, "Arena: The Contest – Dragon Collection"),
        )
        for bgg_id, title in games:
            connection.execute(
                """INSERT INTO board_games
                   (bgg_id,title,original_title,item_type,source_metadata_json,
                    created_at,updated_at)
                   VALUES (?,?,?,'boardgame','{}',?,?)""",
                (bgg_id, title, title, now, now),
            )

    service = RulebookDiscoveryService(db, ())
    assert service.synchronize_catalog() == 3
    with db.transaction() as connection:
        connection.execute(
            "UPDATE rulebook_discovery_games SET status='partial'"
        )
        archived_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id=100002"
        ).fetchone()["id"]
        connection.execute(
            """INSERT INTO game_documents
               (id,board_game_id,document_type,language,title,original_filename,
                storage_path,sha256,size_bytes,source_kind,is_official,
                created_at,updated_at)
               VALUES ('archived-doc',?,'rulebook','en','Rules','rules.pdf',
                       '/tmp/archived-rules.pdf',?,1,'manual_upload',1,?,?)""",
            (archived_id, "b" * 64, now, now),
        )

    with db.connect() as connection:
        discovery, resolution = _rulebook_discovery_counts(connection)

    assert discovery == {"resolved": 2, "partial": 1}
    assert resolution == {
        "archived_pdf": 1,
        "classified_without_pdf": 1,
        "resolved_total": 2,
        "unresolved_total": 1,
    }
