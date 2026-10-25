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
