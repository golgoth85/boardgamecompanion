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


def test_cover_endpoint_prefers_variant_and_falls_back(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from boardgamecompanion.main import app
    from boardgamecompanion.routers import covers as router

    urls = {"full": "https://cf.geekdo-images.com/full.jpg", "thumb": "https://cf.geekdo-images.com/t.jpg"}
    monkeypatch.setattr(router, "_cover_url", lambda bgg_id, variant: urls[variant] if bgg_id == 5 else None)
    monkeypatch.setattr(router.settings, "covers_dir", tmp_path / "missing")
    client = TestClient(app)
    assert client.get("/api/covers/9").status_code == 404
    response = client.get("/api/covers/5?variant=thumb", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"] == urls["thumb"]
    assert client.get("/api/covers/5?variant=bad").status_code == 422
