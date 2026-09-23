from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.database import Database
from boardgamecompanion.main import app
from boardgamecompanion.rulebook_review import (
    MAX_CANDIDATE_SNAPSHOT_BYTES,
    MAX_POLICY_REASONS_BYTES,
    RulebookReviewCandidateMismatch,
    RulebookReviewConflict,
    RulebookReviewError,
    RulebookReviewNotFound,
    RulebookReviewQueue,
    candidate_from_snapshot,
)
from boardgamecompanion.rulebooks import RulebookCandidate
from boardgamecompanion.settings import settings

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def configure_paths(tmp_path: Path) -> None:
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"


def import_fixture(client: TestClient) -> None:
    with FIXTURE.open("rb") as handle:
        response = client.post(
            "/api/imports/bgg-csv",
            files={"file": ("collection.csv", handle, "text/csv")},
        )
    assert response.status_code == 200
def queue() -> RulebookReviewQueue:
    database = Database(settings.database_path)
    database.initialize()
    return RulebookReviewQueue(database)


def submit_candidate(payload: dict, *, bgg_id: int = 900001):
    return queue().submit(
        bgg_id=bgg_id,
        candidate=RulebookCandidate(**payload),
    )


def official_payload(**overrides):
    payload = {
        "provider": "publisher-example",
        "source_kind": "official_publisher",
        "url": "https://publisher.example/rules.pdf",
        "language": "it",
        "document_type": "rulebook",
        "official": True,
        "confidence": 100,
        "title": "Regolamento italiano",
        "version_label": "v2",
        "edition": "Retail IT",
        "bgg_id": 900001,
        "game_title": "Example Game",
        "year": 2024,
        "publisher": "Example Publisher",
        "metadata": {"edition_code": "IT-2", "tags": ["official", "it"]},
    }
    payload.update(overrides)
    return payload
def community_payload(**overrides):
    payload = official_payload(
        provider="community-example",
        source_kind="community",
        url="https://community.example/rules.pdf",
        official=False,
        confidence=70,
    )
    payload.update(overrides)
    return payload


def test_high_confidence_official_exact_candidate_is_policy_approved(
    tmp_path: Path,
) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        item, created = submit_candidate(official_payload())

        assert created is True
        assert item["policy_action"] == "unattended"
        assert item["status"] == "approved"
        assert item["decision_source"] == "policy"
        assert item["decided_at"]
        assert item["candidate"]["bgg_id"] == 900001
        assert item["policy_reasons"] == [
            "source:official",
            "confidence:100",
            "bgg_id:exact",
            "language:it",
        ]

        pending = client.get("/api/rulebook-reviews?status=pending").json()
        approved = client.get("/api/rulebook-reviews?status=approved").json()
        assert pending["total"] == 0
        assert approved["total"] == 1


def test_official_mirror_at_threshold_is_unattended(tmp_path: Path) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        item, created = submit_candidate(
            official_payload(
                provider="official-mirror",
                source_kind="official_mirror",
                url="https://mirror.example/rules.pdf",
                language="en-GB",
                confidence=95,
            )
        )

    assert created is True
    assert item["policy_action"] == "unattended"
    assert item["status"] == "approved"
    assert item["decision_source"] == "policy"


def test_lower_trust_candidate_enters_pending_and_decision_is_atomic(
    tmp_path: Path,
) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        item, created = submit_candidate(community_payload())
        assert created is True
        assert item["policy_action"] == "review"
        assert item["status"] == "pending"
        assert item["decision_source"] is None
        assert "review:unofficial-source" in item["policy_reasons"]
        review_id = item["id"]

        approved = client.post(
            f"/api/rulebook-reviews/{review_id}/decision",
            json={"decision": "approved", "note": "Verificato manualmente"},
        )
        assert approved.status_code == 200
        decided = approved.json()
        assert decided["status"] == "approved"
        assert decided["decision_source"] == "user"
        assert decided["decision_note"] == "Verificato manualmente"
        assert decided["decided_at"]

        repeated = client.post(
            f"/api/rulebook-reviews/{review_id}/decision",
            json={"decision": "approved", "note": "ignored repeat"},
        )
        assert repeated.status_code == 200
        assert repeated.json()["decision_note"] == "Verificato manualmente"

        conflicting = client.post(
            f"/api/rulebook-reviews/{review_id}/decision",
            json={"decision": "rejected"},
        )
        assert conflicting.status_code == 409
def test_duplicate_candidate_submission_is_idempotent(tmp_path: Path) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        first, first_created = submit_candidate(community_payload())
        second, second_created = submit_candidate(community_payload())

        assert first_created is True
        assert second_created is False
        assert first["id"] == second["id"]
        listing = client.get("/api/rulebook-reviews").json()
        assert listing["total"] == 1


def test_policy_requires_exact_bgg_identity_and_it_or_en_language(
    tmp_path: Path,
) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        no_identity, _ = submit_candidate(
            official_payload(
                url="https://publisher.example/no-id.pdf",
                bgg_id=None,
            )
        )
        unsupported_language, _ = submit_candidate(
            official_payload(
                url="https://publisher.example/de.pdf",
                language="de",
            )
        )

        assert no_identity["policy_action"] == "review"
        assert "review:bgg-id-not-exact" in no_identity["policy_reasons"]
        assert unsupported_language["policy_action"] == "review"
        assert "review:language:de" in unsupported_language["policy_reasons"]

        listing = client.get("/api/rulebook-reviews?status=pending").json()
        assert listing["total"] == 2
def test_official_source_below_threshold_requires_review(tmp_path: Path) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        item, _ = submit_candidate(official_payload(confidence=94))

        assert item["policy_action"] == "review"
        assert item["status"] == "pending"
        assert "review:confidence:94" in item["policy_reasons"]


def test_conflicting_candidate_bgg_id_is_rejected_before_queueing(
    tmp_path: Path,
) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        with pytest.raises(RulebookReviewCandidateMismatch):
            submit_candidate(official_payload(bgg_id=900002))

        assert client.get("/api/rulebook-reviews").json()["total"] == 0


def test_candidate_snapshot_round_trip_preserves_normalized_candidate(
    tmp_path: Path,
) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        item, _ = submit_candidate(
            community_payload(
                metadata={
                    "nested": {"value": 1},
                    "sequence": ["a", {"b": True}],
                }
            )
        )

        candidate = candidate_from_snapshot(item["candidate"])
        assert candidate.provider == "community-example"
        assert candidate.source_kind.value == "community"
        assert candidate.url == "https://community.example/rules.pdf"
        assert candidate.bgg_id == 900001
        assert candidate.metadata["nested"]["value"] == 1
        assert candidate.metadata["sequence"][1]["b"] is True
def test_review_listing_filters_and_missing_items(tmp_path: Path) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        submit_candidate(community_payload())
        submit_candidate(official_payload())

        assert client.get(
            "/api/rulebook-reviews?status=pending&bgg_id=900001"
        ).json()["total"] == 1
        assert client.get(
            "/api/rulebook-reviews?status=approved&bgg_id=900001"
        ).json()["total"] == 1
        assert client.get(
            "/api/rulebook-reviews?status=unknown"
        ).status_code == 400
        assert client.get(
            "/api/rulebook-reviews/missing"
        ).status_code == 404
        assert client.post(
            "/api/rulebook-reviews/missing/decision",
            json={"decision": "approved"},
        ).status_code == 404


def test_queue_submission_requires_existing_board_game(tmp_path: Path) -> None:
    configure_paths(tmp_path)
    Database(settings.database_path).initialize()

    with pytest.raises(RulebookReviewNotFound, match="not found"):
        submit_candidate(official_payload())
def test_candidate_snapshot_size_is_bounded(tmp_path: Path) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        with pytest.raises(RulebookReviewError, match="snapshot exceeds"):
            submit_candidate(
                community_payload(
                    metadata={"oversized": "x" * (300 * 1024)},
                )
            )

        assert client.get("/api/rulebook-reviews").json()["total"] == 0


def test_raw_http_cannot_self_assert_candidate_trust(tmp_path: Path) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        import_fixture(client)
        response = client.post(
            "/api/games/900001/rulebook-reviews",
            json=official_payload(),
        )

    assert response.status_code == 404


def test_concurrent_duplicate_submissions_are_idempotent(tmp_path: Path) -> None:
    configure_paths(tmp_path)
    with TestClient(app) as client:
        import_fixture(client)

    database = Database(settings.database_path)
    candidate = RulebookCandidate(**community_payload())
    for index in range(20):
        round_candidate = RulebookCandidate(
            **{
                **community_payload(),
                "url": f"https://community.example/rules-{index}.pdf",
            }
        )
        barrier = Barrier(2)

        def worker(
            barrier: Barrier = barrier,
            round_candidate: RulebookCandidate = round_candidate,
        ):
            barrier.wait()
            return RulebookReviewQueue(database).submit(
                bgg_id=900001,
                candidate=round_candidate,
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                future.result()
                for future in [pool.submit(worker), pool.submit(worker)]
            ]

        created = sorted(result[1] for result in results)
        ids = {result[0]["id"] for result in results}
        assert created == [False, True]
        assert len(ids) == 1

    assert candidate.provider == "community-example"


def test_unrelated_integrity_error_is_not_treated_as_duplicate(
    tmp_path: Path,
) -> None:
    configure_paths(tmp_path)
    with TestClient(app) as client:
        import_fixture(client)
        submit_candidate(community_payload())

    database = Database(settings.database_path)
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER force_review_integrity
            BEFORE INSERT ON rulebook_review_items
            WHEN NEW.provider = 'community-example'
            BEGIN
                SELECT RAISE(ABORT, 'forced unrelated integrity failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced unrelated"):
        submit_candidate(community_payload())


def test_database_rejects_impossible_review_states(tmp_path: Path) -> None:
    configure_paths(tmp_path)
    with TestClient(app) as client:
        import_fixture(client)
        item, _ = submit_candidate(community_payload())

    invalid_updates = [
        (
            "status='pending', policy_action='review', "
            "decision_source='user', decided_at='x'"
        ),
        (
            "status='approved', policy_action='review', "
            "decision_source='user', decided_at=NULL"
        ),
        (
            "status='rejected', policy_action='review', "
            "decision_source='policy', decided_at=NULL"
        ),
        (
            "status='pending', policy_action='review', "
            "decision_source=NULL, decided_at='x'"
        ),
        (
            "status='pending', policy_action='review', "
            "decision_source=NULL, decision_note='spurious', decided_at=NULL"
        ),
    ]
    database = Database(settings.database_path)
    for update in invalid_updates:
        with (
            database.connect() as connection,
            pytest.raises(sqlite3.IntegrityError),
        ):
            connection.execute(
                f"UPDATE rulebook_review_items SET {update} WHERE id = ?",
                (item["id"],),
            )


def test_corrupt_review_rows_are_quarantined_and_not_decidable(
    tmp_path: Path,
) -> None:
    configure_paths(tmp_path)
    with TestClient(app) as client:
        import_fixture(client)
        item, _ = submit_candidate(community_payload())

        database = Database(settings.database_path)
        with database.connect() as connection:
            connection.execute(
                "UPDATE rulebook_review_items SET candidate_json = '{' WHERE id = ?",
                (item["id"],),
            )

        listing = client.get(
            "/api/rulebook-reviews?status=pending&limit=50&offset=0"
        )
        assert listing.status_code == 200
        assert listing.json()["items"] == []
        assert listing.json()["corrupt_count"] == 1
        assert listing.json()["corrupt_items"] == [
            {
                "id": item["id"],
                "error": "corrupt persisted review record",
            }
        ]
        assert client.get(
            f"/api/rulebook-reviews/{item['id']}"
        ).status_code == 500
        assert client.post(
            f"/api/rulebook-reviews/{item['id']}/decision",
            json={"decision": "approved"},
        ).status_code == 500
        with database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM rulebook_review_items WHERE id = ?",
                (item["id"],),
            ).fetchone()
        assert row["status"] == "pending"


@pytest.mark.parametrize(
    ("column", "payload"),
    [
        (
            "candidate_json",
            "[" * 1200 + "0" + "]" * 1200,
        ),
        (
            "policy_reasons_json",
            "[" * 1200 + "0" + "]" * 1200,
        ),
        (
            "candidate_json",
            '{"oversized":"' + "x" * MAX_CANDIDATE_SNAPSHOT_BYTES + '"}',
        ),
        (
            "policy_reasons_json",
            '["' + "x" * MAX_POLICY_REASONS_BYTES + '"]',
        ),
    ],
)
def test_pathological_persisted_json_is_quarantined_without_mutation(
    tmp_path: Path,
    column: str,
    payload: str,
) -> None:
    configure_paths(tmp_path)
    with TestClient(app) as client:
        import_fixture(client)
        item, _ = submit_candidate(
            community_payload(
                url=f"https://community.example/corrupt-{column}.pdf",
            )
        )
        database = Database(settings.database_path)
        with database.connect() as connection:
            connection.execute(
                f"UPDATE rulebook_review_items SET {column} = ? WHERE id = ?",
                (payload, item["id"]),
            )
            before = connection.execute(
                f"SELECT {column}, status FROM rulebook_review_items WHERE id = ?",
                (item["id"],),
            ).fetchone()

        listing = client.get(
            "/api/rulebook-reviews?status=pending&limit=50&offset=0"
        )
        assert listing.status_code == 200
        assert listing.json()["items"] == []
        assert listing.json()["corrupt_count"] == 1
        assert listing.json()["corrupt_items"] == [
            {
                "id": item["id"],
                "error": "corrupt persisted review record",
            }
        ]
        assert client.get(
            f"/api/rulebook-reviews/{item['id']}"
        ).status_code == 500
        assert client.post(
            f"/api/rulebook-reviews/{item['id']}/decision",
            json={"decision": "approved"},
        ).status_code == 500

        with database.connect() as connection:
            after = connection.execute(
                f"SELECT {column}, status FROM rulebook_review_items WHERE id = ?",
                (item["id"],),
            ).fetchone()

    assert before[column] == payload
    assert after[column] == payload
    assert before["status"] == after["status"] == "pending"


def test_semantically_unsafe_snapshot_is_quarantined(tmp_path: Path) -> None:
    configure_paths(tmp_path)
    with TestClient(app) as client:
        import_fixture(client)
        item, _ = submit_candidate(community_payload())

        snapshot = item["candidate"]
        snapshot["url"] = "javascript:alert(1)"
        serialized = json.dumps(
            snapshot,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        database = Database(settings.database_path)
        with database.connect() as connection:
            connection.execute(
                """
                UPDATE rulebook_review_items
                SET candidate_json = ?, candidate_key = ?, url = ?
                WHERE id = ?
                """,
                (serialized, digest, "javascript:alert(1)", item["id"]),
            )

        listing = client.get(
            "/api/rulebook-reviews?status=pending&limit=50&offset=0"
        ).json()
        assert listing["items"] == []
        assert listing["corrupt_count"] == 1


def test_decided_filter_and_backend_pagination(tmp_path: Path) -> None:
    configure_paths(tmp_path)
    with TestClient(app) as client:
        import_fixture(client)
        for index in range(101):
            submit_candidate(
                community_payload(
                    url=f"https://community.example/paged-{index}.pdf",
                )
            )

        first = client.get(
            "/api/rulebook-reviews?status=pending&limit=50&offset=0"
        ).json()
        last = client.get(
            "/api/rulebook-reviews?status=pending&limit=50&offset=100"
        ).json()
        assert first["total"] == 101
        assert len(first["items"]) == 50
        assert len(last["items"]) == 1

        review_id = first["items"][0]["id"]
        response = client.post(
            f"/api/rulebook-reviews/{review_id}/decision",
            json={"decision": "approved"},
        )
        assert response.status_code == 200
        decided = client.get(
            "/api/rulebook-reviews?status=decided&limit=50&offset=0"
        ).json()
        assert decided["total"] == 1
        assert decided["items"][0]["id"] == review_id


def test_concurrent_opposite_decisions_converge_without_lost_update(
    tmp_path: Path,
) -> None:
    configure_paths(tmp_path)
    with TestClient(app) as client:
        import_fixture(client)
        item, _ = submit_candidate(community_payload())

    database = Database(settings.database_path)
    barrier = Barrier(2)

    def decide(value: str):
        barrier.wait()
        try:
            return RulebookReviewQueue(database).decide(
                item["id"],
                decision=value,
            )
        except RulebookReviewConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            future.result()
            for future in [
                pool.submit(decide, "approved"),
                pool.submit(decide, "rejected"),
            ]
        ]
    successes = [result for result in results if isinstance(result, dict)]
    conflicts = [
        result for result in results
        if isinstance(result, RulebookReviewConflict)
    ]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert successes[0]["status"] in {"approved", "rejected"}


def test_concurrent_identical_decisions_preserve_first_audit_data(
    tmp_path: Path,
) -> None:
    configure_paths(tmp_path)
    with TestClient(app) as client:
        import_fixture(client)
        item, _ = submit_candidate(
            community_payload(url="https://community.example/same-decision.pdf")
        )

    database = Database(settings.database_path)
    barrier = Barrier(2)

    def decide(note: str):
        barrier.wait()
        return RulebookReviewQueue(database).decide(
            item["id"],
            decision="approved",
            note=note,
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            future.result()
            for future in [
                pool.submit(decide, "first contender"),
                pool.submit(decide, "second contender"),
            ]
        ]

    assert {result["status"] for result in results} == {"approved"}
    assert len({result["decided_at"] for result in results}) == 1
    assert len({result["decision_note"] for result in results}) == 1
    assert results[0]["decision_note"] in {
        "first contender",
        "second contender",
    }
