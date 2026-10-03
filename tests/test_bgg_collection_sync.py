from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from boardgamecompanion.bgg_collection_sync import (
    BggCollectionClient,
    BggCollectionConfig,
    BggCollectionSyncService,
)
from boardgamecompanion.database import Database


BASE_XML = b"""<?xml version='1.0'?>
<items totalitems='1'>
  <item objecttype='thing' objectid='111' subtype='boardgame' collid='9001'>
    <name>Base Game</name>
    <yearpublished>2022</yearpublished>
    <stats minplayers='2' maxplayers='4' minplaytime='30' maxplaytime='60' playingtime='45' numowned='1234'>
      <rating value='8'>
        <average value='7.5'/>
        <bayesaverage value='7.1'/>
        <averageweight value='2.1'/>
        <ranks><rank name='boardgame' value='321'/></ranks>
      </rating>
    </stats>
    <status own='1' prevowned='0' fortrade='0' want='0' wanttoplay='0' wanttobuy='0' wishlist='0' preordered='0'/>
    <numplays>4</numplays>
  </item>
</items>"""

EXP_XML = b"""<?xml version='1.0'?>
<items totalitems='1'>
  <item objecttype='thing' objectid='222' subtype='boardgameexpansion' collid='9002'>
    <name>Base Game: Expansion</name>
    <yearpublished>2023</yearpublished>
    <stats minplayers='2' maxplayers='5' minplaytime='30' maxplaytime='75' playingtime='60' numowned='456'>
      <rating value='N/A'>
        <average value='8.0'/>
        <bayesaverage value='7.4'/>
        <averageweight value='2.4'/>
        <ranks><rank name='boardgame' value='N/A'/></ranks>
      </rating>
    </stats>
    <status own='1' prevowned='0' fortrade='0' want='0' wanttoplay='0' wanttobuy='0' wishlist='0' preordered='0'/>
    <numplays>0</numplays>
  </item>
</items>"""


def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    return db


def test_collection_client_retries_202_and_splits_base_from_expansions() -> None:
    calls: list[str] = []
    queued_once = {"done": False}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if not queued_once["done"]:
            queued_once["done"] = True
            return httpx.Response(202, request=request)
        body = EXP_XML if request.url.params.get("subtype") == "boardgameexpansion" else BASE_XML
        return httpx.Response(200, content=body, request=request)

    client = BggCollectionClient(
        BggCollectionConfig(
            application_token="secret",
            username="tester",
            min_interval_seconds=0,
            max_attempts=3,
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _seconds: None,
    )

    items = client.owned_collection()

    assert [item["bgg_id"] for item in items] == [111, 222]
    assert items[0]["item_type"] == "standalone"
    assert items[1]["item_type"] == "expansion"
    assert any("excludesubtype=boardgameexpansion" in url for url in calls)
    assert any("subtype=boardgameexpansion" in url for url in calls)


def test_collection_sync_is_idempotent_and_does_not_delete_missing_owned_rows(tmp_path: Path) -> None:
    db = database(tmp_path)

    responses = {"base": BASE_XML, "exp": EXP_XML}

    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            responses["exp"]
            if request.url.params.get("subtype") == "boardgameexpansion"
            else responses["base"]
        )
        return httpx.Response(200, content=body, request=request)

    service = BggCollectionSyncService(
        db,
        BggCollectionClient(
            BggCollectionConfig(
                application_token="secret",
                username="tester",
                min_interval_seconds=0,
            ),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
        interval_seconds=6 * 60 * 60,
    )

    first = service.sync(force=True)
    assert first is not None
    assert first.created_count == 2
    assert first.updated_count == 0
    assert first.unchanged_count == 0
    assert first.created_bgg_ids == (111, 222)

    second = service.sync(force=True)
    assert second is not None
    assert second.created_count == 0
    assert second.updated_count == 0
    assert second.unchanged_count == 2

    responses["base"] = b"<?xml version='1.0'?><items totalitems='0'></items>"
    third = service.sync(force=True)
    assert third is not None
    assert third.row_count == 1

    with db.connect() as connection:
        base = connection.execute(
            """SELECT g.item_type,c.own,c.coll_id
               FROM board_games g
               JOIN collection_entries c ON c.board_game_id=g.id
               WHERE g.bgg_id=111"""
        ).fetchone()
        expansion = connection.execute(
            """SELECT g.item_type,c.own,c.coll_id
               FROM board_games g
               JOIN collection_entries c ON c.board_game_id=g.id
               WHERE g.bgg_id=222"""
        ).fetchone()
        copies = connection.execute(
            "SELECT COUNT(*) AS count FROM physical_copies"
        ).fetchone()["count"]

    assert dict(base) == {"item_type": "standalone", "own": 1, "coll_id": 9001}
    assert dict(expansion) == {"item_type": "expansion", "own": 1, "coll_id": 9002}
    assert copies == 2


def test_collection_sync_due_state_uses_last_success(tmp_path: Path) -> None:
    db = database(tmp_path)
    client = BggCollectionClient(
        BggCollectionConfig(
            application_token="secret",
            username="tester",
            min_interval_seconds=0,
        ),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=EXP_XML if request.url.params.get("subtype") == "boardgameexpansion" else BASE_XML,
                    request=request,
                )
            )
        ),
    )
    service = BggCollectionSyncService(db, client, interval_seconds=6 * 60 * 60)

    now = datetime.now(UTC)
    assert service.status(now=now)["due"] is True
    service.sync(force=True)
    assert service.status(now=now + timedelta(hours=1))["due"] is False
    assert service.status(now=now + timedelta(hours=7))["due"] is True
