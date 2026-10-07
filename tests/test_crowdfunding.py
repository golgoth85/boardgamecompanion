from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from boardgamecompanion.crowdfunding import (
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
    assert payload["providers"]["kickstarter"]["status"] == "unavailable"


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
