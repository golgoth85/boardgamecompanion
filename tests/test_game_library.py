from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from runpy import run_path

from boardgamecompanion import migrations
from boardgamecompanion.bgg_csv import BggCsvImporter
from boardgamecompanion.bgg_reference import BggReferenceCatalog
from boardgamecompanion.catalog import Catalog
from boardgamecompanion.database import Database
from boardgamecompanion.documents import DocumentStore
from boardgamecompanion.game_lists import GameListStore
from boardgamecompanion.players import PlayerProfiles
from boardgamecompanion.plays import PlayLog
from boardgamecompanion.wishlist import WishlistStore


def test_upgrade_and_restore_realistic_schema_30(tmp_path, monkeypatch):
    database = Database(tmp_path / "previous.sqlite3")
    with monkeypatch.context() as previous:
        previous.setattr(migrations, "MIGRATIONS", migrations.MIGRATIONS[:30])
        database.initialize()

    with database.transaction() as connection:
        connection.executescript("""
            INSERT INTO board_games(id,bgg_id,title,created_at,updated_at) VALUES
              (1,101,'Gioco posseduto','before','before'),
              (2,102,'Gioco rimosso','before','before');
            INSERT INTO collection_entries(
                id,board_game_id,own,previously_owned,barcode,quantity,
                private_comment,source_metadata_json,first_seen_at,created_at,updated_at
            ) VALUES
              (1,1,0,0,NULL,NULL,NULL,'{}','before','before','before'),
              (2,1,1,0,'0900000000002',3,'Nota a livello di gioco',
               '{"barcode":"0900000000002","quantity":"3","privatecomment":"Nota a livello di gioco"}',
               'before','before','before'),
              (3,2,0,1,NULL,NULL,NULL,'{}','before','before','before');
            INSERT INTO physical_copies(
                id,board_game_id,source_collection_entry_id,source_copy_index,source_kind,
                barcode,barcode_normalized,notes,created_at,updated_at
            ) VALUES
              ('imported',1,2,1,'bgg_csv','0900000000002','0900000000002',NULL,'before','before'),
              ('edited',1,2,2,'bgg_csv','0900000000001','0900000000001','Nota privata','before','before'),
              ('manual',2,NULL,NULL,'manual','0900000000003','0900000000003',NULL,'before','before');
        """)
    player = PlayerProfiles(database).create({"name": "Anna"})
    play = PlayLog(database).create(102, {"played_on": "2026-10-01", "players": [{"name": "Anna"}]})
    store = DocumentStore(database, tmp_path / "manuals")
    doc, _ = store.import_pdf(
        bgg_id=102, original_filename="regolamento.pdf", stream=BytesIO(b"%PDF-1.7\n"),
        language="it", max_bytes=200,
    )
    lists = GameListStore(database)
    saved_list = lists.create(name="Domenica", kind="manual")
    lists.set_manual_item(saved_list["id"], 101, present=True)
    wish = WishlistStore(database).upsert(source_kind="bgg", source_key="102", title="Gioco rimosso", bgg_id=102)

    snapshot = tmp_path / "backups" / "pre-m31.sqlite3"
    operations = run_path(str(Path(__file__).parents[1] / "scripts" / "library_migration.py"))
    operations["apply"](database.path, snapshot)
    tables = ("board_games", "game_plays", "player_profiles", "game_documents", "saved_game_lists",
              "saved_game_list_items", "personal_wishlist", "game_progress")
    with Database(snapshot).connect() as original:
        assert original.execute("SELECT notes FROM physical_copies WHERE id='edited'").fetchone()[0] == "Nota privata"
        before = {table: original.execute(f"SELECT * FROM {table}").fetchall() for table in tables}

    database.initialize()
    catalog = Catalog(database)
    assert [game["bgg_id"] for game in catalog.list_games(owned=True)["items"]] == [101]
    assert catalog.stats()["owned"] == 1
    assert not catalog.get_game(102)["collection"]["own"]
    with database.connect() as current:
        assert current.execute("PRAGMA foreign_key_check").fetchall() == []
        assert current.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert {table: current.execute(f"SELECT * FROM {table}").fetchall() for table in tables} == before
        assert current.execute("SELECT 1 FROM sqlite_master WHERE name='physical_copies'").fetchone() is None
        assert current.execute("SELECT private_comment FROM collection_entries WHERE id=2").fetchone()[0] == "Nota a livello di gioco"
        assert [row[0] for row in current.execute("SELECT barcode FROM barcode_product_hints ORDER BY barcode")] == [
            "0900000000001", "0900000000003",
        ]
    assert PlayerProfiles(database).get(player["id"])["name"] == "Anna"
    assert PlayLog(database).get(play["id"])["played_on"] == "2026-10-01"
    assert store.get(doc["id"])["language"] == "it"
    assert WishlistStore(database).get(wish["id"])["bgg_id"] == 102

    operations["restore"](database.path, snapshot)
    with database.connect() as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 30
        assert connection.execute("SELECT COUNT(*) FROM physical_copies").fetchone()[0] == 3
        assert connection.execute("SELECT notes FROM physical_copies WHERE id='edited'").fetchone()[0] == "Nota privata"


def test_duplicate_csv_rows_and_parallel_reactivation_keep_one_owned_game(tmp_path):
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    importer = BggCsvImporter(database)
    payload = b"""objectid,objectname,collid,own,quantity,numplays
101,Gioco A,1,0,4,2
101,Gioco A,2,1,3,2
101,Gioco A,2,0,7,2
101,Gioco A,3,1,1,2
"""
    importer.import_bytes(payload, "library.csv")
    assert importer.import_bytes(payload, "library.csv").updated_count == 0

    catalog = Catalog(database)
    reference = BggReferenceCatalog(database)
    assert catalog.list_games(owned=True)["total"] == 1
    assert catalog.get_game(101)["collection"]["own"]
    log = PlayLog(database)
    play = log.create(101, {"played_on": "2026-10-01"})
    assert catalog.remove_from_library(101) == 2
    assert catalog.list_games(owned=True)["total"] == 0
    assert not catalog.get_game(101)["collection"]["own"]
    assert catalog.ownership([101, 999]) == {101: False}

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(reference.add_to_collection, [101] * 12))
    assert sum(result["created_entry"] for result in results) == 1
    assert catalog.list_games(owned=True)["total"] == 1
    assert catalog.ownership([101]) == {101: True}
    assert log.get(play["id"])["played_on"] == "2026-10-01"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM collection_entries").fetchone()[0] == 3


def test_tonight_checks_known_constraints_and_reports_missing_data(tmp_path):
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    BggCsvImporter(database).import_bytes(b"""objectid,objectname,own,itemtype,minplayers,maxplayers,minplaytime,maxplaytime,avgweight,bggbestplayers,bgglanguagedependence
1,Ideale,1,standalone,2,4,45,60,2.2,4,No necessary in-game text
2,Troppo lungo,1,standalone,2,4,60,90,2.2,4,No necessary in-game text
3,Scatola,1,standalone,2,4,30,60,2.2,,No necessary in-game text
4,Espansione,1,expansion,2,4,30,60,2.2,4,No necessary in-game text
5,Non posseduto,0,standalone,2,4,30,60,2.2,4,No necessary in-game text
6,Dati mancanti,1,standalone,,,,,,,
""", "library.csv")
    PlayLog(database).create(1, {"played_on": "2026-03-01"})
    catalog = Catalog(database)
    filters = {"players": 4, "minutes": 60, "weight": "light", "language": 1}
    result = catalog.tonight(**filters)
    assert [(game["bgg_id"], game["player_fit"], game["last_play"]) for game in result["items"]] == [
        (1, "ideal", "2026-03-01"), (3, "box", None),
    ]
    result = catalog.tonight(**{**filters, "minutes": 15})
    assert result["items"] == [] and "minutes" in result["relaxable"]
