import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.bgg_csv import BggCsvImporter
from boardgamecompanion.bgg_reference import (
    BggReferenceCatalog,
    BggReferenceError,
    BggReferenceImporter,
    ReferenceSettings,
    clear_browse_cache,
    load_reference_settings,
    parse_ranks_dump,
    save_reference_settings,
)
from boardgamecompanion.database import Database
from boardgamecompanion.main import app
from boardgamecompanion.settings import settings

HEADER = (
    "id,name,yearpublished,rank,bayesaverage,average,usersrated,is_expansion,"
    "abstracts_rank,cgs_rank,childrensgames_rank,familygames_rank,partygames_rank,"
    "strategygames_rank,thematic_rank,wargames_rank\n"
)
DUMP = (
    HEADER
    + '224517,"Brass: Birmingham",2018,1,8.39048,8.5586,60686,0,,,,,,1,,\n'
    + "28720,Brass,2007,250,7.3,7.5,15000,0,,,,,,200,,\n"
    + '900100,"Brass: Birmingham – Promo",2019,0,0,7.1,40,1,,,,,,,,\n'
    + "900200,Café Obscure,0,0,0,6.0,150,0,,,,,,,,\n"
    + ",Missing Id,2020,0,0,0,10,0,,,,,,,,\n"
    + "28720,Brass duplicate,2007,0,0,0,10,0,,,,,,,,\n"
    + "900300,Bad Flag,2020,0,0,0,10,x,,,,,,,,\n"
).encode("utf-8")
COLLECTION_FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


@pytest.fixture(autouse=True)
def _fresh_browse_cache():
    clear_browse_cache()
    yield
    clear_browse_cache()


@pytest.fixture()
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    return database


def test_parse_rejects_malformed_rows_and_duplicates() -> None:
    rows, rejected = parse_ranks_dump(DUMP)

    assert [row.bgg_id for row in rows] == [224517, 28720, 900100, 900200]
    assert rejected == 3
    brass = rows[0]
    assert brass.name == "Brass: Birmingham"
    assert brass.rank == 1
    assert brass.users_rated == 60686
    assert rows[2].is_expansion == 1
    assert rows[2].rank is None
    assert rows[3].year_published is None


def test_parse_requires_dump_columns() -> None:
    with pytest.raises(BggReferenceError, match="Missing required dump columns"):
        parse_ranks_dump(b"objectid,objectname\n1,Foo\n")
    with pytest.raises(BggReferenceError, match="no valid rows"):
        parse_ranks_dump(HEADER.encode())


def test_import_is_idempotent_and_does_not_touch_board_games(database: Database) -> None:
    importer = BggReferenceImporter(database)

    first = importer.import_bytes(DUMP, "boardgames_ranks.csv")
    second = importer.import_bytes(DUMP, "boardgames_ranks.csv")

    assert (first.created_count, first.updated_count, first.unchanged_count) == (4, 0, 0)
    assert first.rejected_count == 3
    assert (second.created_count, second.updated_count, second.unchanged_count) == (0, 0, 4)
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM board_games").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM import_runs WHERE source_type = 'bgg_ranks_dump'"
        ).fetchone()[0] == 2


def test_import_updates_dump_rows_but_preserves_api_rows(database: Database) -> None:
    importer = BggReferenceImporter(database)
    importer.import_bytes(DUMP, "boardgames_ranks.csv")
    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE bgg_reference_games
            SET users_rated = 99999, source = 'api', api_checked_at = '2026-10-24T00:00:00+00:00'
            WHERE bgg_id = 224517
            """
        )

    newer = DUMP.replace(b"15000,0", b"15500,0").replace(b"60686,0", b"61000,0")
    result = importer.import_bytes(newer, "boardgames_ranks.csv")

    assert result.updated_count == 1
    with database.connect() as connection:
        votes = dict(
            connection.execute("SELECT bgg_id, users_rated FROM bgg_reference_games").fetchall()
        )
    assert votes[28720] == 15500
    assert votes[224517] == 99999


def test_search_applies_vote_threshold_and_expansion_setting(database: Database) -> None:
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    catalog = BggReferenceCatalog(database)

    default = catalog.search("brass")
    assert [item["bgg_id"] for item in default] == [28720, 224517]

    low = ReferenceSettings(min_votes=10)
    assert [item["bgg_id"] for item in catalog.search("brass", reference_settings=low)] == [
        28720,
        224517,
        900100,
    ]
    no_expansions = ReferenceSettings(min_votes=10, include_expansions=False)
    assert 900100 not in {
        item["bgg_id"] for item in catalog.search("brass", reference_settings=no_expansions)
    }


def test_browse_paginates_sorts_and_filters_visible_titles(database: Database) -> None:
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    catalog = BggReferenceCatalog(database)

    ranked = catalog.browse()
    assert ranked["total"] == 3
    assert [item["bgg_id"] for item in ranked["items"]] == [224517, 28720, 900200]

    page = catalog.browse(sort="title", limit=1, offset=1)
    assert (page["total"], [item["bgg_id"] for item in page["items"]]) == (3, [224517])
    assert [item["bgg_id"] for item in catalog.browse(sort="newest")["items"]] == [
        224517,
        28720,
        900200,
    ]
    assert [item["bgg_id"] for item in catalog.browse(sort="votes")["items"]][0] == 224517

    filtered = catalog.browse(query="brass", sort="votes")
    assert (filtered["total"], [item["bgg_id"] for item in filtered["items"]]) == (2, [224517, 28720])
    assert catalog.browse(query='"*')["total"] == 0
    assert catalog.browse(sort="unknown")["sort"] == "rank"


def test_browse_caches_the_visible_scan_but_keeps_library_flags_fresh(database: Database) -> None:
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    catalog = BggReferenceCatalog(database)
    assert catalog.browse()["items"][1]["in_catalog"] is False

    with database.transaction() as connection:
        connection.execute("UPDATE bgg_reference_games SET removed_at = 'x' WHERE bgg_id = 900200")
    catalog.add_to_collection(28720)

    cached = catalog.browse()
    assert cached["total"] == 3  # visibility comes from the cached scan
    assert cached["items"][1]["in_catalog"] is True
    assert [item["bgg_id"] for item in cached["items"]] == [224517, 28720]
    assert catalog.browse(reference_settings=ReferenceSettings(min_votes=10))["total"] == 3


def test_browse_filters_by_type_and_returns_card_facts(database: Database) -> None:
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE bgg_reference_games
            SET details_json = '{"min_players": 2, "max_players": 4, "playing_time": 120,
                                 "bgg_average_weight": 3.9, "bgg_recommended_age": "14"}'
            WHERE bgg_id = 224517
            """
        )
    catalog = BggReferenceCatalog(database)
    catalog.add_to_collection(28720)
    low = ReferenceSettings(min_votes=10)

    expansions = catalog.browse(item_type="expansion", reference_settings=low)
    assert [item["bgg_id"] for item in expansions["items"]] == [900100]
    searched = catalog.browse(query="brass", item_type="standalone", reference_settings=low)
    assert {item["bgg_id"] for item in searched["items"]} == {224517, 28720}

    items = {item["bgg_id"]: item for item in catalog.browse(item_type="standalone")["items"]}
    assert items[224517]["players"] == {"min": 2, "max": 4}
    assert items[224517]["play_time"]["playing"] == 120
    assert (items[224517]["average_weight"], items[224517]["recommended_age"]) == (3.9, "14")
    assert (items[224517]["owned"], items[28720]["owned"]) == (False, True)
    assert catalog.detail(28720)["owned"] is True


def test_assistant_candidates_skip_owned_titles_and_expansions(database: Database) -> None:
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    catalog = BggReferenceCatalog(database)
    catalog.add_to_collection(28720)

    candidates = catalog.assistant_candidates(reference_settings=ReferenceSettings(min_votes=10))
    assert [item["bgg_id"] for item in candidates] == [224517, 900200]
    assert candidates[0]["owned"] is False and candidates[0]["players"] == {"min": None, "max": None}


def test_search_prefix_diacritics_and_exact_title_first(database: Database) -> None:
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    catalog = BggReferenceCatalog(database)

    assert [item["bgg_id"] for item in catalog.search("cafe obs")] == [900200]
    assert [item["bgg_id"] for item in catalog.search("birmingham")] == [224517]
    assert catalog.search("bir")[0]["bgg_id"] == 224517
    assert catalog.search('"*') == []


def test_signal_admission_expires(database: Database) -> None:
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    catalog = BggReferenceCatalog(database)
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE bgg_reference_games
            SET admission_reason = 'crowdfunding', admission_until = ?
            WHERE bgg_id = 900100
            """,
            (future,),
        )
    found = catalog.search("promo")
    assert [item["admission_reason"] for item in found] == ["crowdfunding"]

    with database.transaction() as connection:
        connection.execute(
            "UPDATE bgg_reference_games SET admission_until = ? WHERE bgg_id = 900100",
            (past,),
        )
    assert catalog.search("promo") == []


def test_search_marks_titles_already_in_catalog(database: Database) -> None:
    BggCsvImporter(database).import_path(COLLECTION_FIXTURE)
    with database.connect() as connection:
        owned = connection.execute("SELECT bgg_id, title FROM board_games LIMIT 1").fetchone()
    payload = (HEADER + f'{owned["bgg_id"]},"{owned["title"]}",2020,0,0,7,500,0,,,,,,,,\n').encode()
    BggReferenceImporter(database).import_bytes(payload, "boardgames_ranks.csv")

    found = BggReferenceCatalog(database).search(owned["title"])

    assert found[0]["in_catalog"] is True


def test_settings_roundtrip_and_validation(database: Database) -> None:
    assert load_reference_settings(database) == ReferenceSettings(min_votes=100)
    saved = save_reference_settings(database, ReferenceSettings(min_votes=250, include_expansions=False))
    assert saved == ReferenceSettings(min_votes=250, include_expansions=False)
    with pytest.raises(BggReferenceError):
        save_reference_settings(database, ReferenceSettings(min_votes=-1))


def test_dump_in_import_folder_is_imported_once(database: Database, tmp_path: Path) -> None:
    import_dir = tmp_path / "import"
    import_dir.mkdir()
    importer = BggReferenceImporter(database)

    assert importer.import_if_changed(import_dir) is None

    dump = import_dir / "boardgames_ranks.csv"
    dump.write_bytes(DUMP)
    first = importer.import_if_changed(import_dir)
    assert first is not None and first.created_count == 4
    assert importer.import_if_changed(import_dir) is None

    # Same content rewritten (new mtime): hashed again but not reimported.
    dump.write_bytes(DUMP)
    os.utime(dump, ns=(1, 1))
    assert importer.import_if_changed(import_dir) is None

    dump.write_bytes(DUMP.replace(b"15000,0", b"15500,0"))
    second = importer.import_if_changed(import_dir)
    assert second is not None and second.updated_count == 1
    assert dump.exists()
    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM import_runs WHERE source_type = 'bgg_ranks_dump'"
        ).fetchone()[0] == 2


def test_reference_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "bgg_reference_dump_worker_enabled", False)
    monkeypatch.setattr(settings, "bgg_reference_api_worker_enabled", False)
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"
    settings.import_dir.mkdir(parents=True)
    (settings.import_dir / "boardgames_ranks.csv").write_bytes(DUMP)

    with TestClient(app) as client:
        assert client.post("/api/reference/import-dump", json={"filename": "../x.csv"}).status_code == 400
        assert client.post("/api/reference/import-dump", json={"filename": "nope.csv"}).status_code == 404

        imported = client.post("/api/reference/import-dump")
        assert imported.status_code == 200
        assert imported.json()["created_count"] == 4

        status = client.get("/api/reference/status").json()
        assert (status["total"], status["visible"]) == (4, 3)
        assert status["last_dump_import"]["row_count"] == 4

        assert client.put("/api/reference/settings", json={"min_votes": -1}).status_code == 422
        assert client.put("/api/reference/settings", json={"min_votes": 1, "daily_budget": 5001}).status_code == 422
        assert client.get("/api/reference/status").json()["worker"]["budget_used"] == 0
        updated = client.put("/api/reference/settings", json={"min_votes": 50000})
        assert updated.json()["min_votes"] == 50000
        assert client.get("/api/reference/status").json()["visible"] == 1
        everything = client.put("/api/reference/settings", json={"min_votes": 0})
        assert everything.json()["min_votes"] == 0
        assert client.get("/api/reference/status").json()["visible"] == 4
        client.put("/api/reference/settings", json={"min_votes": 100})

        assert client.post("/api/reference/777/collection").status_code == 404
        assert client.get("/api/reference/settings").status_code == 200
        assert client.get("/api/reference/777").status_code == 404
        offline = client.get("/api/reference/28720").json()
        assert offline["name"] == "Brass" and offline["detail_error"] == "no_token"
        added = client.post("/api/reference/28720/collection")
        assert added.status_code == 201
        assert added.json()["created_game"] and added.json()["created_entry"]
        again = client.post("/api/reference/28720/collection").json()
        assert not again["created_game"] and not again["created_entry"]
        flagged = client.get("/api/reference/search", params={"q": "brass"}).json()["items"]
        assert {i["bgg_id"]: i["in_catalog"] for i in flagged} == {28720: True, 224517: False}

        browse = client.get("/api/reference/browse", params={"sort": "votes", "limit": 2}).json()
        assert browse["total"] == 3
        assert [(i["bgg_id"], i["in_catalog"]) for i in browse["items"]] == [(224517, False), (28720, True)]
        assert all("image_url" in i for i in browse["items"])
        assert client.get("/api/reference/browse", params={"sort": "nope"}).status_code == 422

        search = client.get("/api/reference/search", params={"q": "brass"}).json()
        assert [item["bgg_id"] for item in search["items"]] == [28720, 224517]


def test_startup_imports_dump_without_user_action(tmp_path: Path) -> None:
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"
    settings.import_dir.mkdir(parents=True)
    (settings.import_dir / "boardgames_ranks.csv").write_bytes(DUMP)

    with TestClient(app) as client:
        deadline = time.monotonic() + 10
        status = client.get("/api/reference/status").json()
        while status["total"] == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
            status = client.get("/api/reference/status").json()

    assert status["total"] == 4
    assert status["last_dump_import"]["source_filename"] == "boardgames_ranks.csv"


def test_import_in_small_batches_keeps_counts(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("boardgamecompanion.bgg_reference.IMPORT_BATCH_SIZE", 3)
    importer = BggReferenceImporter(database)

    first = importer.import_bytes(DUMP, "boardgames_ranks.csv")
    second = importer.import_bytes(DUMP.replace(b"150,0", b"151,0"), "boardgames_ranks.csv")

    assert (first.created_count, first.updated_count) == (4, 0)
    assert (second.created_count, second.updated_count, second.unchanged_count) == (0, 1, 3)


class FakeThingClient:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def thing_with_xml(self, bgg_id: int) -> tuple[dict, str]:
        self.calls.append(bgg_id)
        return self._metadata(bgg_id), '<item id="28720"><poll name="x"/></item>'

    def _metadata(self, bgg_id: int) -> dict:
        return {
            "bgg_id": bgg_id,
            "title": "Brass",
            "alternate_titles": ["Brass: Imperio del Carbone", "Castelli Fittizi"],
            "description": "Una descrizione.",
            "cover_url": "https://cf.geekdo-images.com/x.jpg",
            "thumbnail_url": "https://cf.geekdo-images.com/t.jpg",
            "bgg_rank": 100,
            "bgg_average": 7.9,
            "bgg_bayes_average": 7.6,
            "bgg_users_rated": 16000,
            "bgg_wishing": 321,
            "bgg_num_owned": 20000,
        }


def test_detail_fetches_once_and_indexes_alternate_titles(database: Database) -> None:
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    catalog = BggReferenceCatalog(database)
    assert catalog.search("castelli fittizi") == []

    offline = catalog.detail(28720, None)
    assert offline["detail_error"] == "no_token" and offline["description"] is None
    assert catalog.detail(777, None) is None

    client = FakeThingClient()
    first = catalog.detail(28720, client)
    assert first["description"] == "Una descrizione."
    assert first["alternate_names"] == ["Brass: Imperio del Carbone", "Castelli Fittizi"]
    assert first["wishing"] == 321 and first["users_rated"] == 16000
    catalog.detail(28720, client)
    assert client.calls == [28720]
    assert "raw_xml" not in first["details"]
    with database.connect() as connection:
        stored = connection.execute("SELECT details_json FROM bgg_reference_games WHERE bgg_id=28720").fetchone()[0]
    assert '<poll name=\\"x\\"/>' in stored or '<poll name="x"/>' in stored

    assert [i["bgg_id"] for i in catalog.search("castelli fittizi")] == [28720]
    # a later dump import must not overwrite API data
    BggReferenceImporter(database).import_bytes(DUMP + b"", "again.csv")
    assert catalog.detail(28720, None)["description"] == "Una descrizione."


def test_detail_provider_failure_keeps_dump_data(database: Database) -> None:
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")

    class Broken:
        def thing_with_xml(self, bgg_id: int) -> tuple[dict, str]:
            raise RuntimeError("boom")

    item = BggReferenceCatalog(database).detail(28720, Broken())
    assert item["name"] == "Brass" and "boom" in item["detail_error"]
    assert item["api_checked_at"] is None


def test_explore_and_rankings_sources_groups_and_language(database: Database) -> None:
    import json

    from boardgamecompanion.catalog import Catalog

    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    poll = (
        '<poll name="language_dependence" title="Language Dependence" totalvotes="9">'
        '<results><result level="1" value="No necessary in-game text" numvotes="2"/>'
        '<result level="2" value="Some necessary text - easily memorized" numvotes="7"/>'
        "</results></poll>"
    )
    details = {
        224517: {
            "min_players": 2, "max_players": 4, "bgg_average_weight": 3.9,
            "categories": ["Economic", "Industry / Manufacturing"],
            "mechanics": ["Hand Management", "Network and Route Building"],
            "raw_xml": f"<items><item>{poll}</item></items>",
        },
        900200: {
            "min_players": 1, "max_players": 6,
            "categories": ["Party Game"], "mechanics": ["Some Brand New Auction"],
            "bgg_language_dependence": "Extensive use of text",
        },
        28720: {"categories": ["Economic"], "mechanics": ["Hand Management"]},
    }
    with database.transaction() as connection:
        for bgg_id, value in details.items():
            connection.execute(
                "UPDATE bgg_reference_games SET details_json=? WHERE bgg_id=?",
                (json.dumps(value), bgg_id),
            )
    BggReferenceCatalog(database).add_to_collection(28720)
    with database.transaction() as connection:
        board_game_id = connection.execute(
            "SELECT id FROM board_games WHERE bgg_id=28720"
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO board_game_enrichments(board_game_id,source,external_id,title,
               metadata_json,next_refresh_at,created_at,updated_at)
               VALUES(?,'test','28720','Brass',?,'2099-01-01','2026-01-01','2026-01-01')""",
            (board_game_id, json.dumps(details[28720])),
        )

    rows = BggReferenceCatalog(database).explore_rows(ReferenceSettings(min_votes=10))
    by_id = {row["bgg_id"]: row for row in rows}
    assert 900100 not in by_id  # expansions are not explored
    assert by_id[224517]["bgg_language_dependence"].startswith("Some necessary")
    assert by_id[900200]["bgg_language_dependence"] == "Extensive use of text"

    catalog = Catalog(database)
    explore = lambda **kwargs: catalog.explore(reference_rows=rows, **kwargs)  # noqa: E731

    library = explore()
    assert [game["bgg_id"] for game in library["games"]] == [28720]
    assert library["games"][0]["source"] == "library"

    only_catalog = explore(source="catalog")
    assert {game["bgg_id"] for game in only_catalog["games"]} == {224517, 900200}
    assert all(game["source"] == "catalog" for game in only_catalog["games"])

    both = explore(source="both", category_groups=["economy"])
    assert {game["bgg_id"] for game in both["games"]} == {224517, 28720}
    economy = next(group for group in both["category_groups"] if group["key"] == "economy")
    assert economy == {"key": "economy", "label": "Economia e costruzione", "count": 2, "selected": True}
    groups = {item["name"]: item["group"] for item in both["mechanics"]}
    assert groups["Network and Route Building"] == "map"

    auction = explore(source="catalog", mechanic_groups=["social"])
    assert [game["bgg_id"] for game in auction["games"]] == [900200]

    light_text = explore(source="both", max_language=2)
    assert [game["bgg_id"] for game in light_text["games"]] == [224517]
    labels = {item["label"]: item["count"] for item in light_text["options"]["max_language"]}
    assert labels == {"Poca": 1, "Moderata": 1}

    # 900200 has no Bayesian average in the dump: give it one, unranked titles are excluded.
    ranked_rows = [{**row, "bgg_bayes_average": row["bgg_bayes_average"] or 6.0} for row in rows]
    rank = lambda **kwargs: catalog.rankings(reference_rows=ranked_rows, **kwargs)  # noqa: E731
    assert [item["game"]["bgg_id"] for item in rank()["items"]] == [28720]
    both_ranked = rank(source="both")
    assert {item["game"]["bgg_id"] for item in both_ranked["items"]} == {224517, 28720, 900200}
    assert {item["game"]["source"] for item in both_ranked["items"]} == {"library", "catalog"}
    economy_ranked = rank(source="catalog", category_groups=["economy"])
    assert [item["game"]["bgg_id"] for item in economy_ranked["items"]] == [224517]
    # Group counts ignore the group filter itself, so alternatives stay visible.
    party = next(group for group in economy_ranked["category_groups"] if group["key"] == "party")
    assert party["count"] == 1
    language_ranked = rank(source="both", max_language=2)
    assert [item["game"]["bgg_id"] for item in language_ranked["items"]] == [224517]
    assert {item["label"]: item["count"] for item in language_ranked["options"]["max_language"]} == {
        "Poca": 1, "Moderata": 1,
    }
    assert rank(source="catalog", mode="personal_favorites")["items"] == []
    assert 900200 not in {
        item["game"]["bgg_id"]
        for item in catalog.rankings(reference_rows=rows, source="catalog")["items"]
    }
