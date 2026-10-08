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
 <name type='alternate' value='7 Wonders Duello'/>
 <yearpublished value='2015'/>
 <minplayers value='2'/><maxplayers value='2'/>
 <playingtime value='30'/><minplaytime value='30'/><maxplaytime value='30'/>
 <minage value='10'/>
 <poll name='suggested_numplayers'>
   <results numplayers='2'>
     <result value='Best' numvotes='100'/>
     <result value='Recommended' numvotes='20'/>
     <result value='Not Recommended' numvotes='1'/>
   </results>
 </poll>
 <poll name='suggested_playerage'>
   <results>
     <result value='10' numvotes='5'/>
     <result value='8' numvotes='25'/>
   </results>
 </poll>
 <statistics><ratings>
   <average value='8.1'/><bayesaverage value='7.9'/><averageweight value='2.2'/><owned value='50000'/>
   <ranks><rank name='boardgame' value='15'/></ranks>
 </ratings></statistics>
 <image>https://cf.geekdo-images.com/cover.jpg</image>
 <description>A &amp; B</description>
 <link type='boardgamepublisher' value='Repos Production'/>
 <link type='boardgamedesigner' value='Antoine Bauza'/>
 <link type='boardgamecategory' value='Ancient'/>
 <link type='boardgameexpansion' id='202976' value='7 Wonders Duel: Pantheon'/>
 <link type='boardgameexpansion' id='236435' value='7 Wonders Duel: Agora'/>
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
        "url": "https://boardgamegeek.com/xmlapi2/thing?id=173346&stats=1",
    }
    assert item["external_id"] == "173346"
    assert item["cover_url"] == "https://cf.geekdo-images.com/cover.jpg"
    assert item["publishers"] == ["Repos Production"]
    assert item["metadata"]["bgg_id"] == 173346
    assert item["metadata"]["alternate_titles"] == [
        "7 Wonders: Duel",
        "7 Wonders Duello",
    ]
    assert item["metadata"]["expansions"] == [
        {"bgg_id": 202976, "title": "7 Wonders Duel: Pantheon"},
        {"bgg_id": 236435, "title": "7 Wonders Duel: Agora"},
    ]
    # Official minage wins over the community suggested_playerage poll.
    assert item["metadata"]["bgg_recommended_age"] == "10"
    with store.database.connect() as connection:
        game = connection.execute(
            "SELECT min_players,max_players,bgg_average_weight,bgg_rank,bgg_best_players,bgg_recommended_age FROM board_games WHERE bgg_id=173346"
        ).fetchone()
    assert dict(game) == {
        "min_players": 2,
        "max_players": 2,
        "bgg_average_weight": 2.2,
        "bgg_rank": 15,
        "bgg_best_players": "2",
        "bgg_recommended_age": "10",
    }


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


def test_bgg_202_is_retried_with_bounded_retry_after() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(202, headers={"retry-after": "2"}, request=request)
        return httpx.Response(200, content=XML, request=request)

    client = BggApiClient(
        BggApiConfig("secret", min_interval_seconds=0, max_attempts=2),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
    )
    assert client.thing(173346)["bgg_id"] == 173346
    assert calls == 2 and sleeps == [2.0]


def test_bgg_streaming_byte_limit_is_enforced_before_parse() -> None:
    client = BggApiClient(
        BggApiConfig("secret", min_interval_seconds=0, max_attempts=1),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1), request=request)
        )),
    )
    with pytest.raises(BggMetadataError, match="byte limit"):
        client.thing(173346)


def test_bgg_rejects_content_encoding_before_decoding() -> None:
    client = BggApiClient(
        BggApiConfig("secret", min_interval_seconds=0, max_attempts=1),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-encoding": "gzip"},
                stream=httpx.ByteStream(b"compressed"),
                request=request,
            )
        )),
    )
    with pytest.raises(BggMetadataError, match="encoding"):
        client.thing(173346)


HOT_XML = b"""<?xml version='1.0'?>
<items total='2' termsofuse='https://boardgamegeek.com/xmlapi/termsofuse'>
  <item id='999001' rank='1'>
    <name value='Candidate One'/>
    <yearpublished value='2025'/>
  </item>
  <item id='999002' rank='2'>
    <name value='Candidate Two'/>
    <yearpublished value='2024'/>
  </item>
</items>"""


def test_bgg_hot_list_is_bearer_authenticated_and_bounded() -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers["authorization"]
        observed["url"] = str(request.url)
        return httpx.Response(200, content=HOT_XML, request=request)

    client = BggApiClient(
        BggApiConfig("secret", min_interval_seconds=0),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.hot(limit=1) == [
        {
            "bgg_id": 999001,
            "title": "Candidate One",
            "year_published": 2025,
            "hot_rank": 1,
        }
    ]
    assert observed == {
        "authorization": "Bearer secret",
        "url": "https://boardgamegeek.com/xmlapi2/hot?type=boardgame",
    }
