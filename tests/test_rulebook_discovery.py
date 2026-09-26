from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path

import httpx

from boardgamecompanion.database import Database
from boardgamecompanion.rulebook_discovery import RulebookDiscoveryService
from boardgamecompanion.rulebook_providers import (
    ProviderHttpClient,
    ReposProductionProvider,
)
from boardgamecompanion.rulebook_review import RulebookReviewQueue
from boardgamecompanion.rulebook_fetch import RulebookFetchResult
from boardgamecompanion.rulebook_updates import RulebookUpdateService
from boardgamecompanion.rulebooks import (
    RulebookCandidate,
    RulebookProviderError,
    RulebookQuery,
    RulebookResolver,
)


def query(**overrides) -> RulebookQuery:
    values = {
        "bgg_id": 173346,
        "title": "7 Wonders Duel",
        "original_title": "7 Wonders Duel",
        "year": 2015,
        "item_type": "boardgame",
        "publishers": ("Repos Production",),
    }
    values.update(overrides)
    return RulebookQuery(**values)


def repos_html(title: str = "7 Wonders Duel") -> bytes:
    return f"""<!doctype html><h1>{title}</h1>
      <a href='https://cdn.svc.asmodee.net/games/7wd/it/7wd-rules-it.pdf'>IT</a>
      <a href='https://cdn.svc.asmodee.net/games/7wd/en/7wd-rules-us.pdf'>EN</a>
      <a href='https://cdn.svc.asmodee.net/games/7wd/fr/7wd-rules-fr.pdf'>FR</a>""".encode()


def test_repos_adapter_normalizes_both_it_and_en_and_filters_other_languages() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=repos_html(), request=request))
    provider = ReposProductionProvider(
        ProviderHttpClient(client=httpx.Client(transport=transport), min_interval_seconds=0)
    )

    candidates = tuple(provider.discover(query()))

    assert [item.language for item in candidates] == ["it", "en"]
    assert all(item.bgg_id == 173346 for item in candidates)
    assert all(item.source_kind.value == "official_publisher" for item in candidates)
    assert all(item.confidence == 100 and item.official for item in candidates)


def test_repos_adapter_requires_publisher_and_exact_base_expansion_identity() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=repos_html("7 Wonders Duel: Pantheon"), request=request)

    provider = ReposProductionProvider(
        ProviderHttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval_seconds=0)
    )
    assert tuple(provider.discover(query(publishers=("Other",)))) == ()
    assert calls == 0
    assert tuple(provider.discover(query())) == ()
    assert calls == 1


class StaticProvider:
    def __init__(self, name: str, values: tuple[RulebookCandidate, ...] = (), error: Exception | None = None):
        self.name = name
        self.values = values
        self.error = error

    def discover(self, _: RulebookQuery):
        if self.error:
            raise self.error
        return self.values


def candidate(*, provider: str, source: str, language: str, url: str, official: bool, confidence: int, bgg_id: int | None = 173346) -> RulebookCandidate:
    return RulebookCandidate(
        provider=provider,
        source_kind=source,
        url=url,
        language=language,
        official=official,
        confidence=confidence,
        bgg_id=bgg_id,
        game_title="7 Wonders Duel",
        year=2015,
    )


def test_ranking_keeps_trust_authoritative_then_prefers_it_over_en() -> None:
    official_en = candidate(provider="official", source="official_publisher", language="en", url="https://publisher.example/en.pdf", official=True, confidence=100)
    official_it = candidate(provider="official", source="official_publisher", language="it", url="https://publisher.example/it.pdf", official=True, confidence=100)
    community_it = candidate(provider="community", source="community", language="it", url="https://community.example/it.pdf", official=False, confidence=70, bgg_id=None)
    result = RulebookResolver((StaticProvider("all", (community_it, official_en, official_it)),)).resolve(query())
    assert [item.candidate for item in result.candidates] == [official_it, official_en, community_it]


def test_conflicting_bgg_id_is_rejected_and_duplicate_url_is_deduplicated() -> None:
    good = candidate(provider="a", source="official_publisher", language="it", url="https://publisher.example/rules.pdf", official=True, confidence=100)
    duplicate = candidate(provider="b", source="official_mirror", language="it", url="https://publisher.example/rules.pdf#copy", official=True, confidence=95)
    conflict = candidate(provider="bad", source="official_publisher", language="it", url="https://publisher.example/wrong.pdf", official=True, confidence=100, bgg_id=99)
    result = RulebookResolver((StaticProvider("values", (good, duplicate, conflict)),)).resolve(query())
    assert [item.candidate for item in result.candidates] == [good]


def test_provider_failure_is_isolated_from_partial_success() -> None:
    good = candidate(provider="good", source="official_publisher", language="it", url="https://publisher.example/rules.pdf", official=True, confidence=100)
    result = RulebookResolver((StaticProvider("broken", error=RulebookProviderError("down")), StaticProvider("good", (good,)))).resolve(query())
    assert result.best and result.best.candidate == good
    assert [(item.provider, item.error_type) for item in result.failures] == [("broken", "RulebookProviderError")]


def test_http_client_bounds_timeout_retries_and_rate_limit() -> None:
    calls = 0
    sleeps: list[float] = []
    ticks = iter((0.0, 0.0, 0.1, 0.1, 2.0, 2.0))

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, content=b"ok", request=request)

    client = ProviderHttpClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=2,
        min_interval_seconds=1,
        sleep=sleeps.append,
        monotonic=lambda: next(ticks),
    )
    response = client.get("https://provider.example/index", allowed_hosts={"provider.example"})
    assert response.content == b"ok"
    assert calls == 2
    assert sleeps == [0.25, 0.9]


def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    now = datetime.now(UTC).isoformat()
    with db.transaction() as connection:
        connection.execute(
            """INSERT INTO board_games
               (bgg_id,title,original_title,year_published,item_type,source_metadata_json,created_at,updated_at)
               VALUES (173346,'7 Wonders Duel','7 Wonders Duel',2015,'boardgame','{}',?,?)""",
            (now, now),
        )
        game_id = connection.execute("SELECT id FROM board_games WHERE bgg_id=173346").fetchone()["id"]
        connection.execute(
            """INSERT INTO collection_entries
               (board_game_id,own,version_publishers,source_metadata_json,created_at,updated_at)
               VALUES (?,1,'Repos Production','{}',?,?)""", (game_id, now, now)
        )
    return db


def discovery_providers() -> tuple[StaticProvider, ...]:
    return (
        StaticProvider("official", (
            candidate(provider="official", source="official_publisher", language="it", url="https://publisher.example/it.pdf", official=True, confidence=100),
            candidate(provider="official", source="official_publisher", language="en", url="https://publisher.example/en.pdf", official=True, confidence=100),
        )),
        StaticProvider("community", (
            candidate(provider="community", source="community", language="it", url="https://community.example/it.pdf", official=False, confidence=70, bgg_id=None),
        )),
    )


def test_discovery_routes_candidates_through_policy_and_rediscovery_is_idempotent(tmp_path: Path) -> None:
    db = database(tmp_path)
    service = RulebookDiscoveryService(db, discovery_providers(), refresh_seconds=3600, empty_refresh_seconds=3600)
    assert service.synchronize_catalog() == 1

    first = service.run_game(173346)
    second = service.run_game(173346)
    reviews = RulebookReviewQueue(db).list(limit=20)

    assert first["candidates_found"] == 3 and first["review_items_created"] == 3
    assert second["candidates_found"] == 3 and second["review_items_created"] == 0
    assert reviews["total"] == 3
    assert sorted(item["status"] for item in reviews["items"]) == ["approved", "approved", "pending"]
    community = next(item for item in reviews["items"] if item["candidate"]["provider"] == "community")
    assert community["candidate"]["official"] is False
    assert community["policy_action"] == "review"


def test_discovery_persists_state_across_service_restart_and_partial_outage(tmp_path: Path) -> None:
    db = database(tmp_path)
    providers = (StaticProvider("broken", error=RuntimeError("offline")), discovery_providers()[0])
    first = RulebookDiscoveryService(db, providers)
    first.synchronize_catalog()
    result = first.run_game(173346)
    restarted = RulebookDiscoveryService(db, providers)
    state = restarted.list_status(bgg_id=173346)["items"][0]

    assert result["status"] == "partial"
    assert state["status"] == "partial"
    assert state["provider_failures"] == 1
    with db.connect() as connection:
        runs = connection.execute("SELECT provider,outcome FROM rulebook_discovery_provider_runs ORDER BY provider").fetchall()
    assert [(row["provider"], row["outcome"]) for row in runs] == [("broken", "failed"), ("official", "succeeded")]


def test_discovery_to_policy_guarded_fetch_archive_and_auto_index_queue(tmp_path: Path) -> None:
    db = database(tmp_path)
    discovery = RulebookDiscoveryService(db, (discovery_providers()[0],))
    discovery.synchronize_catalog()
    result = discovery.run_game(173346)
    assert result["review_items_created"] == 2

    pdf = b"%PDF-1.4\nreal pipeline fixture\n%%EOF\n"

    class Fetcher:
        def fetch(self, found: RulebookCandidate) -> RulebookFetchResult:
            digest = hashlib.sha256(pdf).hexdigest()
            path = tmp_path / "manuals" / f"{digest}.pdf"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pdf)
            return RulebookFetchResult(
                candidate=found,
                requested_url=found.url,
                final_url=found.url,
                status_code=200,
                content_type="application/pdf",
                byte_size=len(pdf),
                sha256=digest,
                local_path=str(path),
            )

    updates = RulebookUpdateService(
        db,
        tmp_path / "manuals",
        fetcher_factory=Fetcher,
        default_interval_seconds=3600,
        retry_base_seconds=60,
        retry_max_seconds=60,
        lease_seconds=60,
    )
    synchronized = updates.synchronize_approved_targets()
    assert synchronized["created"] == 2
    review = RulebookReviewQueue(db).list(status="approved", limit=10)["items"][0]
    archived = updates.run_review_now(review["id"])

    assert archived["outcome"] == "created"
    with db.connect() as connection:
        document = connection.execute("SELECT id,language,source_provider,is_official FROM game_documents").fetchone()
        job = connection.execute("SELECT status,stage FROM document_index_jobs WHERE document_id=?", (document["id"],)).fetchone()
    assert document["source_provider"] == "official"
    assert document["is_official"] == 1
    assert job["status"] == "pending" and job["stage"] == "queued"
