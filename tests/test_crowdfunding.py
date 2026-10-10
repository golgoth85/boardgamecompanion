from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from boardgamecompanion.crowdfunding import (
    ApifyKickstarterProvider,
    CrowdfundingProviderError,
    CrowdfundingService,
)


class FakeGamefound:
    def __init__(self, campaigns):
        self.campaigns = campaigns
        self.fail = False

    def fetch_active(self):
        if self.fail:
            raise CrowdfundingProviderError("Gamefound offline")
        return [dict(item) for item in self.campaigns]


class FakeKickstarter:
    configured = True

    def __init__(self, campaigns):
        self.campaigns = campaigns
        self.fail = False
        self.calls = 0

    def fetch_campaigns(self):
        self.calls += 1
        if self.fail:
            raise CrowdfundingProviderError("Kickstarter offline")
        return [dict(item) for item in self.campaigns]


class FakeFx:
    def __init__(self, rates):
        self.rates = rates
        self.fail = False

    def fetch_rates(self):
        if self.fail:
            raise CrowdfundingProviderError("ECB offline")
        return dict(self.rates)


def campaign(
    slug: str,
    *,
    funds: float,
    currency: str,
    backers: int,
    hours_left: int,
) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": f"gamefound:{slug}",
        "platform": "gamefound",
        "platform_project_id": slug,
        "title": slug.replace("-", " ").title(),
        "creator": "Studio",
        "funds": funds,
        "currency": currency,
        "goal": 10_000,
        "backer_count": backers,
        "campaign_start": (now - timedelta(days=10)).isoformat(),
        "campaign_end": (now + timedelta(hours=hours_left)).isoformat(),
        "project_url": f"https://gamefound.com/en/projects/studio/{slug}",
        "image_url": None,
        "description": "Test campaign",
        "reward_count": 1,
        "update_count": 2,
        "comment_count": 3,
    }


def service(tmp_path: Path) -> CrowdfundingService:
    gamefound = FakeGamefound(
        [
            campaign("big-usd", funds=120_000, currency="USD", backers=5000, hours_left=240),
            campaign("big-eur", funds=100_000, currency="EUR", backers=2500, hours_left=24),
            campaign("crowd-favorite", funds=40_000, currency="EUR", backers=7000, hours_left=96),
        ]
    )
    fx = FakeFx({"EUR": 1.0, "USD": 1.2})
    return CrowdfundingService(
        cache_path=tmp_path / "crowdfunding-cache.json",
        cache_ttl_seconds=3600,
        gamefound=gamefound,
        fx=fx,
    )


def test_funds_ranking_uses_eur_normalization_and_preserves_originals(tmp_path: Path) -> None:
    subject = service(tmp_path)
    payload = subject.list_campaigns(sort="funds", status="active", refresh=True)

    assert payload["count"] == 3
    assert [item["platform_project_id"] for item in payload["items"]][:2] == [
        "big-usd",
        "big-eur",
    ]
    usd = payload["items"][0]
    assert usd["funds"] == 120_000
    assert usd["currency"] == "USD"
    assert usd["funds_eur"] == 100_000
    assert payload["providers"]["gamefound"]["status"] == "ok"
    assert payload["providers"]["kickstarter"]["status"] == "configuration_required"


def test_backer_and_ending_rankings_are_independent(tmp_path: Path) -> None:
    subject = service(tmp_path)

    by_backers = subject.list_campaigns(sort="backers", refresh=True)
    assert by_backers["items"][0]["platform_project_id"] == "crowd-favorite"

    by_ending = subject.list_campaigns(sort="ending")
    assert by_ending["items"][0]["platform_project_id"] == "big-eur"
    assert by_ending["items"][0]["status"] == "ending_soon"


def test_top_score_is_explainable_and_not_percent_funded_only(tmp_path: Path) -> None:
    payload = service(tmp_path).list_campaigns(sort="top", refresh=True)

    assert "55% fondi" in payload["ranking"]["top"]
    assert all("top_score" in item for item in payload["items"])
    assert all(item["funding_percent"] is not None for item in payload["items"])


def test_stale_local_cache_keeps_section_readable_when_provider_fails(tmp_path: Path) -> None:
    subject = service(tmp_path)
    first = subject.list_campaigns(refresh=True)
    assert first["providers"]["gamefound"]["status"] == "ok"

    subject.gamefound.fail = True
    subject.fx.fail = True
    stale = subject.list_campaigns(refresh=True)

    assert stale["count"] == 3
    assert stale["providers"]["gamefound"]["status"] == "stale"
    assert stale["providers"]["gamefound"]["error"] == "Gamefound offline"
    assert stale["providers"]["fx"]["status"] == "stale"


def test_upcoming_does_not_scrape_when_public_api_lacks_discovery(tmp_path: Path) -> None:
    payload = service(tmp_path).list_campaigns(sort="upcoming", status="upcoming", refresh=True)

    assert payload["items"] == []
    assert payload["providers"]["gamefound"]["supports_upcoming"] is False



def kickstarter_campaign(
    slug: str,
    *,
    funds: float,
    currency: str,
    backers: int,
    hours_left: int,
) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": f"kickstarter:{slug}",
        "platform": "kickstarter",
        "platform_project_id": slug,
        "title": slug.replace("-", " ").title(),
        "creator": "Kickstarter Studio",
        "funds": funds,
        "currency": currency,
        "goal": 20_000,
        "backer_count": backers,
        "campaign_start": (now - timedelta(days=5)).isoformat(),
        "campaign_end": (now + timedelta(hours=hours_left)).isoformat(),
        "project_url": f"https://www.kickstarter.com/projects/studio/{slug}",
        "image_url": None,
        "description": "Kickstarter campaign",
        "reward_count": 0,
        "update_count": 0,
        "comment_count": 0,
        "raw_status": "live",
        "funds_usd": funds,
    }


def test_kickstarter_campaigns_are_merged_into_shared_ranking(tmp_path: Path) -> None:
    subject = service(tmp_path)
    subject.kickstarter = FakeKickstarter(
        [
            kickstarter_campaign(
                "ks-hit",
                funds=250_000,
                currency="EUR",
                backers=9_000,
                hours_left=120,
            )
        ]
    )

    payload = subject.list_campaigns(sort="top", refresh=True)

    assert payload["providers"]["kickstarter"]["status"] == "ok"
    assert payload["providers"]["kickstarter"]["supports_upcoming"] is True
    assert any(item["platform_project_id"] == "ks-hit" for item in payload["items"])
    assert payload["items"][0]["platform_project_id"] == "ks-hit"


def test_kickstarter_cache_is_reused_across_more_frequent_gamefound_refreshes(
    tmp_path: Path,
) -> None:
    ks = FakeKickstarter(
        [
            kickstarter_campaign(
                "cached-ks",
                funds=50_000,
                currency="EUR",
                backers=1_500,
                hours_left=72,
            )
        ]
    )
    subject = service(tmp_path)
    subject.cache_ttl_seconds = 0
    subject.kickstarter = ks
    subject.kickstarter_cache_ttl_seconds = 3600

    subject.list_campaigns(refresh=False)
    subject.list_campaigns(refresh=False)

    assert ks.calls == 1


def test_apify_provider_normalizes_structured_campaign_data() -> None:
    seen_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == (
            "/v2/actors/fetchfinch~kickstarter-scraper/"
            "run-sync-get-dataset-items"
        )
        assert "token" not in request.url.params
        assert request.headers["Authorization"] == "Bearer secret"
        seen_payload.update(__import__("json").loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json=[
                {
                    "projectId": "123",
                    "slug": "great-game",
                    "url": "https://www.kickstarter.com/projects/studio/great-game",
                    "title": "Great Game",
                    "blurb": "A board game",
                    "status": "live",
                    "goal": 10000,
                    "pledged": 75000,
                    "usdPledged": 80000,
                    "currency": "EUR",
                    "percentFunded": 750,
                    "backersCount": 2200,
                    "deadline": "2026-11-01T12:00:00Z",
                    "launchedAt": "2026-10-01T12:00:00Z",
                    "creator": {"name": "Studio"},
                    "imageUrl": "https://example.test/game.jpg",
                }
            ],
        )

    provider = ApifyKickstarterProvider(
        token="secret",
        transport=httpx.MockTransport(handler),
        max_items=25,
        max_pages=2,
    )

    campaigns = provider.fetch_campaigns()

    assert seen_payload["maxItems"] == 25
    assert seen_payload["maxPages"] == 2
    assert len(seen_payload["startUrls"]) == 2
    assert campaigns == [
        {
            "id": "kickstarter:123",
            "platform": "kickstarter",
            "platform_project_id": "123",
            "title": "Great Game",
            "creator": "Studio",
            "funds": 75000.0,
            "currency": "EUR",
            "goal": 10000.0,
            "backer_count": 2200,
            "campaign_start": "2026-10-01T12:00:00Z",
            "campaign_end": "2026-11-01T12:00:00Z",
            "project_url": "https://www.kickstarter.com/projects/studio/great-game",
            "image_url": "https://example.test/game.jpg",
            "description": "A board game",
            "reward_count": 0,
            "update_count": 0,
            "comment_count": 0,
            "raw_status": "live",
            "funds_usd": 80000.0,
        }
    ]



def test_manual_refresh_does_not_bypass_kickstarter_billing_ttl(tmp_path: Path) -> None:
    ks = FakeKickstarter(
        [
            kickstarter_campaign(
                "paid-cache",
                funds=80_000,
                currency="EUR",
                backers=2_000,
                hours_left=96,
            )
        ]
    )
    subject = service(tmp_path)
    subject.kickstarter = ks
    subject.kickstarter_cache_ttl_seconds = 3600

    subject.list_campaigns(refresh=True)
    subject.list_campaigns(refresh=True)

    assert ks.calls == 1


def test_newly_configured_kickstarter_fetches_even_with_fresh_gamefound_cache(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "crowdfunding-cache.json"
    without_kickstarter = service(tmp_path)
    without_kickstarter.list_campaigns(refresh=True)

    ks = FakeKickstarter(
        [
            kickstarter_campaign(
                "first-fetch",
                funds=65_000,
                currency="EUR",
                backers=1_900,
                hours_left=120,
            )
        ]
    )
    with_kickstarter = service(tmp_path)
    with_kickstarter.kickstarter = ks

    payload = with_kickstarter.list_campaigns()

    assert ks.calls == 1
    assert any(
        item["platform_project_id"] == "first-fetch"
        for item in payload["items"]
    )



def test_unconfigured_kickstarter_does_not_serve_old_cached_rows(tmp_path: Path) -> None:
    ks = FakeKickstarter(
        [
            kickstarter_campaign(
                "cached-before-disable",
                funds=90_000,
                currency="EUR",
                backers=2_100,
                hours_left=96,
            )
        ]
    )
    enabled = service(tmp_path)
    enabled.kickstarter = ks
    enabled.list_campaigns(refresh=True)

    disabled = service(tmp_path)
    payload = disabled.list_campaigns()

    assert payload["providers"]["kickstarter"]["status"] == "configuration_required"
    assert all(item["platform"] != "kickstarter" for item in payload["items"])


def test_gamefound_error_is_not_marked_stale_from_kickstarter_only_cache(
    tmp_path: Path,
) -> None:
    ks = FakeKickstarter(
        [
            kickstarter_campaign(
                "ks-only",
                funds=120_000,
                currency="EUR",
                backers=3_000,
                hours_left=120,
            )
        ]
    )
    subject = service(tmp_path)
    subject.kickstarter = ks
    subject.gamefound.fail = True

    payload = subject.list_campaigns(refresh=True)

    assert payload["providers"]["gamefound"]["status"] == "error"
    assert payload["providers"]["kickstarter"]["status"] == "ok"



def test_apify_provider_verifies_token_with_bearer_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v2/users/me"
        assert "token" not in request.url.params
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={"data": {"id": "user-123", "username": "marco-test"}},
        )

    provider = ApifyKickstarterProvider(
        token="secret",
        transport=httpx.MockTransport(handler),
    )

    assert provider.verify_token() == {
        "verified": True,
        "username": "marco-test",
        "user_id": "user-123",
    }



def test_crowdfunding_filters_obvious_non_boardgame_tabletop_noise(
    tmp_path: Path,
) -> None:
    subject = service(tmp_path)
    subject.kickstarter = FakeKickstarter(
        [
            {
                **kickstarter_campaign(
                    "wizard-lamp",
                    funds=100_000,
                    currency="EUR",
                    backers=2_000,
                    hours_left=120,
                ),
                "title": "Wizard's Light: A Staff-Lamp That Brings Magic to Your Space",
                "description": "A handcrafted staff lamp for your gaming room.",
            },
            {
                **kickstarter_campaign(
                    "real-boardgame",
                    funds=80_000,
                    currency="EUR",
                    backers=1_500,
                    hours_left=120,
                ),
                "title": "Real Adventure",
                "description": "A cooperative board game with miniatures.",
            },
        ]
    )

    payload = subject.list_campaigns(sort="top", refresh=True)

    ids = {item["platform_project_id"] for item in payload["items"]}
    assert "wizard-lamp" not in ids
    assert "real-boardgame" in ids
    assert payload["relevance_filtered_count"] == 1


def test_boardgame_positive_signal_overrides_accessory_word_in_description(
    tmp_path: Path,
) -> None:
    subject = service(tmp_path)
    subject.kickstarter = FakeKickstarter(
        [
            {
                **kickstarter_campaign(
                    "miniature-game",
                    funds=60_000,
                    currency="EUR",
                    backers=1_000,
                    hours_left=96,
                ),
                "title": "Miniature Realms",
                "description": (
                    "A strategic board game with miniatures and optional "
                    "3D printable terrain."
                ),
            }
        ]
    )

    payload = subject.list_campaigns(sort="top", refresh=True)

    assert any(
        item["platform_project_id"] == "miniature-game"
        for item in payload["items"]
    )
    assert payload["relevance_filtered_count"] == 0
