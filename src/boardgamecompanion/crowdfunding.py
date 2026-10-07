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
CACHE_SCHEMA_VERSION = 1


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
        fx: EcbFxProvider | None = None,
    ) -> None:
        self.cache_path = cache_path
        self.cache_ttl_seconds = cache_ttl_seconds
        self.gamefound = gamefound or GamefoundProvider()
        self.fx = fx or EcbFxProvider()
        self._lock = threading.Lock()

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

    def _refresh(self, cached: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
        provider_error: str | None = None
        fx_error: str | None = None
        campaigns: list[dict[str, object]] | None = None
        rates: dict[str, float] | None = None

        try:
            campaigns = self.gamefound.fetch_active()
        except CrowdfundingProviderError as exc:
            provider_error = str(exc)

        try:
            rates = self.fx.fetch_rates()
        except CrowdfundingProviderError as exc:
            fx_error = str(exc)

        if campaigns is None and cached:
            campaigns = [
                dict(item) for item in cached.get("campaigns", [])
                if isinstance(item, dict)
            ]
        if rates is None and cached and isinstance(cached.get("fx_rates"), dict):
            rates = {
                str(key).upper(): float(value)
                for key, value in cached["fx_rates"].items()
                if _number(value) > 0
            }

        campaigns = campaigns or []
        rates = rates or {"EUR": 1.0}
        payload: dict[str, Any] = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "fetched_at": now.isoformat().replace("+00:00", "Z"),
            "campaigns": campaigns,
            "fx_rates": rates,
            "provider_errors": {
                "gamefound": provider_error,
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

        status = "active"
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
            if refresh or not self._fresh(cached, now):
                cache = self._refresh(cached, now)
                cache_state = "refreshed" if not cache.get("provider_errors", {}).get("gamefound") else "stale"
            else:
                cache = cached or {}
                cache_state = "fresh"

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

        providers = {
            "gamefound": {
                "status": gamefound_status,
                "error": gamefound_error,
                "supports_active": True,
                "supports_upcoming": False,
                "source": "Gamefound Public API",
            },
            "kickstarter": {
                "status": "unavailable",
                "error": (
                    "No supported public project-discovery source is configured; "
                    "internal or reverse-engineered Kickstarter APIs are intentionally not used."
                ),
                "supports_active": False,
                "supports_upcoming": False,
                "source": None,
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
