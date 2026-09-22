from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from boardgamecompanion.floppy import (
    FloppyClient,
    FloppyConfig,
    build_sync_preview,
)
from boardgamecompanion.main import app
from boardgamecompanion.settings import settings


def test_floppy_client_auth_pagination_and_schema() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)

        if request.url.path == "/api/v1/info/":
            assert "X-API-Key" not in request.headers
            return httpx.Response(200, json={"name": "Floppy", "version": "26.9"})

        if request.url.path == "/api/v1/media/boardgame/":
            assert request.headers["X-API-Key"] == "secret"
            offset = int(request.url.params.get("offset", "0"))
            if offset == 0:
                return httpx.Response(
                    200,
                    json={
                        "pagination": {"total": 201},
                        "results": [
                            {
                                "title": f"Game {index}",
                                "source": "bgg",
                                "media_id": str(1000 + index),
                            }
                            for index in range(200)
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "pagination": {"total": 201},
                    "results": [
                        {"title": "Game 200", "source": "bgg", "media_id": "1200"}
                    ],
                },
            )

        if request.url.path == "/api/schema/":
            return httpx.Response(
                200,
                json={
                    "paths": {
                        "/api/v1/media/{media_type}/{source}/{media_id}/": {
                            "post": {"responses": {"200": {}}}
                        },
                        "/api/v1/collection/": {
                            "post": {"responses": {"201": {}}}
                        },
                    }
                },
            )

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = FloppyClient(
        FloppyConfig(base_url="http://floppy:8000/", api_key="secret"),
        transport=httpx.MockTransport(handler),
    )

    assert client.info()["name"] == "Floppy"
    assert len(client.boardgames()) == 201
    assert client.schema_capabilities() == {
        "available": True,
        "media_write": True,
        "collection_write": True,
        "write_contract_ready": True,
    }

    boardgame_calls = [
        request for request in calls if request.url.path == "/api/v1/media/boardgame/"
    ]
    assert len(boardgame_calls) == 2


def test_matching_prefers_bgg_id_then_title_and_year() -> None:
    local = [
        {
            "bgg_id": 101,
            "title": "Ark Nova",
            "year_published": 2021,
            "item_type": "standalone",
        },
        {
            "bgg_id": 202,
            "title": "Café International",
            "year_published": 1989,
            "item_type": "standalone",
        },
        {
            "bgg_id": 303,
            "title": "Missing Game",
            "year_published": 2020,
            "item_type": "standalone",
        },
    ]
    remote = [
        {
            "title": "Totally Different Display Title",
            "source": "bgg",
            "media_id": "101",
            "year": 2021,
        },
        {
            "title": "Cafe International",
            "source": "manual",
            "media_id": "9999",
            "year": 1989,
        },
    ]

    preview = build_sync_preview(local, remote)

    assert preview["local_owned"] == 3
    assert preview["remote_boardgames"] == 2
    assert preview["matched"] == 2
    assert preview["matched_by_bgg_id"] == 1
    assert preview["matched_by_title_year"] == 1
    assert preview["missing_in_floppy"] == 1
    assert preview["ambiguous"] == 0
    assert preview["missing"][0]["bgg_id"] == 303


def test_matching_marks_duplicate_candidates_ambiguous() -> None:
    local = [
        {
            "bgg_id": 101,
            "title": "Duplicate",
            "year_published": 2020,
            "item_type": "standalone",
        }
    ]
    remote = [
        {"title": "Duplicate A", "source": "bgg", "media_id": "101"},
        {"title": "Duplicate B", "source": "boardgamegeek", "media_id": "101"},
    ]

    preview = build_sync_preview(local, remote)

    assert preview["matched"] == 0
    assert preview["ambiguous"] == 1
    assert preview["ambiguous_items"][0]["reason"] == "duplicate_bgg_id"


def test_floppy_api_reports_unconfigured_without_network(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    monkeypatch.setattr(settings, "floppy_url", None)
    monkeypatch.setattr(settings, "floppy_api_key", None)

    with TestClient(app) as client:
        status = client.get("/api/integrations/floppy/status")
        preview = client.get("/api/integrations/floppy/preview")

    assert status.status_code == 200
    assert status.json()["configured"] is False
    assert status.json()["authenticated"] is False
    assert preview.status_code == 409
    assert "BGC_FLOPPY_URL" in preview.json()["detail"]
