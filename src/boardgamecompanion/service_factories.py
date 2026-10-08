from __future__ import annotations

from boardgamecompanion.app_settings import (
    resolve_bgg_settings,
    resolve_crowdfunding_settings,
)
from boardgamecompanion.bgg_metadata import BggApiClient, BggApiConfig, BggMetadataStore
from boardgamecompanion.crowdfunding import (
    ApifyKickstarterProvider,
    CrowdfundingService,
    EcbFxProvider,
    GamefoundProvider,
)
from boardgamecompanion.dependencies import get_database
from boardgamecompanion.expansions import ExpansionService
from boardgamecompanion.rate_limits import PersistentRateLimiter
from boardgamecompanion.settings import settings


def get_bgg_metadata_store() -> BggMetadataStore:
    database = get_database()
    database.initialize()
    resolved = resolve_bgg_settings(database)
    token = (resolved.application_token or "").strip()
    client = (
        BggApiClient(
            BggApiConfig(
                application_token=token,
                timeout_seconds=resolved.timeout_seconds,
                min_interval_seconds=resolved.min_interval_seconds,
            ),
            rate_limiter=PersistentRateLimiter(database).acquire,
        )
        if token
        else None
    )
    return BggMetadataStore(
        database,
        client,
        refresh_seconds=settings.bgg_metadata_refresh_seconds,
    )


def get_expansion_service() -> ExpansionService:
    database = get_database()
    database.initialize()
    return ExpansionService(
        database,
        get_bgg_metadata_store(),
        refresh_seconds=settings.expansion_watch_refresh_seconds,
    )


def get_crowdfunding_service() -> CrowdfundingService:
    database = get_database()
    database.initialize()
    crowdfunding_settings = resolve_crowdfunding_settings(database)
    return CrowdfundingService(
        cache_path=settings.crowdfunding_cache_path,
        cache_ttl_seconds=settings.crowdfunding_cache_ttl_seconds,
        gamefound=GamefoundProvider(
            base_url=settings.gamefound_public_api_url,
            timeout_seconds=settings.crowdfunding_timeout_seconds,
        ),
        kickstarter=ApifyKickstarterProvider(
            token=crowdfunding_settings.apify_token,
            base_url=settings.kickstarter_apify_base_url,
            actor=settings.kickstarter_apify_actor,
            timeout_seconds=settings.kickstarter_apify_timeout_seconds,
            max_items=settings.kickstarter_max_items,
            max_pages=settings.kickstarter_max_pages,
        ),
        kickstarter_cache_ttl_seconds=settings.kickstarter_cache_ttl_seconds,
        fx=EcbFxProvider(timeout_seconds=settings.crowdfunding_timeout_seconds),
    )
