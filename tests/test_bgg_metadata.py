from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from boardgamecompanion.bgg_metadata import (
    BggApiClient,
    BggApiConfig,
    BggMetadataError,
    BggMetadataStore,
)
from boardgamecompanion.database import Database


XML = b"""<?xml version='1.0'?>
<items><item type='boardgame' id='173346'>
 <name type='primary' value='7 Wonders Duel'/>
 <name type='alternate' value='7 Wonders: Duel'/>
 <yearpublished value='2015'/>
 <image>https://cf.geekdo-images.com/cover.jpg</image>
 <description>A &amp; B</description>
 <link type='boardgamepublisher' value='Repos Production'/>
 <link type='boardgamedesigner' value='Antoine Bauza'/>
 <link type='boardgamecategory' value='Ancient'/>
</item></items>"""


def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    now = datetime.now(UTC).isoformat()
    with db.transaction() as connection:
        connection.execute(
            """INSERT INTO board_games
               (bgg_id,title,source_metadata_json,created_at,updated_at)
               VALUES (173346,'7 Wonders Duel','{}',?,?)""", (now, now)
        )
    return db


def test_direct_bgg_api_uses_bearer_token_and_persists_cover_metadata(tmp_path: Path) -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers["authorization"]
        observed["url"] = str(request.url)
        return httpx.Response(200, content=XML, request=request)

    client = BggApiClient(
        BggApiConfig("secret", min_interval_seconds=0),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    store = BggMetadataStore(database(tmp_path), client)
    item = store.refresh(173346)

    assert observed == {
        "authorization": "Bearer secret",
        "url": "https://boardgamegeek.com/xmlapi2/thing?id=173346",
    }
    assert item["external_id"] == "173346"
    assert item["cover_url"] == "https://cf.geekdo-images.com/cover.jpg"
    assert item["publishers"] == ["Repos Production"]
    assert item["metadata"]["bgg_id"] == 173346


def test_bgg_api_rejects_conflicting_identity_and_keeps_catalog_independent(tmp_path: Path) -> None:
    wrong = XML.replace(b"id='173346'", b"id='99'")
    client = BggApiClient(
        BggApiConfig("secret", min_interval_seconds=0, max_attempts=1),
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=wrong, request=request))),
    )
    store = BggMetadataStore(database(tmp_path), client, retry_seconds=60)

    with pytest.raises(BggMetadataError, match="conflicting"):
        store.refresh(173346)

    state = store.get(173346)
    assert state is not None and state["consecutive_failures"] == 1
    with store.database.connect() as connection:
        assert connection.execute("SELECT title FROM board_games WHERE bgg_id=173346").fetchone()["title"] == "7 Wonders Duel"


def test_bgg_metadata_cache_survives_restart_without_api_client(tmp_path: Path) -> None:
    db = database(tmp_path)
    client = BggApiClient(
        BggApiConfig("secret", min_interval_seconds=0),
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=XML, request=request))),
    )
    BggMetadataStore(db, client).refresh(173346)

    restarted = BggMetadataStore(db, None)
    assert restarted.get(173346)["title"] == "7 Wonders Duel"
    with pytest.raises(BggMetadataError, match="not configured"):
        restarted.refresh(173346, force=True)

