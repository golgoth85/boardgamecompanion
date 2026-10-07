from __future__ import annotations

import json

import httpx

from boardgamecompanion.bgg_rulebook_search import (
    BGG_GROUNDING_MODEL,
    GeminiBggFileProvider,
)
from boardgamecompanion.rulebooks import RulebookQuery, RulebookSource


def test_bgg_grounding_model_stays_free_tier_compatible():
    assert BGG_GROUNDING_MODEL == "gemini-3.5-flash-lite"


def query() -> RulebookQuery:
    return RulebookQuery(
        bgg_id=221965,
        title="The Fox in the Forest",
        original_title="The Fox in the Forest",
        year=2017,
        item_type="boardgame",
        publishers=("Renegade Game Studios",),
        verified_publishers=("Renegade Game Studios",),
        verified_titles=("The Fox in the Forest",),
        bgg_identity_verified=True,
    )


def response_payload(*, source_url: str, download_url: str, grounded_download: str | None = None):
    text = json.dumps(
        {
            "items": [
                {
                    "source_url": source_url,
                    "download_url": download_url,
                    "language": "en",
                    "title": "Official English Rulebook",
                }
            ]
        }
    )
    chunks = [
        {"web": {"uri": source_url, "title": "BoardGameGeek filepage"}},
        {
            "web": {
                "uri": grounded_download or download_url,
                "title": "Rulebook PDF",
            }
        },
    ]
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}]},
                "groundingMetadata": {"groundingChunks": chunks},
            }
        ]
    }


def provider(payload: dict) -> GeminiBggFileProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret"
        assert request.url.path.endswith(":generateContent")
        body = json.loads(request.content)
        assert body["tools"] == [{"googleSearch": {}}]
        return httpx.Response(200, json=payload)

    client = httpx.Client(
        base_url="https://generativelanguage.googleapis.com",
        transport=httpx.MockTransport(handler),
    )
    return GeminiBggFileProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.5-flash-lite",
        api_key="secret",
        client=client,
    )


def test_grounded_bgg_pair_becomes_pending_community_candidate():
    source = (
        "https://boardgamegeek.com/filepage/148606/"
        "official-english-rulebook"
    )
    download = (
        "https://cdn.1j1ju.com/medias/b9/b0/"
        "80-the-fox-in-the-forest-rulebook.pdf"
    )
    results = tuple(
        provider(
            response_payload(source_url=source, download_url=download)
        ).discover(query())
    )
    assert len(results) == 1
    candidate = results[0]
    assert candidate.provider == "bgg_google_search"
    assert candidate.source_kind is RulebookSource.COMMUNITY
    assert candidate.official is False
    assert candidate.language == "en"
    assert candidate.bgg_id == 221965
    assert candidate.url == download
    assert candidate.metadata["bgg_filepage"] == source
    assert "google_grounded_transport" in candidate.metadata["identity_evidence"]


def test_ungrounded_download_url_is_rejected():
    source = "https://boardgamegeek.com/filepage/148606/official-english-rulebook"
    claimed = "https://cdn.1j1ju.com/medias/example/rules.pdf"
    other = "https://cdn.1j1ju.com/medias/example/other.pdf"
    results = tuple(
        provider(
            response_payload(
                source_url=source,
                download_url=claimed,
                grounded_download=other,
            )
        ).discover(query())
    )
    assert results == ()


def test_non_bgg_source_or_unapproved_transport_is_rejected():
    source = "https://example.com/filepage/148606/rules"
    download = "https://example.com/rules.pdf"
    results = tuple(
        provider(
            response_payload(source_url=source, download_url=download)
        ).discover(query())
    )
    assert results == ()


def test_bgg_429_exposes_sanitized_quota_failure_without_response_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "sensitive project-specific quota message",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [
                                {
                                    "quotaId": "GroundingSearchRequestsPerDay-FreeTier",
                                    "quotaValue": "0",
                                    "quotaDimensions": {
                                        "project": "must-not-leak",
                                        "model": "gemini-3.5-flash-lite",
                                    },
                                }
                            ],
                        }
                    ],
                }
            },
            request=request,
        )

    client = httpx.Client(
        base_url="https://generativelanguage.googleapis.com",
        transport=httpx.MockTransport(handler),
    )
    item = GeminiBggFileProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.5-flash-lite",
        api_key="secret",
        client=client,
        max_attempts=1,
    )

    try:
        tuple(item.discover(query()))
    except Exception as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected quota failure")

    assert "RESOURCE_EXHAUSTED" in message
    assert "GroundingSearchRequestsPerDay-FreeTier" in message
    assert "limit=0" in message
    assert "sensitive project-specific quota message" not in message
    assert "must-not-leak" not in message


def test_http_429_is_retried_with_bounded_backoff_and_persistent_gate():
    source = "https://boardgamegeek.com/filepage/148606/official-english-rulebook"
    download = "https://cdn.1j1ju.com/medias/example/rules.pdf"
    payload = response_payload(source_url=source, download_url=download)
    calls = 0
    sleeps: list[float] = []
    gates: list[tuple[str, float]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "3"},
                json={
                    "error": {
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                                "retryDelay": "37.5s",
                            }
                        ]
                    }
                },
                request=request,
            )
        return httpx.Response(200, json=payload, request=request)

    client = httpx.Client(
        base_url="https://generativelanguage.googleapis.com",
        transport=httpx.MockTransport(handler),
    )
    item = GeminiBggFileProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.5-flash-lite",
        api_key="secret",
        client=client,
        rate_limiter=lambda scope, interval: gates.append((scope, interval)),
        min_interval_seconds=8.0,
        max_attempts=3,
        sleep=sleeps.append,
    )

    results = tuple(item.discover(query()))

    assert len(results) == 1
    assert calls == 2
    assert gates == [
        ("gemini:bgg-google-search", 8.0),
        ("gemini:bgg-google-search", 8.0),
    ]
    assert sleeps == [37.5]
