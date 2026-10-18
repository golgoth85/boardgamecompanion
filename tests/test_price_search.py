from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.main import app
from boardgamecompanion.price_search import (
    GeminiPriceProvider,
    PriceSearchError,
    best_offer,
)
from boardgamecompanion.settings import settings

EGYP = "https://egyp.it/lang-en/carte/226422-il-signore-degli-anelli--5425016928226.html"
DUNGEON = "https://www.dungeondice.it/20218-il-signore-degli-anelli-duel-for-middle-earth.html"


def _response(offers: list[dict], chunks: list[dict], *, fenced: bool = False) -> dict:
    text = json.dumps({"offers": offers})
    if fenced:
        text = f"```json\n{text}\n```"
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}]},
                "groundingMetadata": {"groundingChunks": chunks},
            }
        ]
    }


def _provider(payload: dict, status: int = 200) -> GeminiPriceProvider:
    client = httpx.Client(
        base_url="https://generativelanguage.googleapis.com",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload)),
    )
    return GeminiPriceProvider(
        base_url="https://generativelanguage.googleapis.com",
        api_key="k",
        client=client,
        sleep=lambda _: None,
    )


def test_keeps_only_grounded_allowlisted_sane_offers() -> None:
    payload = _response(
        [
            {"url": DUNGEON, "price_eur": 29.99, "availability": "in_stock"},
            {"url": EGYP, "price_eur": 26.9, "availability": "in_stock"},
            {"url": "https://evil.example/x", "price_eur": 1, "availability": "in_stock"},
            {"url": "https://www.amazon.it/dp/B0", "price_eur": 20.99, "availability": "in_stock"},
            {"url": "https://www.dragonstore.it/p", "price_eur": 2000, "availability": "in_stock"},
            {"url": "http://www.toyscenter.it/p", "price_eur": 25, "availability": "in_stock"},
        ],
        [
            {"web": {"uri": EGYP, "title": "egyp.it"}},
            {"web": {"uri": "https://vertexaisearch.example/redirect/1", "title": "dungeondice.it"}},
            {"web": {"uri": "https://www.dragonstore.it/p", "title": "dragonstore.it"}},
            {"web": {"uri": "http://www.toyscenter.it/p", "title": "toyscenter.it"}},
        ],
        fenced=True,
    )
    offers = _provider(payload).search(title="Duel for Middle-earth", year=2024)
    assert [(o["shop"], o["price_eur"]) for o in offers] == [
        ("egyp.it", 26.9),
        ("dungeondice.it", 29.99),
    ]


def test_best_offer_skips_out_of_stock() -> None:
    offers = [
        {"shop": "a", "url": "u1", "price_eur": 10.0, "availability": "out_of_stock"},
        {"shop": "b", "url": "u2", "price_eur": 12.0, "availability": "unknown"},
    ]
    assert best_offer(offers)["shop"] == "b"
    assert best_offer(offers[:1]) is None


def test_invalid_output_and_http_errors_raise() -> None:
    bad = {"candidates": [{"content": {"parts": [{"text": "non json"}]}}]}
    with pytest.raises(PriceSearchError):
        _provider(bad).search(title="X")
    with pytest.raises(PriceSearchError):
        _provider({}, status=500).search(title="X")


def test_quota_error_reports_diagnostic_without_retry() -> None:
    calls: list[int] = []
    error = {
        "error": {
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [{"quotaId": "GroundingRequestsPerDay", "quotaValue": "0"}],
                }
            ],
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, json=error)

    provider = GeminiPriceProvider(
        base_url="https://generativelanguage.googleapis.com",
        api_key="k",
        client=httpx.Client(
            base_url="https://generativelanguage.googleapis.com",
            transport=httpx.MockTransport(handler),
        ),
        sleep=lambda _: None,
    )
    with pytest.raises(PriceSearchError, match="GroundingRequestsPerDay"):
        provider.search(title="X")
    assert len(calls) == 1


def test_error_message_is_included_in_failure() -> None:
    payload = {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded, limit: 0"}}
    with pytest.raises(PriceSearchError, match="limit: 0"):
        _provider(payload, status=429).search(title="X")


class _FakeProvider:
    def __init__(self, offers=None, error: Exception | None = None) -> None:
        self.offers = offers or []
        self.error = error

    def search(self, *, title: str, year: int | None = None):
        if self.error:
            raise self.error
        return self.offers


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    return TestClient(app)


def _add_item(client: TestClient) -> str:
    response = client.post(
        "/api/wishlist",
        json={"source_kind": "bgg", "source_key": "1", "title": "Duel", "bgg_id": 1},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_wishlist_price_refresh_endpoint(monkeypatch, tmp_path: Path) -> None:
    offers = [{"shop": "egyp.it", "url": EGYP, "price_eur": 26.9, "availability": "in_stock"}]
    with _client(monkeypatch, tmp_path) as client:
        item_id = _add_item(client)
        path = f"/api/wishlist/{item_id}/prices"

        monkeypatch.setattr(
            "boardgamecompanion.routers.wishlist.get_price_provider", lambda: None
        )
        assert client.post(path).status_code == 409

        monkeypatch.setattr(
            "boardgamecompanion.routers.wishlist.get_price_provider",
            lambda: _FakeProvider(error=PriceSearchError("boom")),
        )
        assert client.post(path).status_code == 502

        monkeypatch.setattr(
            "boardgamecompanion.routers.wishlist.get_price_provider",
            lambda: _FakeProvider(offers),
        )
        body = client.post(path).json()
        assert body["metadata"]["prices"]["best"]["price_eur"] == 26.9
        assert body["metadata"]["prices"]["checked_at"]
        assert client.get("/api/wishlist").json()["items"][0]["metadata"]["prices"]["offers"] == offers

        assert client.post("/api/wishlist/missing/prices").status_code == 404
