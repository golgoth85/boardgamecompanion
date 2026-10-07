from __future__ import annotations

import json
import math
import threading
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


GAMEFOUND_ACTIVE_PATH = "/api/public/projects/getActiveCrowdfundingProjects"
ECB_DAILY_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
KICKSTARTER_LIVE_TABLETOP_URL = (
    "https://www.kickstarter.com/discover/advanced"
    "?category_id=34&sort=most_funded&state=live"
)
KICKSTARTER_UPCOMING_TABLETOP_URL = (
    "https://www.kickstarter.com/discover/advanced"
    "?category_id=34&sort=newest&state=upcoming"
)
CACHE_SCHEMA_VERSION = 2
_CACHE_LOCK = threading.Lock()


class CrowdfundingError(RuntimeError):
    pass


class CrowdfundingProviderError(CrowdfundingError):
    pass


def _number(value: object, *, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(0.0, number)


def _integer(value: object, *, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, number)


def _iso(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class GamefoundProvider:
    platform = "gamefound"

    def __init__(
        self,
        *,
        base_url: str = "https://gamefound.com",
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def fetch_active(self) -> list[dict[str, object]]:
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                transport=self.transport,
                headers={"User-Agent": "BoardGameCompanion/0.1 crowdfunding"},
            ) as client:
                response = client.get(self.base_url + GAMEFOUND_ACTIVE_PATH)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CrowdfundingProviderError(
                f"Gamefound public API unavailable: {type(exc).__name__}"
            ) from exc

        if not isinstance(payload, list):
            raise CrowdfundingProviderError("Gamefound public API returned a non-list payload")

        campaigns: list[dict[str, object]] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            slug = str(raw.get("projectUrlName") or "").strip()
            name = str(raw.get("projectName") or "").strip()
            if not slug or not name:
                continue
            campaigns.append(
                {
                    "id": f"gamefound:{slug}",
                    "platform": "gamefound",
                    "platform_project_id": slug,
                    "title": name,
                    "creator": str(raw.get("creatorName") or "").strip() or None,
                    "funds": _number(raw.get("fundsGathered")),
                    "currency": str(raw.get("currencyShortName") or "").strip().upper() or None,
                    "goal": _number(raw.get("campaignGoal")),
                    "backer_count": _integer(raw.get("backerCount")),
                    "campaign_start": _iso(raw.get("campaignStartDate")),
                    "campaign_end": _iso(raw.get("campaignEndDate")),
                    "project_url": str(raw.get("projectHomeUrl") or "").strip() or None,
                    "image_url": str(raw.get("projectImageUrl") or "").strip() or None,
                    "description": str(raw.get("shortDescription") or "").strip() or None,
                    "reward_count": _integer(raw.get("rewardCount")),
                    "update_count": _integer(raw.get("updateCount")),
                    "comment_count": _integer(raw.get("commentCount")),
                }
            )
        return campaigns


class ApifyKickstarterProvider:
    platform = "kickstarter"

    def __init__(
        self,
        *,
        token: str | None,
        base_url: str = "https://api.apify.com/v2",
        actor: str = "fetchfinch~kickstarter-scraper",
        timeout_seconds: float = 180.0,
        max_items: int = 60,
        max_pages: int = 5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.token = (token or "").strip()
        self.base_url = base_url.rstrip("/")
        self.actor = actor.strip() or "fetchfinch~kickstarter-scraper"
        self.timeout_seconds = timeout_seconds
        self.max_items = max_items
        self.max_pages = max_pages
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @staticmethod
    def _text(value: object) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return None

    @classmethod
    def _nested_text(cls, value: object, *keys: str) -> str | None:
        if not isinstance(value, dict):
            return cls._text(value)
        for key in keys:
            candidate = cls._text(value.get(key))
            if candidate:
                return candidate
        return None

    def fetch_campaigns(self) -> list[dict[str, object]]:
        if not self.configured:
            raise CrowdfundingProviderError("Apify token is not configured")

        endpoint = f"{self.base_url}/acts/{self.actor}/run-sync-get-dataset-items"
        payload = {
            "startUrls": [
                {"url": KICKSTARTER_LIVE_TABLETOP_URL},
                {"url": KICKSTARTER_UPCOMING_TABLETOP_URL},
            ],
            "maxItems": self.max_items,
            "maxPages": self.max_pages,
        }
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                transport=self.transport,
                headers={
                    "User-Agent": "BoardGameCompanion/0.1 crowdfunding",
                    "Accept": "application/json",
                },
            ) as client:
                response = client.post(
                    endpoint,
                    params={"token": self.token},
                    json=payload,
                )
                response.raise_for_status()
                raw_payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CrowdfundingProviderError(
                f"Apify Kickstarter provider unavailable: {type(exc).__name__}"
            ) from exc

        if not isinstance(raw_payload, list):
            raise CrowdfundingProviderError(
                "Apify Kickstarter provider returned a non-list payload"
            )

        campaigns: list[dict[str, object]] = []
        for raw in raw_payload:
            if not isinstance(raw, dict):
                continue
            project_id = self._text(raw.get("projectId"))
            slug = self._text(raw.get("slug"))
            url = self._text(raw.get("url")) or self._text(raw.get("projectUrl"))
            title = self._text(raw.get("title")) or self._text(raw.get("name"))
            stable_id = project_id or slug or url
            if not stable_id or not title:
                continue

            creator = self._nested_text(
                raw.get("creator"), "name", "displayName", "displayableName"
            )
            campaigns.append(
                {
                    "id": f"kickstarter:{stable_id}",
                    "platform": "kickstarter",
                    "platform_project_id": project_id or slug or stable_id,
                    "title": title,
                    "creator": creator,
                    "funds": _number(raw.get("pledged")),
                    "currency": self._text(raw.get("currency")),
                    "goal": _number(raw.get("goal")),
                    "backer_count": _integer(raw.get("backersCount")),
                    "campaign_start": _iso(
                        raw.get("launchedAt")
                        or raw.get("launchDate")
                        or raw.get("launchAt")
                    ),
                    "campaign_end": _iso(raw.get("deadline")),
                    "project_url": url,
                    "image_url": self._text(raw.get("imageUrl")),
                    "description": self._text(raw.get("blurb"))
                    or self._text(raw.get("description")),
                    "reward_count": 0,
                    "update_count": 0,
                    "comment_count": 0,
                    "raw_status": (
                        self._text(raw.get("status"))
                        or self._text(raw.get("state"))
                        or ""
                    ).lower(),
                    "funds_usd": _number(raw.get("usdPledged")),
                }
            )
        return campaigns


class EcbFxProvider:
    def __init__(
        self,
        *,
        url: str = ECB_DAILY_RATES_URL,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def fetch_rates(self) -> dict[str, float]:
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                transport=self.transport,
                headers={"User-Agent": "BoardGameCompanion/0.1 crowdfunding"},
            ) as client:
                response = client.get(self.url)
                response.raise_for_status()
                root = ET.fromstring(response.content)
        except (httpx.HTTPError, ET.ParseError) as exc:
            raise CrowdfundingProviderError(
                f"ECB exchange rates unavailable: {type(exc).__name__}"
            ) from exc

        rates: dict[str, float] = {"EUR": 1.0}
        for element in root.iter():
            currency = element.attrib.get("currency")
            rate = element.attrib.get("rate")
            if not currency or not rate:
                continue
            parsed = _number(rate)
            if parsed > 0:
                rates[currency.upper()] = parsed
        if len(rates) == 1:
            raise CrowdfundingProviderError("ECB exchange-rate response contained no rates")
        return rates


class CrowdfundingService:
    def __init__(
        self,
        *,
        cache_path: Path,
        cache_ttl_seconds: int = 3 * 60 * 60,
        gamefound: GamefoundProvider | None = None,
        kickstarter: ApifyKickstarterProvider | None = None,
        kickstarter_cache_ttl_seconds: int = 12 * 60 * 60,
        fx: EcbFxProvider | None = None,
    ) -> None:
        self.cache_path = cache_path
        self.cache_ttl_seconds = cache_ttl_seconds
        self.gamefound = gamefound or GamefoundProvider()
        self.kickstarter = kickstarter
        self.kickstarter_cache_ttl_seconds = kickstarter_cache_ttl_seconds
        self.fx = fx or EcbFxProvider()
        self._lock = _CACHE_LOCK

    def _read_cache(self) -> dict[str, Any] | None:
        try:
            raw = self.cache_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (FileNotFoundError, OSError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        if not isinstance(payload.get("campaigns"), list):
            return None
        return payload

    def _write_cache(self, payload: dict[str, object]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.cache_path)

    def _fresh(self, cached: dict[str, Any] | None, now: datetime) -> bool:
        if not cached:
            return False
        fetched_at = _parse_datetime(cached.get("fetched_at"))
        if fetched_at is None:
            return False
        return (now - fetched_at).total_seconds() < self.cache_ttl_seconds

    def _refresh(
        self,
        cached: dict[str, Any] | None,
        now: datetime,
        *,
        force_kickstarter: bool = False,
    ) -> dict[str, Any]:
        gamefound_error: str | None = None
        kickstarter_error: str | None = None
        fx_error: str | None = None
        gamefound_campaigns: list[dict[str, object]] | None = None
        kickstarter_campaigns: list[dict[str, object]] | None = None
        rates: dict[str, float] | None = None

        cached_campaigns = [
            dict(item)
            for item in (cached or {}).get("campaigns", [])
            if isinstance(item, dict)
        ]
        cached_gamefound = [
            item for item in cached_campaigns if item.get("platform") == "gamefound"
        ]
        cached_kickstarter = [
            item for item in cached_campaigns if item.get("platform") == "kickstarter"
        ]
        provider_fetched_at = dict((cached or {}).get("provider_fetched_at") or {})

        try:
            gamefound_campaigns = self.gamefound.fetch_active()
            provider_fetched_at["gamefound"] = now.isoformat().replace("+00:00", "Z")
        except CrowdfundingProviderError as exc:
            gamefound_error = str(exc)

        kickstarter_due = False
        if self.kickstarter is not None and self.kickstarter.configured:
            last_kickstarter = _parse_datetime(provider_fetched_at.get("kickstarter"))
            kickstarter_due = (
                force_kickstarter
                or last_kickstarter is None
                or (now - last_kickstarter).total_seconds()
                >= self.kickstarter_cache_ttl_seconds
            )
            if kickstarter_due:
                try:
                    kickstarter_campaigns = self.kickstarter.fetch_campaigns()
                    provider_fetched_at["kickstarter"] = now.isoformat().replace(
                        "+00:00", "Z"
                    )
                except CrowdfundingProviderError as exc:
                    kickstarter_error = str(exc)
            else:
                kickstarter_campaigns = cached_kickstarter
        else:
            kickstarter_campaigns = cached_kickstarter

        try:
            rates = self.fx.fetch_rates()
            provider_fetched_at["fx"] = now.isoformat().replace("+00:00", "Z")
        except CrowdfundingProviderError as exc:
            fx_error = str(exc)

        if gamefound_campaigns is None:
            gamefound_campaigns = cached_gamefound
        if kickstarter_campaigns is None:
            kickstarter_campaigns = cached_kickstarter
        if rates is None and cached and isinstance(cached.get("fx_rates"), dict):
            rates = {
                str(key).upper(): float(value)
                for key, value in cached["fx_rates"].items()
                if _number(value) > 0
            }

        campaigns = [*gamefound_campaigns, *kickstarter_campaigns]
        rates = rates or {"EUR": 1.0}
        payload: dict[str, Any] = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "fetched_at": now.isoformat().replace("+00:00", "Z"),
            "provider_fetched_at": provider_fetched_at,
            "campaigns": campaigns,
            "fx_rates": rates,
            "provider_errors": {
                "gamefound": gamefound_error,
                "kickstarter": kickstarter_error,
                "fx": fx_error,
            },
        }
        if campaigns or cached:
            self._write_cache(payload)
        return payload

    @staticmethod
    def _percentile(values: list[float], value: float | None) -> float:
        if value is None or not values:
            return 0.0
        below_or_equal = sum(1 for candidate in values if candidate <= value)
        return below_or_equal / len(values)

    def _decorate(
        self,
        campaign: dict[str, object],
        *,
        rates: dict[str, float],
        now: datetime,
    ) -> dict[str, object]:
        item = dict(campaign)
        funds = _number(item.get("funds"))
        goal = _number(item.get("goal"))
        currency = str(item.get("currency") or "").upper()
        rate = rates.get(currency)
        funds_eur = (funds / rate) if rate and rate > 0 else (funds if currency == "EUR" else None)
        goal_eur = (goal / rate) if rate and rate > 0 else (goal if currency == "EUR" else None)
        end = _parse_datetime(item.get("campaign_end"))
        start = _parse_datetime(item.get("campaign_start"))
        remaining = None if end is None else max(0, int((end - now).total_seconds()))

        raw_status = str(item.get("raw_status") or "").strip().lower()
        status = "upcoming" if raw_status in {"upcoming", "prelaunch"} else "active"
        if start is not None and start > now:
            status = "upcoming"
        elif end is not None and end <= now:
            status = "ended"
        elif remaining is not None and remaining <= 72 * 60 * 60:
            status = "ending_soon"

        item.update(
            {
                "funds_eur": None if funds_eur is None else round(funds_eur, 2),
                "goal_eur": None if goal_eur is None else round(goal_eur, 2),
                "funding_percent": None if goal <= 0 else round((funds / goal) * 100, 1),
                "remaining_seconds": remaining,
                "status": status,
            }
        )
        return item

    def list_campaigns(
        self,
        *,
        sort: str = "top",
        platform: str = "all",
        status: str = "all",
        limit: int = 50,
        refresh: bool = False,
    ) -> dict[str, object]:
        if sort not in {"top", "funds", "backers", "ending", "upcoming"}:
            raise CrowdfundingError("Unsupported crowdfunding sort")
        if platform not in {"all", "gamefound", "kickstarter"}:
            raise CrowdfundingError("Unsupported crowdfunding platform")
        if status not in {"all", "active", "upcoming"}:
            raise CrowdfundingError("Unsupported crowdfunding status")
        if not 1 <= limit <= 100:
            raise CrowdfundingError("Crowdfunding limit must be between 1 and 100")

        now = datetime.now(UTC)
        with self._lock:
            cached = self._read_cache()
            provider_fetched_at = dict((cached or {}).get("provider_fetched_at") or {})
            kickstarter_needs_initial_fetch = (
                self.kickstarter is not None
                and self.kickstarter.configured
                and _parse_datetime(provider_fetched_at.get("kickstarter")) is None
            )
            if refresh or kickstarter_needs_initial_fetch or not self._fresh(cached, now):
                # A generic/manual refresh never bypasses the Kickstarter TTL: Actor
                # results are billable. A newly configured provider is refreshed
                # immediately because it has no provider-level timestamp yet.
                cache = self._refresh(cached, now, force_kickstarter=False)
                cache_state = "refreshed" if not cache.get("provider_errors", {}).get("gamefound") else "stale"
            else:
                cache = cached or {}
                cached_errors = cache.get("provider_errors") or {}
                cache_state = "stale" if cached_errors.get("gamefound") else "fresh"

        rates = {
            str(key).upper(): float(value)
            for key, value in (cache.get("fx_rates") or {"EUR": 1.0}).items()
            if _number(value) > 0
        }
        campaigns = [
            self._decorate(dict(item), rates=rates, now=now)
            for item in cache.get("campaigns", [])
            if isinstance(item, dict)
        ]

        provider_errors = cache.get("provider_errors") or {}
        gamefound_error = provider_errors.get("gamefound")
        gamefound_status = "ok"
        if gamefound_error:
            gamefound_status = "stale" if campaigns else "error"

        kickstarter_items = [
            item for item in campaigns if item.get("platform") == "kickstarter"
        ]
        kickstarter_error = provider_errors.get("kickstarter")
        if self.kickstarter is None or not self.kickstarter.configured:
            kickstarter_status = "configuration_required"
            kickstarter_error = (
                "Set BGC_APIFY_TOKEN to enable the Kickstarter provider. "
                "No reverse-engineered Kickstarter API is used."
            )
        elif kickstarter_error:
            kickstarter_status = "stale" if kickstarter_items else "error"
        else:
            kickstarter_status = "ok"

        providers = {
            "gamefound": {
                "status": gamefound_status,
                "error": gamefound_error,
                "supports_active": True,
                "supports_upcoming": False,
                "source": "Gamefound Public API",
            },
            "kickstarter": {
                "status": kickstarter_status,
                "error": kickstarter_error,
                "supports_active": True,
                "supports_upcoming": True,
                "source": (
                    "Apify / fetchfinch Kickstarter Scraper"
                    if self.kickstarter is not None
                    else None
                ),
                "terms_notice": (
                    "Third-party discovery provider over public Kickstarter data; "
                    "review Kickstarter terms before enabling automated collection."
                ),
            },
            "fx": {
                "status": "stale" if provider_errors.get("fx") else "ok",
                "error": provider_errors.get("fx"),
                "source": "European Central Bank",
            },
        }

        if platform != "all":
            campaigns = [item for item in campaigns if item.get("platform") == platform]
        if status == "active":
            campaigns = [
                item for item in campaigns
                if item.get("status") in {"active", "ending_soon"}
            ]
        elif status == "upcoming":
            campaigns = [item for item in campaigns if item.get("status") == "upcoming"]

        active_for_score = [
            item for item in campaigns
            if item.get("status") in {"active", "ending_soon"}
        ]
        fund_values = [
            float(item["funds_eur"])
            for item in active_for_score
            if item.get("funds_eur") is not None
        ]
        backer_values = [
            float(_integer(item.get("backer_count")))
            for item in active_for_score
        ]

        for item in campaigns:
            funds_eur = (
                float(item["funds_eur"]) if item.get("funds_eur") is not None else None
            )
            backers = float(_integer(item.get("backer_count")))
            remaining = item.get("remaining_seconds")
            urgency = 0.0
            if isinstance(remaining, int):
                urgency = max(0.0, 1.0 - min(remaining / (14 * 24 * 60 * 60), 1.0))
            item["top_score"] = round(
                0.55 * self._percentile(fund_values, funds_eur)
                + 0.40 * self._percentile(backer_values, backers)
                + 0.05 * urgency,
                4,
            )

        if sort == "funds":
            campaigns.sort(
                key=lambda item: (
                    item.get("funds_eur") is not None,
                    float(item.get("funds_eur") or -1),
                    _integer(item.get("backer_count")),
                ),
                reverse=True,
            )
        elif sort == "backers":
            campaigns.sort(
                key=lambda item: (
                    _integer(item.get("backer_count")),
                    float(item.get("funds_eur") or -1),
                ),
                reverse=True,
            )
        elif sort == "ending":
            campaigns = [
                item for item in campaigns
                if item.get("status") in {"active", "ending_soon"}
            ]
            campaigns.sort(
                key=lambda item: int(item.get("remaining_seconds") or 10**12)
            )
        elif sort == "upcoming":
            campaigns = [item for item in campaigns if item.get("status") == "upcoming"]
            campaigns.sort(
                key=lambda item: _parse_datetime(item.get("campaign_start"))
                or datetime.max.replace(tzinfo=UTC)
            )
        else:
            campaigns.sort(
                key=lambda item: (
                    float(item.get("top_score") or 0.0),
                    _integer(item.get("backer_count")),
                ),
                reverse=True,
            )

        return {
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "cache_state": cache_state,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "ranking": {
                "top": "55% fondi normalizzati EUR, 40% backer, 5% urgenza entro 14 giorni",
                "funds": "fondi raccolti normalizzati in EUR con cambio ECB; valori originali preservati",
                "backers": "numero di finanziatori",
            },
            "providers": providers,
            "count": min(len(campaigns), limit),
            "total_matching": len(campaigns),
            "items": campaigns[:limit],
        }
