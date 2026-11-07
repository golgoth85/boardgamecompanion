from __future__ import annotations

import json
from pathlib import Path

from boardgamecompanion.bgg_metadata import BggMetadataStore, _parse_versions
from boardgamecompanion.catalog import Catalog
from boardgamecompanion.database import Database
from boardgamecompanion.italian_titles import ItalianTitleService, choose_italian_title
from boardgamecompanion.title_search import display_title, is_edition_label, italian_title

XML = b"""<items><item type="boardgame" id="7"><versions>
<item><name type="primary" value="Creature e Reietti"/><link type="language" value="Italian"/></item>
<item><name type="primary" value="Creature e Reietti"/><link type="language" value="Italian"/></item>
<item><name type="primary" value="Italian edition"/><link type="language" value="Italian"/></item>
<item><name type="primary" value="Wesen und Ausgestossene"/><link type="language" value="German"/></item>
</versions></item></items>"""


def test_parse_versions_and_choose_italian_title() -> None:
    versions = _parse_versions(XML, expected_bgg_id=7)
    assert versions[0] == {"name": "Creature e Reietti", "languages": ["Italian"]}
    assert choose_italian_title(versions) == "Creature e Reietti"
    assert choose_italian_title([{"name": "Italian edition", "languages": ["Italian"]}]) is None
    assert choose_italian_title([{"name": "Das Spiel", "languages": ["German"]}]) is None


class _Client:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def versions(self, bgg_id: int):
        self.calls.append(bgg_id)
        return _parse_versions(XML, expected_bgg_id=7)


def _game(database: Database) -> None:
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO board_games(id,bgg_id,title,item_type,created_at,updated_at) "
            "VALUES (1,7,'Creatures and Outcasts','standalone','x','x')"
        )
        connection.execute(
            "INSERT INTO collection_entries(board_game_id,own,first_seen_at,created_at,updated_at) "
            "VALUES (1,1,'x','x','x')"
        )
        connection.execute(
            """INSERT INTO board_game_enrichments
               (board_game_id,source,external_id,title,publishers_json,categories_json,designers_json,
                metadata_json,fetched_at,next_refresh_at,created_at,updated_at)
               VALUES (1,'bgg_xml_api2','7','Creatures and Outcasts','[]','[]','[]','{}','x','x','x','x')"""
        )


def test_scan_stores_edition_title_once_and_catalog_shows_it(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.initialize()
    _game(database)
    client = _Client()
    service = ItalianTitleService(database, client)

    assert service.scan_due(limit=5) == {"checked": 1, "found": 1, "failed": 0}
    assert service.scan_due(limit=5) == {"checked": 0, "found": 0, "failed": 0}
    assert client.calls == [7]
    item = Catalog(database).list_games(owned=True)["items"][0]
    assert (item["title"], item["bgg_title"]) == ("Creature e Reietti", "Creatures and Outcasts")
    assert Catalog(database).list_games(query="creature e reietti")["total"] == 1


def test_metadata_refresh_keeps_collected_italian_title(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.initialize()
    _game(database)
    ItalianTitleService(database, _Client()).scan_due(limit=1)
    metadata = {
        "title": "Creatures and Outcasts", "original_title": None, "year_published": 2020,
        "cover_url": None, "description": None, "publishers": [], "categories": [], "designers": [],
    }
    from datetime import UTC, datetime

    BggMetadataStore(database, None)._persist_metadata(7, metadata, datetime.now(UTC))
    with database.connect() as connection:
        stored = json.loads(connection.execute("SELECT metadata_json FROM board_game_enrichments").fetchone()[0])
    assert stored["italian_title"] == "Creature e Reietti"


def test_edition_labels_are_not_titles() -> None:
    for label in (
        "Italian edition 2016", "Ghenos Games Italian edition", "Italian 2.0 edition",
        "Multilingual first edition", "DUT/ENG/FRE/GER/ITA/SPA edition", "Italian sundrop edition",
    ):
        assert is_edition_label(label), label
        assert choose_italian_title([{"name": label, "languages": ["Italian"]}]) is None
    for title in (
        "Il Trono di Spade: il Gioco di Carte (Seconda edizione)", "Mercoledì: Creature e Reietti",
        "Arkham Horror: Il Gioco di Carte", "Chronicles of Crime: 2400",
    ):
        assert not is_edition_label(title), title
    assert not is_edition_label("Italian Job 2012", ["The Italian Job 2012", "Italian Job 2012"])


def test_stored_edition_label_is_hidden_and_rescanned(tmp_path: Path) -> None:
    database = Database(tmp_path / "db.sqlite3")
    database.initialize()
    _game(database)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE board_game_enrichments SET metadata_json=?",
            (json.dumps({"italian_title": "Italian edition 2016", "italian_title_next_check_at": "9999"}),),
        )
    assert display_title("Creatures and Outcasts", {"italian_title": "Italian edition 2016"}) == (
        "Creatures and Outcasts"
    )
    assert Catalog(database).list_games(owned=True)["items"][0]["title"] == "Creatures and Outcasts"
    service = ItalianTitleService(database, _Client())
    assert service.due_ids(limit=5) == [7]
    service.scan_due(limit=5)
    assert service.due_ids(limit=5) == []
    assert Catalog(database).list_games(owned=True)["items"][0]["title"] == "Creature e Reietti"


def test_alternate_with_non_italian_accents_is_not_italian() -> None:
    assert italian_title(
        "Chronicles of Crime: 2400", ["Crónicas del Crimen: La Saga Millenium – 2400"]
    ) == "Chronicles of Crime: 2400"
    assert italian_title("Wednesday", ["Mercoledì: Creature e Reietti"]) == "Mercoledì: Creature e Reietti"
