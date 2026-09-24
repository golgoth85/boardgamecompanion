from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

import boardgamecompanion.main as main_module
from boardgamecompanion.database import Database
from boardgamecompanion.main import app
from boardgamecompanion.rulebook_fetch import RulebookFetchResult
from boardgamecompanion.rulebook_review import RulebookReviewQueue
from boardgamecompanion.rulebook_updates import RulebookUpdateService
from boardgamecompanion.rulebooks import RulebookCandidate
from boardgamecompanion.settings import settings

NOW = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
PDF = b"%PDF-1.4\nP6B API test\n%%EOF\n"


def configure(monkeypatch, tmp_path: Path) -> Database:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    monkeypatch.setattr(settings, "max_document_bytes", 1024 * 1024)
    monkeypatch.setattr(settings, "rulebook_fetch_max_bytes", 1024 * 1024)
    monkeypatch.setattr(settings, "rulebook_update_worker_enabled", False)

    database = Database(settings.database_path)
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO board_games (
                bgg_id, title, source_metadata_json, created_at, updated_at
            ) VALUES (900001, 'API Test Game', '{}', ?, ?)
            """,
            (NOW.isoformat(), NOW.isoformat()),
        )
    return database


def official_candidate() -> RulebookCandidate:
    return RulebookCandidate(
        provider="publisher-api",
        source_kind="official_publisher",
        url="https://publisher.example/api-rules.pdf",
        language="it",
        document_type="rulebook",
        official=True,
        confidence=100,
        title="Regolamento API",
        bgg_id=900001,
    )


def community_candidate() -> RulebookCandidate:
    return RulebookCandidate(
        provider="community-api",
        source_kind="community",
        url="https://community.example/api-rules.pdf",
        language="it",
        document_type="rulebook",
        official=False,
        confidence=70,
        bgg_id=900001,
    )


class ApiFetcher:
    def __init__(self, manuals_dir: Path):
        self.manuals_dir = manuals_dir
        self.calls = 0

    def fetch(self, candidate: RulebookCandidate) -> RulebookFetchResult:
        self.calls += 1
        self.manuals_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(PDF).hexdigest()
        path = self.manuals_dir / f"{digest}.pdf"
        path.write_bytes(PDF)
        return RulebookFetchResult(
            candidate=candidate,
            requested_url=candidate.url,
            final_url=candidate.url,
            status_code=200,
            content_type="application/pdf",
            byte_size=len(PDF),
            sha256=digest,
            local_path=str(path),
            http_metadata={"etag": '"api-test"'},
        )


def update_service(database: Database, fetcher: ApiFetcher) -> RulebookUpdateService:
    return RulebookUpdateService(
        database,
        settings.manuals_dir,
        fetcher_factory=lambda: fetcher,
        default_interval_seconds=30 * 24 * 60 * 60,
        retry_base_seconds=3600,
        retry_max_seconds=86400,
        lease_seconds=120,
        max_archive_bytes=1024 * 1024,
        fetch_max_bytes=1024 * 1024,
    )


def test_manual_approval_creates_update_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = configure(monkeypatch, tmp_path)
    review, _ = RulebookReviewQueue(database).submit(
        bgg_id=900001,
        candidate=community_candidate(),
    )
    fetcher = ApiFetcher(settings.manuals_dir)
    service = update_service(database, fetcher)
    monkeypatch.setattr(main_module, "get_rulebook_update_service", lambda: service)

    with TestClient(app) as client:
        response = client.post(
            f"/api/rulebook-reviews/{review['id']}/decision",
            json={"decision": "approved", "note": "reviewed"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    target = service.get_target(review["id"])
    assert target is not None
    assert target["enabled"] is True


def test_update_api_list_configure_run_and_audit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = configure(monkeypatch, tmp_path)
    review, _ = RulebookReviewQueue(database).submit(
        bgg_id=900001,
        candidate=official_candidate(),
    )
    fetcher = ApiFetcher(settings.manuals_dir)
    service = update_service(database, fetcher)
    monkeypatch.setattr(main_module, "get_rulebook_update_service", lambda: service)

    with TestClient(app) as client:
        listing = client.get("/api/rulebook-updates?limit=50&offset=0")
        assert listing.status_code == 200
        body = listing.json()
        assert body["total"] == 1
        assert body["items"][0]["review_item_id"] == review["id"]
        assert body["items"][0]["provider"] == "publisher-api"
        assert body["worker"]["enabled"] is False

        configured = client.patch(
            f"/api/rulebook-updates/{review['id']}",
            json={"enabled": False, "interval_seconds": 7 * 24 * 60 * 60},
        )
        assert configured.status_code == 200
        assert configured.json()["enabled"] is False
        assert configured.json()["interval_seconds"] == 604800

        detail = client.get(f"/api/rulebook-updates/{review['id']}")
        assert detail.status_code == 200
        assert detail.json()["id"] == configured.json()["id"]

        run = client.post(f"/api/rulebook-updates/{review['id']}/run")
        assert run.status_code == 200
        assert run.json()["outcome"] == "created"
        assert run.json()["document"]["source"]["provider"] == "publisher-api"

        runs = client.get(f"/api/rulebook-updates/{review['id']}/runs")
        assert runs.status_code == 200
        assert runs.json()["total"] == 1
        assert runs.json()["items"][0]["outcome"] == "created"

    assert fetcher.calls == 1


def test_update_api_rejects_pending_review(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = configure(monkeypatch, tmp_path)
    review, _ = RulebookReviewQueue(database).submit(
        bgg_id=900001,
        candidate=community_candidate(),
    )
    fetcher = ApiFetcher(settings.manuals_dir)
    service = update_service(database, fetcher)
    monkeypatch.setattr(main_module, "get_rulebook_update_service", lambda: service)

    with TestClient(app) as client:
        configured = client.patch(
            f"/api/rulebook-updates/{review['id']}",
            json={"enabled": True},
        )
        run = client.post(f"/api/rulebook-updates/{review['id']}/run")

    assert configured.status_code == 409
    assert run.status_code == 409


def test_update_api_validates_schedule_bounds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = configure(monkeypatch, tmp_path)
    review, _ = RulebookReviewQueue(database).submit(
        bgg_id=900001,
        candidate=official_candidate(),
    )
    fetcher = ApiFetcher(settings.manuals_dir)
    service = update_service(database, fetcher)
    service.ensure_target(review["id"], now=NOW)
    monkeypatch.setattr(main_module, "get_rulebook_update_service", lambda: service)

    with TestClient(app) as client:
        too_short = client.patch(
            f"/api/rulebook-updates/{review['id']}",
            json={"interval_seconds": 3599},
        )
        too_long = client.patch(
            f"/api/rulebook-updates/{review['id']}",
            json={"interval_seconds": 365 * 24 * 60 * 60 + 1},
        )

    assert too_short.status_code == 422
    assert too_long.status_code == 422


def test_update_api_quarantines_target_whose_review_was_corrupted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = configure(monkeypatch, tmp_path)
    review, _ = RulebookReviewQueue(database).submit(
        bgg_id=900001,
        candidate=official_candidate(),
    )
    fetcher = ApiFetcher(settings.manuals_dir)
    service = update_service(database, fetcher)
    service.ensure_target(review["id"], now=NOW)
    monkeypatch.setattr(main_module, "get_rulebook_update_service", lambda: service)

    with database.connect() as connection:
        connection.execute(
            """
            UPDATE rulebook_review_items
            SET candidate_json = '{', url = 'javascript:alert(1)'
            WHERE id = ?
            """,
            (review["id"],),
        )

    with TestClient(app) as client:
        listing = client.get("/api/rulebook-updates?limit=50&offset=0")
        detail = client.get(f"/api/rulebook-updates/{review['id']}")
        run = client.post(f"/api/rulebook-updates/{review['id']}/run")

    assert listing.status_code == 200
    payload = listing.json()
    assert payload["total"] == 1
    assert payload["items"] == []
    assert payload["corrupt_count"] == 1
    assert payload["corrupt_items"] == [
        {
            "review_item_id": review["id"],
            "error": "corrupt persisted review record",
        }
    ]
    assert detail.status_code == 500
    assert run.status_code == 500
    assert fetcher.calls == 0

    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT candidate_json, url, status
            FROM rulebook_review_items
            WHERE id = ?
            """,
            (review["id"],),
        ).fetchone()
    assert row["candidate_json"] == "{"
    assert row["url"] == "javascript:alert(1)"
    assert row["status"] == "approved"


def test_run_history_api_remains_available_if_review_later_corrupts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = configure(monkeypatch, tmp_path)
    review, _ = RulebookReviewQueue(database).submit(
        bgg_id=900001,
        candidate=official_candidate(),
    )
    fetcher = ApiFetcher(settings.manuals_dir)
    service = update_service(database, fetcher)
    monkeypatch.setattr(main_module, "get_rulebook_update_service", lambda: service)
    service.run_review_now(review["id"], owner="manual", now=NOW)

    with database.connect() as connection:
        connection.execute(
            """
            UPDATE rulebook_review_items
            SET candidate_json = '{'
            WHERE id = ?
            """,
            (review["id"],),
        )

    with TestClient(app) as client:
        response = client.get(f"/api/rulebook-updates/{review['id']}/runs")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["outcome"] == "created"


def test_run_history_api_quarantines_corrupt_audit_json(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = configure(monkeypatch, tmp_path)
    review, _ = RulebookReviewQueue(database).submit(
        bgg_id=900001,
        candidate=official_candidate(),
    )
    fetcher = ApiFetcher(settings.manuals_dir)
    service = update_service(database, fetcher)
    monkeypatch.setattr(main_module, "get_rulebook_update_service", lambda: service)
    service.run_review_now(review["id"], owner="manual", now=NOW)
    run_id = service.list_runs(review["id"])["items"][0]["id"]

    with database.connect() as connection:
        connection.execute(
            """
            UPDATE rulebook_update_runs
            SET http_metadata_json = ?
            WHERE id = ?
            """,
            ('{"value":"' + ("x" * 70000) + '"}', run_id),
        )

    with TestClient(app) as client:
        response = client.get(f"/api/rulebook-updates/{review['id']}/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"] == []
    assert payload["corrupt_count"] == 1
    assert payload["corrupt_items"][0]["id"] == run_id
