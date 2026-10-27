import httpx

from boardgamecompanion import covers
from boardgamecompanion.covers import CoverStore

URL = "https://cf.geekdo-images.com/abc/pic1.jpg"


def test_url_allowlist():
    assert CoverStore.url_allowed(URL)
    assert not CoverStore.url_allowed("http://cf.geekdo-images.com/x.jpg")
    assert not CoverStore.url_allowed("https://geekdo-images.com.evil.test/x.jpg")


def test_missing_directory_is_never_created(tmp_path):
    store = CoverStore(tmp_path / "covers")
    assert store.fetch(1, URL) is None
    assert not (tmp_path / "covers").exists()


def test_fetch_stores_once_then_reuses(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})

    from contextlib import contextmanager

    @contextmanager
    def stream(method, url, **kwargs):
        yield handler(httpx.Request(method, url))

    monkeypatch.setattr(covers.httpx, "stream", stream)
    store = CoverStore(tmp_path)
    first = store.fetch(7, URL)
    second = store.fetch(7, URL)
    assert first == second and first.read_bytes() == b"img"
    assert len(calls) == 1


def test_cover_endpoint_serves_one_cover_per_game(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from boardgamecompanion.main import app
    from boardgamecompanion.routers import covers as router

    full = "https://cf.geekdo-images.com/full.jpg"
    monkeypatch.setattr(router, "_cover_url", lambda bgg_id: full if bgg_id == 5 else None)
    monkeypatch.setattr(router.settings, "covers_dir", tmp_path / "missing")
    client = TestClient(app)
    assert client.get("/api/covers/9").status_code == 404
    for path in ("/api/covers/5", "/api/covers/5?variant=thumb", "/api/covers/5?src=https://cf.geekdo-images.com/other.jpg"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 302 and response.headers["location"] == full
    assert client.get("/api/covers/5?variant=bad").status_code == 422
    # Unknown games fall back to a BGG image given by the caller, never to other hosts.
    fallback = client.get("/api/covers/9?src=https://cf.geekdo-images.com/s.jpg", follow_redirects=False)
    assert fallback.headers["location"] == "https://cf.geekdo-images.com/s.jpg"
    assert client.get("/api/covers/9?src=https://evil.test/s.jpg").status_code == 404


def test_canonical_cover_prefers_library_then_catalog_image(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from boardgamecompanion.database import Database
    from boardgamecompanion.routers import covers as router

    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    now = datetime.now(UTC).isoformat()
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO bgg_reference_games (bgg_id,name,thumbnail_url,image_url,source,created_at,updated_at)"
            " VALUES (1,'A','https://cf.geekdo-images.com/t1.jpg','https://cf.geekdo-images.com/i1.jpg','api',?,?),"
            " (2,'B','https://cf.geekdo-images.com/t2.jpg',NULL,'api',?,?)",
            (now, now, now, now),
        )
        game_id = connection.execute(
            "INSERT INTO board_games (bgg_id,title,source_metadata_json,created_at,updated_at)"
            " VALUES (1,'A','{}',?,?)",
            (now, now),
        ).lastrowid
        connection.execute(
            "INSERT INTO board_game_enrichments (board_game_id,source,external_id,title,cover_url,"
            "next_refresh_at,created_at,updated_at) VALUES (?,'bgg_xml_api2','1','A',"
            "'https://cf.geekdo-images.com/own1.jpg',?,?,?)",
            (game_id, now, now, now),
        )
    monkeypatch.setattr(router, "get_database", lambda: database)
    assert router._cover_url(1) == "https://cf.geekdo-images.com/own1.jpg"
    assert router._cover_url(2) == "https://cf.geekdo-images.com/t2.jpg"
    assert router._cover_url(3) is None
