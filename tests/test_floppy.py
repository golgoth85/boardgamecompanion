from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.database import Database
from boardgamecompanion.floppy import (
    FloppyClient,
    FloppyConfig,
    FloppyPlanChanged,
    apply_floppy_sync,
    build_sync_preview,
    load_floppy_links,
)
from boardgamecompanion.main import app
from boardgamecompanion.settings import settings


def media_row(
    *,
    item_db_id: int,
    media_id: str,
    source: str,
    title: str,
    year: int | None = None,
    bgg_id: int | None = None,
) -> dict:
    item = {
        "media_id": media_id,
        "source": source,
        "title": title,
        "release_date": f"{year}-01-01" if year else None,
        "ids": {"bgg": str(bgg_id)} if bgg_id is not None else {},
    }
    return {
        "id": item_db_id,
        "consumption_id": None,
        "item": item,
        "tracked": True,
    }


def collection_row(
    *,
    entry_id: int,
    media_id: str,
    source: str,
    title: str,
) -> dict:
    return {
        "id": entry_id,
        "media_type": "",
        "item": {
            "media_id": media_id,
            "source": source,
            "title": title,
        },
    }


def local_game(
    bgg_id: int,
    title: str,
    year: int,
    *,
    price_paid: float | None = None,
    acquired_from: str | None = None,
    acquisition_date: str | None = None,
) -> dict:
    return {
        "bgg_id": bgg_id,
        "title": title,
        "original_title": title,
        "year_published": year,
        "item_type": "standalone",
        "coll_id": 800000 + bgg_id,
        "own": 1,
        "price_paid": price_paid,
        "acquisition_date": acquisition_date,
        "acquired_from": acquired_from,
        "quantity": 1,
        "version_languages": None,
        "version_publishers": None,
        "version_nickname": None,
    }


def test_floppy_client_auth_pagination_schema_and_write_payloads() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)

        if request.url.path == "/api/v1/info/":
            assert "X-API-Key" not in request.headers
            return httpx.Response(200, json={"name": "Floppy", "version": "26.9"})

        if request.url.path == "/api/v1/media/boardgame/" and request.method == "GET":
            assert request.headers["X-API-Key"] == "secret"
            offset = int(request.url.params.get("offset", "0"))
            if offset == 0:
                return httpx.Response(
                    200,
                    json={
                        "pagination": {"total": 201},
                        "results": [
                            media_row(
                                item_db_id=5000 + index,
                                media_id=str(1000 + index),
                                source="bgg",
                                title=f"Game {index}",
                                bgg_id=1000 + index,
                            )
                            for index in range(200)
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "pagination": {"total": 201},
                    "results": [
                        media_row(
                            item_db_id=5200,
                            media_id="1200",
                            source="bgg",
                            title="Game 200",
                            bgg_id=1200,
                        )
                    ],
                },
            )

        if request.url.path == "/api/schema/":
            return httpx.Response(
                200,
                json={
                    "paths": {
                        "/api/v1/media/{media_type}/": {
                            "post": {"responses": {"201": {}}}
                        },
                        "/api/v1/collection/": {
                            "post": {"responses": {"201": {}}}
                        },
                    }
                },
            )

        if request.url.path == "/api/v1/media/boardgame/" and request.method == "POST":
            payload = request.read()
            body = __import__("json").loads(payload)
            assert body["status"] == ""
            if body["source"] == "bgg":
                assert body["media_id"] == "777"
                return httpx.Response(
                    201,
                    json=media_row(
                        item_db_id=77,
                        media_id="777",
                        source="bgg",
                        title="Provider Game",
                        bgg_id=777,
                    ),
                )
            assert body["source"] == "manual"
            assert body["title"] == "Manual Game"
            return httpx.Response(
                201,
                json=media_row(
                    item_db_id=88,
                    media_id="manual-88",
                    source="manual",
                    title="Manual Game",
                ),
            )

        if request.url.path == "/api/v1/collection/" and request.method == "POST":
            body = __import__("json").loads(request.read())
            assert body == {
                "item_id": 77,
                "purchase_price": 49.9,
                "purchase_location": "Shop",
                "collected_at": "2026-01-02",
            }
            return httpx.Response(
                201,
                json=collection_row(
                    entry_id=991,
                    media_id="777",
                    source="bgg",
                    title="Provider Game",
                ),
            )

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = FloppyClient(
        FloppyConfig(base_url="http://floppy:8000/", api_key="secret"),
        transport=httpx.MockTransport(handler),
    )

    assert client.info()["name"] == "Floppy"
    assert len(client.boardgames()) == 201
    assert client.schema_capabilities()["write_contract_ready"] is True

    provider = client.track_boardgame_bgg(777)
    assert provider["id"] == 77
    manual = client.track_boardgame_manual("Manual Game")
    assert manual["id"] == 88
    owned = client.add_collection_entry(
        item_db_id=77,
        purchase_price=49.9,
        purchase_location="Shop",
        collected_at="2026-01-02",
    )
    assert owned["id"] == 991


def test_preview_distinguishes_owned_collection_media_and_missing() -> None:
    local = [
        local_game(101, "Already Owned", 2021),
        local_game(202, "Tracked Only", 2022),
        local_game(303, "Missing Game", 2023),
        local_game(404, "Saved Manual", 2024),
    ]
    remote = [
        media_row(
            item_db_id=11,
            media_id="101",
            source="bgg",
            title="Already Owned",
            year=2021,
            bgg_id=101,
        ),
        media_row(
            item_db_id=22,
            media_id="202",
            source="bgg",
            title="Tracked Only",
            year=2022,
            bgg_id=202,
        ),
        media_row(
            item_db_id=44,
            media_id="manual-44",
            source="manual",
            title="Saved Manual",
            year=2024,
        ),
    ]
    collection = [
        collection_row(
            entry_id=501,
            media_id="101",
            source="bgg",
            title="Already Owned",
        )
    ]
    links = {
        404: {
            "bgg_id": 404,
            "source": "manual",
            "media_id": "manual-44",
            "item_db_id": 44,
            "collection_entry_id": None,
            "link_method": "manual_fallback",
        }
    }

    preview = build_sync_preview(local, remote, collection, links)

    assert preview["already_owned"] == 1
    assert preview["needs_collection"] == 2
    assert preview["needs_media"] == 1
    assert preview["actionable"] == 3
    assert preview["matched_by_bgg_id"] == 2
    assert preview["matched_by_saved_link"] == 1
    assert preview["matched_by_title_year"] == 0
    assert {row["bgg_id"] for row in preview["needs_collection_items"]} == {202, 404}
    assert preview["needs_media_items"][0]["bgg_id"] == 303
    assert len(preview["plan_hash"]) == 64


def test_preview_uses_title_year_fallback_but_marks_duplicates_ambiguous() -> None:
    local = [
        local_game(501, "Café International", 1989),
        local_game(502, "Duplicate", 2020),
    ]
    remote = [
        media_row(
            item_db_id=51,
            media_id="manual-51",
            source="manual",
            title="Cafe International",
            year=1989,
        ),
        media_row(
            item_db_id=52,
            media_id="a",
            source="manual",
            title="Duplicate",
            year=2020,
        ),
        media_row(
            item_db_id=53,
            media_id="b",
            source="manual",
            title="Duplicate",
            year=2020,
        ),
    ]

    preview = build_sync_preview(local, remote)

    assert preview["matched_by_title_year"] == 1
    assert preview["ambiguous"] == 1
    assert preview["ambiguous_items"][0]["bgg_id"] == 502


def test_apply_sync_provider_success_and_collection_metadata(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    _insert_local_owned(database, local_game(
        701,
        "Provider Game",
        2020,
        price_paid=39.5,
        acquired_from="Friendly Store",
        acquisition_date="2026-02-03",
    ))

    state = {"media": [], "collection": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/media/boardgame/" and request.method == "GET":
            return _page(state["media"])
        if request.url.path == "/api/v1/collection/" and request.method == "GET":
            return _page(state["collection"])
        if request.url.path == "/api/v1/media/boardgame/" and request.method == "POST":
            body = __import__("json").loads(request.read())
            assert body == {"source": "bgg", "media_id": "701", "status": ""}
            row = media_row(
                item_db_id=1701,
                media_id="701",
                source="bgg",
                title="Provider Game",
                year=2020,
                bgg_id=701,
            )
            state["media"].append(row)
            return httpx.Response(201, json=row)
        if request.url.path == "/api/v1/collection/" and request.method == "POST":
            body = __import__("json").loads(request.read())
            assert body == {
                "item_id": 1701,
                "purchase_price": 39.5,
                "purchase_location": "Friendly Store",
                "collected_at": "2026-02-03",
            }
            row = collection_row(
                entry_id=2701,
                media_id="701",
                source="bgg",
                title="Provider Game",
            )
            state["collection"].append(row)
            return httpx.Response(201, json=row)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = FloppyClient(
        FloppyConfig("http://floppy", "secret"),
        transport=httpx.MockTransport(handler),
    )
    preview = build_sync_preview(
        [local_game(701, "Provider Game", 2020)],
        [],
        [],
    )

    result = apply_floppy_sync(
        database,
        client,
        expected_plan_hash=preview["plan_hash"],
        batch_size=20,
    )

    assert result["attempted"] == 1
    assert result["media_created"] == 1
    assert result["collection_created"] == 1
    assert result["failed"] == 0
    links = load_floppy_links(database)
    assert links[701]["source"] == "bgg"
    assert links[701]["item_db_id"] == 1701
    assert links[701]["collection_entry_id"] == 2701

    second = build_sync_preview(
        [local_game(701, "Provider Game", 2020)],
        state["media"],
        state["collection"],
        links,
    )
    assert second["actionable"] == 0
    assert second["already_owned"] == 1


def test_apply_sync_falls_back_to_manual_and_persists_partial_link(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    _insert_local_owned(database, local_game(801, "No BGG Provider", 2022))

    state = {"media": [], "collection": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/media/boardgame/" and request.method == "GET":
            return _page(state["media"])
        if request.url.path == "/api/v1/collection/" and request.method == "GET":
            return _page(state["collection"])
        if request.url.path == "/api/v1/media/boardgame/" and request.method == "POST":
            body = __import__("json").loads(request.read())
            if body["source"] == "bgg":
                return httpx.Response(500, json={"detail": "BGG provider unavailable"})
            row = media_row(
                item_db_id=1801,
                media_id="manual-1801",
                source="manual",
                title="No BGG Provider",
                year=2022,
            )
            state["media"].append(row)
            return httpx.Response(201, json=row)
        if request.url.path == "/api/v1/collection/" and request.method == "POST":
            return httpx.Response(500, json={"detail": "collection temporarily failed"})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = FloppyClient(
        FloppyConfig("http://floppy", "secret"),
        transport=httpx.MockTransport(handler),
    )
    preview = build_sync_preview(
        [local_game(801, "No BGG Provider", 2022)],
        [],
        [],
    )

    result = apply_floppy_sync(
        database,
        client,
        expected_plan_hash=preview["plan_hash"],
    )

    assert result["media_created"] == 1
    assert result["collection_created"] == 0
    assert result["failed"] == 1
    link = load_floppy_links(database)[801]
    assert link["source"] == "manual"
    assert link["media_id"] == "manual-1801"
    assert link["collection_entry_id"] is None

    recovery_preview = build_sync_preview(
        [local_game(801, "No BGG Provider", 2022)],
        state["media"],
        [],
        load_floppy_links(database),
    )
    assert recovery_preview["needs_media"] == 0
    assert recovery_preview["needs_collection"] == 1
    assert recovery_preview["matched_by_saved_link"] == 1


def test_apply_sync_rejects_stale_plan(tmp_path: Path) -> None:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    _insert_local_owned(database, local_game(901, "Stale", 2024))

    remote = [
        media_row(
            item_db_id=1901,
            media_id="901",
            source="bgg",
            title="Stale",
            year=2024,
            bgg_id=901,
        )
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/media/boardgame/":
            return _page(remote)
        if request.url.path == "/api/v1/collection/":
            return _page([])
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = FloppyClient(
        FloppyConfig("http://floppy", "secret"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(FloppyPlanChanged):
        apply_floppy_sync(
            database,
            client,
            expected_plan_hash="0" * 64,
        )


def test_floppy_api_reports_unconfigured_without_network(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    for key in (
        "BGC_FLOPPY_URL",
        "BGC_FLOPPY_API_KEY",
        "BGC_FLOPPY_TIMEOUT_SECONDS",
        "BGC_FLOPPY_VERIFY_TLS",
    ):
        monkeypatch.delenv(key, raising=False)

    with TestClient(app) as client:
        status = client.get("/api/integrations/floppy/status")
        preview = client.get("/api/integrations/floppy/preview")

    assert status.status_code == 200
    assert status.json()["configured"] is False
    assert preview.status_code == 409
    assert "Open Impostazioni" in preview.json()["detail"]


def _page(rows: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "pagination": {
                "total": len(rows),
                "limit": 200,
                "offset": 0,
                "next": None,
                "previous": None,
            },
            "results": rows,
        },
    )


def _insert_local_owned(database: Database, game: dict) -> None:
    now = "2026-09-22T00:00:00+00:00"
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO board_games (
                bgg_id, title, original_title, year_published, item_type,
                source_metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, '{}', ?, ?)
            """,
            (
                game["bgg_id"],
                game["title"],
                game["original_title"],
                game["year_published"],
                game["item_type"],
                now,
                now,
            ),
        )
        board_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id = ?",
            (game["bgg_id"],),
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO collection_entries (
                coll_id, board_game_id, own, price_paid, acquisition_date,
                acquired_from, quantity, source_metadata_json, created_at, updated_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, '{}', ?, ?)
            """,
            (
                game["coll_id"],
                board_id,
                game.get("price_paid"),
                game.get("acquisition_date"),
                game.get("acquired_from"),
                game.get("quantity"),
                now,
                now,
            ),
        )
