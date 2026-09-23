from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from boardgamecompanion.database import Database
from boardgamecompanion.documents import DocumentStore
from boardgamecompanion.rulebook_fetch import (
    RedirectHop,
    RulebookFetchFailure,
    RulebookFetchFailureCode,
    RulebookFetchResult,
)
from boardgamecompanion.rulebook_review import RulebookReviewQueue
from boardgamecompanion.rulebook_updates import (
    DEFAULT_LEASE_SECONDS,
    RulebookUpdateBusy,
    RulebookUpdateNotApproved,
    RulebookUpdateService,
)
from boardgamecompanion.rulebooks import RulebookCandidate

PDF_A = b"%PDF-1.4\nP6B version A\n%%EOF\n"
PDF_B = b"%PDF-1.4\nP6B version B\n%%EOF\n"
NOW = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)


def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "config" / "boardgamecompanion.sqlite3")
    db.initialize()
    now = NOW.isoformat()
    with db.transaction() as connection:
        connection.execute(
            """
            INSERT INTO board_games (
                bgg_id, title, source_metadata_json, created_at, updated_at
            ) VALUES (900001, 'P6B Test Game', '{}', ?, ?)
            """,
            (now, now),
        )
    return db


def official_candidate(**overrides) -> RulebookCandidate:
    values = {
        "provider": "publisher-test",
        "source_kind": "official_publisher",
        "url": "https://publisher.example/rules.pdf",
        "language": "it",
        "document_type": "rulebook",
        "official": True,
        "confidence": 100,
        "title": "Regolamento ufficiale",
        "version_label": "v1",
        "edition": "Retail IT",
        "bgg_id": 900001,
        "game_title": "P6B Test Game",
        "year": 2026,
        "publisher": "Publisher Test",
        "metadata": {"source": "test"},
    }
    values.update(overrides)
    return RulebookCandidate(**values)


def community_candidate(**overrides) -> RulebookCandidate:
    values = {
        "provider": "community-test",
        "source_kind": "community",
        "url": "https://community.example/rules.pdf",
        "language": "it",
        "document_type": "rulebook",
        "official": False,
        "confidence": 70,
        "bgg_id": 900001,
    }
    values.update(overrides)
    return RulebookCandidate(**values)


class SequenceFetcher:
    def __init__(self, manuals_dir: Path, outcomes: list[bytes | str]):
        self.manuals_dir = manuals_dir
        self.outcomes = list(outcomes)
        self.calls = 0

    def fetch(self, candidate: RulebookCandidate) -> RulebookFetchResult:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, str):
            failure = RulebookFetchFailure(
                code=RulebookFetchFailureCode(outcome),
                message=f"simulated {outcome}",
                url=candidate.url,
            )
            return RulebookFetchResult(
                candidate=candidate,
                requested_url=candidate.url,
                final_url=candidate.url,
                failure=failure,
            )

        self.manuals_dir.mkdir(parents=True, exist_ok=True)
        sha256 = hashlib.sha256(outcome).hexdigest()
        path = self.manuals_dir / f"{sha256}.pdf"
        path.write_bytes(outcome)
        return RulebookFetchResult(
            candidate=candidate,
            requested_url=candidate.url,
            final_url="https://cdn.publisher.example/final-rules.pdf",
            redirect_chain=(
                RedirectHop(
                    status_code=302,
                    from_url=candidate.url,
                    to_url="https://cdn.publisher.example/final-rules.pdf",
                ),
            ),
            status_code=200,
            content_type="application/pdf",
            byte_size=len(outcome),
            sha256=sha256,
            local_path=str(path),
            http_metadata={
                "etag": '"p6b-test"',
                "last-modified": "Wed, 23 Sep 2026 18:00:00 GMT",
            },
        )


def service(
    db: Database,
    manuals_dir: Path,
    fetcher: SequenceFetcher,
) -> RulebookUpdateService:
    return RulebookUpdateService(
        db,
        manuals_dir,
        fetcher_factory=lambda: fetcher,
        default_interval_seconds=24 * 60 * 60,
        retry_base_seconds=60 * 60,
        retry_max_seconds=8 * 60 * 60,
        lease_seconds=120,
        max_archive_bytes=1024 * 1024,
        fetch_max_bytes=1024 * 1024,
    )


def approved_review(db: Database, candidate: RulebookCandidate | None = None) -> dict:
    item, _ = RulebookReviewQueue(db).submit(
        bgg_id=900001,
        candidate=candidate or official_candidate(),
    )
    assert item["status"] == "approved"
    return item


def test_approved_candidate_becomes_idempotent_due_target(tmp_path: Path) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    fetcher = SequenceFetcher(tmp_path / "manuals", [PDF_A])
    updates = service(db, tmp_path / "manuals", fetcher)

    first, created = updates.ensure_target(review["id"], now=NOW)
    second, created_again = updates.ensure_target(review["id"], now=NOW)

    assert created is True
    assert created_again is False
    assert first["id"] == second["id"]
    assert first["enabled"] is True
    assert first["next_check_at"] == NOW.isoformat()
    assert first["last_outcome"] is None


def test_pending_candidate_cannot_be_scheduled(tmp_path: Path) -> None:
    db = database(tmp_path)
    review, _ = RulebookReviewQueue(db).submit(
        bgg_id=900001,
        candidate=community_candidate(),
    )
    fetcher = SequenceFetcher(tmp_path / "manuals", [PDF_A])
    updates = service(db, tmp_path / "manuals", fetcher)

    with pytest.raises(RulebookUpdateNotApproved):
        updates.ensure_target(review["id"], now=NOW)


def test_manual_approval_is_discovered_by_target_sync(tmp_path: Path) -> None:
    db = database(tmp_path)
    review, _ = RulebookReviewQueue(db).submit(
        bgg_id=900001,
        candidate=community_candidate(),
    )
    RulebookReviewQueue(db).decide(review["id"], decision="approved")
    fetcher = SequenceFetcher(tmp_path / "manuals", [PDF_A])
    updates = service(db, tmp_path / "manuals", fetcher)

    result = updates.synchronize_approved_targets(now=NOW)

    assert result == {"discovered": 1, "created": 1, "corrupt": 0}
    assert updates.get_target(review["id"]) is not None


def test_first_execution_archives_pdf_and_full_provenance(tmp_path: Path) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A])
    updates = service(db, manuals, fetcher)

    result = updates.run_review_now(review["id"], owner="manual-test", now=NOW)

    assert result["outcome"] == "created"
    assert result["document"]["sha256"] == hashlib.sha256(PDF_A).hexdigest()
    documents = DocumentStore(db, manuals).list_for_game(900001)
    assert len(documents) == 1
    document = documents[0]
    assert document["source"]["kind"] == "official_publisher"
    assert document["source"]["provider"] == "publisher-test"
    assert document["source"]["official"] is True
    assert document["provenance"]["ingest"] == "scheduled_rulebook_fetch"
    assert document["provenance"]["review_item_id"] == review["id"]
    assert document["provenance"]["decision_source"] == "policy"
    assert document["provenance"]["http_metadata"]["etag"] == '"p6b-test"'
    assert document["provenance"]["redirect_chain"][0]["status_code"] == 302

    target = updates.get_target(review["id"])
    assert target["last_outcome"] == "created"
    assert target["last_document_id"] == document["id"]
    assert target["consecutive_failures"] == 0
    assert target["leased"] is False

    runs = updates.list_runs(review["id"])
    assert runs["total"] == 1
    assert runs["items"][0]["outcome"] == "created"
    assert runs["items"][0]["document_id"] == document["id"]


def test_unchanged_hash_does_not_create_duplicate_document(tmp_path: Path) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A, PDF_A])
    updates = service(db, manuals, fetcher)

    first = updates.run_review_now(review["id"], owner="first", now=NOW)
    second = updates.run_review_now(
        review["id"],
        owner="second",
        now=NOW + timedelta(minutes=1),
    )

    assert first["outcome"] == "created"
    assert second["outcome"] == "unchanged"
    assert first["document"]["id"] == second["document"]["id"]
    assert len(DocumentStore(db, manuals).list_for_game(900001)) == 1
    assert updates.list_runs(review["id"])["total"] == 2
    assert updates.get_target(review["id"])["last_outcome"] == "unchanged"


def test_changed_hash_creates_new_document_version(tmp_path: Path) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A, PDF_B])
    updates = service(db, manuals, fetcher)

    first = updates.run_review_now(review["id"], owner="first", now=NOW)
    second = updates.run_review_now(
        review["id"],
        owner="second",
        now=NOW + timedelta(minutes=1),
    )

    assert first["outcome"] == second["outcome"] == "created"
    assert first["document"]["id"] != second["document"]["id"]
    documents = DocumentStore(db, manuals).list_for_game(900001)
    assert {item["sha256"] for item in documents} == {
        hashlib.sha256(PDF_A).hexdigest(),
        hashlib.sha256(PDF_B).hexdigest(),
    }


def test_fetch_failure_is_audited_and_uses_exponential_backoff(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(
        manuals,
        [
            RulebookFetchFailureCode.NETWORK_TIMEOUT.value,
            RulebookFetchFailureCode.NETWORK_TIMEOUT.value,
        ],
    )
    updates = service(db, manuals, fetcher)

    first = updates.run_review_now(review["id"], owner="first", now=NOW)
    target_after_first = updates.get_target(review["id"])
    second = updates.run_review_now(
        review["id"],
        owner="second",
        now=NOW + timedelta(minutes=1),
    )
    target_after_second = updates.get_target(review["id"])

    assert first["outcome"] == second["outcome"] == "failed"
    assert first["failure_code"] == "network_timeout"
    assert target_after_first["consecutive_failures"] == 1
    assert target_after_second["consecutive_failures"] == 2
    first_next = datetime.fromisoformat(first["next_check_at"])
    second_next = datetime.fromisoformat(second["next_check_at"])
    assert first_next > NOW
    assert second_next > first_next
    runs = updates.list_runs(review["id"])
    assert [item["outcome"] for item in runs["items"]] == ["failed", "failed"]


def test_success_after_failure_resets_backoff_state(tmp_path: Path) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(
        manuals,
        [RulebookFetchFailureCode.NETWORK_ERROR.value, PDF_A],
    )
    updates = service(db, manuals, fetcher)

    updates.run_review_now(review["id"], owner="fail", now=NOW)
    result = updates.run_review_now(
        review["id"],
        owner="success",
        now=NOW + timedelta(minutes=1),
    )

    target = updates.get_target(review["id"])
    assert result["outcome"] == "created"
    assert target["consecutive_failures"] == 0
    assert target["last_failure_code"] is None
    assert target["last_failure_message"] is None
    assert target["last_success_at"] is not None


def test_due_claim_lease_prevents_duplicate_workers_and_expires(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    fetcher = SequenceFetcher(tmp_path / "manuals", [PDF_A])
    updates = service(db, tmp_path / "manuals", fetcher)
    updates.ensure_target(review["id"], now=NOW)

    first = updates.claim_due(owner="worker-a", now=NOW)
    second = updates.claim_due(owner="worker-b", now=NOW)
    reclaimed = updates.claim_due(
        owner="worker-b",
        now=NOW + timedelta(seconds=121),
    )

    assert len(first) == 1
    assert second == []
    assert len(reclaimed) == 1
    assert reclaimed[0]["id"] == first[0]["id"]


def test_manual_run_refuses_active_lease(tmp_path: Path) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    fetcher = SequenceFetcher(tmp_path / "manuals", [PDF_A])
    updates = service(db, tmp_path / "manuals", fetcher)
    updates.ensure_target(review["id"], now=NOW)
    updates.claim_due(owner="worker-a", now=NOW)

    with pytest.raises(RulebookUpdateBusy):
        updates.run_review_now(
            review["id"],
            owner="manual",
            now=NOW + timedelta(seconds=1),
        )


def test_disabled_target_is_skipped_by_scheduler_but_can_run_manually(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A])
    updates = service(db, manuals, fetcher)
    updates.ensure_target(review["id"], now=NOW)
    configured = updates.configure_target(
        review["id"],
        enabled=False,
        interval_seconds=2 * 60 * 60,
        now=NOW,
    )

    assert configured["enabled"] is False
    assert configured["interval_seconds"] == 7200
    assert updates.claim_due(owner="worker", now=NOW) == []
    manual = updates.run_review_now(review["id"], owner="manual", now=NOW)
    assert manual["outcome"] == "created"


def test_run_due_syncs_and_executes_approved_candidate(tmp_path: Path) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A])
    updates = service(db, manuals, fetcher)

    batch = updates.run_due(limit=5, owner="worker", now=NOW)

    assert batch["synchronized"]["created"] == 1
    assert batch["claimed"] == 1
    assert batch["results"][0]["review_item_id"] == review["id"]
    assert batch["results"][0]["outcome"] == "created"


def test_interval_changed_during_fetch_controls_next_success_schedule(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A])
    updates = service(db, manuals, fetcher)
    updates.ensure_target(review["id"], now=NOW)

    original_fetch = fetcher.fetch

    def fetch_after_reconfigure(candidate: RulebookCandidate) -> RulebookFetchResult:
        updates.configure_target(
            review["id"],
            interval_seconds=2 * 60 * 60,
            now=NOW + timedelta(seconds=30),
        )
        return original_fetch(candidate)

    fetcher.fetch = fetch_after_reconfigure  # type: ignore[method-assign]

    result = updates.run_review_now(review["id"], owner="manual", now=NOW)
    target = updates.get_target(review["id"])

    checked = datetime.fromisoformat(target["last_checked_at"])
    next_check = datetime.fromisoformat(result["next_check_at"])
    assert target["interval_seconds"] == 7200
    assert next_check - checked == timedelta(seconds=7200)


def test_run_due_claims_each_target_immediately_before_execution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    first = approved_review(
        db,
        official_candidate(url="https://publisher.example/rules-a.pdf"),
    )
    second = approved_review(
        db,
        official_candidate(
            url="https://publisher.example/rules-b.pdf",
            version_label="v2",
        ),
    )
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A, PDF_B])
    updates = service(db, manuals, fetcher)
    limits: list[int] = []
    original_claim_due = updates.claim_due

    def recording_claim_due(**kwargs):
        limits.append(kwargs["limit"])
        return original_claim_due(**kwargs)

    monkeypatch.setattr(updates, "claim_due", recording_claim_due)

    result = updates.run_due(limit=2, owner="worker", now=NOW)

    assert result["claimed"] == 2
    assert {item["review_item_id"] for item in result["results"]} == {
        first["id"],
        second["id"],
    }
    assert limits == [1, 1]


def test_archive_rejects_fetch_artifact_tampering_before_dedup(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A, PDF_A])
    updates = service(db, manuals, fetcher)
    first = updates.run_review_now(review["id"], owner="first", now=NOW)
    assert first["outcome"] == "created"

    original_fetch = fetcher.fetch

    def tampered_fetch(candidate: RulebookCandidate) -> RulebookFetchResult:
        result = original_fetch(candidate)
        assert result.local_path is not None
        path = Path(result.local_path)
        payload = path.read_bytes()
        path.write_bytes(b"X" + payload[1:])
        return result

    fetcher.fetch = tampered_fetch  # type: ignore[method-assign]
    second = updates.run_review_now(
        review["id"],
        owner="second",
        now=NOW + timedelta(minutes=1),
    )

    assert second["outcome"] == "failed"
    assert second["failure_code"] == "archive_error"
    assert len(DocumentStore(db, manuals).list_for_game(900001)) == 1


def test_unrelated_document_integrity_failure_is_not_deduplicated(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A])
    updates = service(db, manuals, fetcher)

    with db.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER force_document_abort
            BEFORE INSERT ON game_documents
            BEGIN
                SELECT RAISE(ABORT, 'forced document integrity failure');
            END
            """
        )

    result = updates.run_review_now(review["id"], owner="manual", now=NOW)

    assert result["outcome"] == "failed"
    assert result["failure_code"] == "archive_error"
    assert "forced document integrity failure" in result["failure_message"]
    assert DocumentStore(db, manuals).list_for_game(900001) == []
    runs = updates.list_runs(review["id"])
    assert runs["items"][0]["outcome"] == "failed"


def test_target_database_invariants_reject_impossible_success_state(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    fetcher = SequenceFetcher(tmp_path / "manuals", [PDF_A])
    updates = service(db, tmp_path / "manuals", fetcher)
    target, _ = updates.ensure_target(review["id"], now=NOW)

    with db.connect() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            UPDATE rulebook_update_targets
            SET last_outcome = 'created',
                last_checked_at = ?,
                last_success_at = ?,
                consecutive_failures = 0
            WHERE id = ?
            """,
            (NOW.isoformat(), NOW.isoformat(), target["id"]),
        )


def test_audited_document_cannot_be_deleted_while_update_history_references_it(
    tmp_path: Path,
) -> None:
    db = database(tmp_path)
    review = approved_review(db)
    manuals = tmp_path / "manuals"
    fetcher = SequenceFetcher(manuals, [PDF_A])
    updates = service(db, manuals, fetcher)

    result = updates.run_review_now(review["id"], owner="manual", now=NOW)
    document_id = result["document"]["id"]

    with db.connect() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "DELETE FROM game_documents WHERE id = ?",
            (document_id,),
        )

    assert DocumentStore(db, manuals).get(document_id) is not None
    assert updates.list_runs(review["id"])["items"][0]["document_id"] == document_id


def test_default_lease_constant_exceeds_small_test_fetch_window() -> None:
    assert DEFAULT_LEASE_SECONDS >= 5 * 60
