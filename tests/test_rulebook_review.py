from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.database import Database
from boardgamecompanion.main import app
from boardgamecompanion.rulebook_review import (
    RulebookReviewCandidateMismatch,
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
