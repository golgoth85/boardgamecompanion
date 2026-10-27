from __future__ import annotations

import json
import re
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from boardgamecompanion.bgg_metadata import BggApiClient, BggMetadataError
from boardgamecompanion.catalog import Catalog
from boardgamecompanion.database import Database
from boardgamecompanion.suggestion_editorial import SuggestionEditorialService


class SuggestionsError(RuntimeError):
    pass


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _compact_names(values: list[str], limit: int) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if not cleaned:
        return ""
    selected = cleaned[:limit]
    if len(cleaned) > limit:
        return ", ".join(selected) + " e altre"
    return ", ".join(selected)


def _plain_description(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _game_overview(metadata: dict[str, Any]) -> dict[str, Any]:
    categories = [str(value) for value in metadata.get("categories") or []]
    mechanics = [str(value) for value in metadata.get("mechanics") or []]
    min_players = metadata.get("min_players")
    max_players = metadata.get("max_players")
    playing = metadata.get("playing_time")
    weight = metadata.get("bgg_average_weight")

    facts: list[str] = []
    if categories:
        facts.append("Tema/ambito: " + _compact_names(categories, 3) + ".")
    if mechanics:
        facts.append("Meccaniche: " + _compact_names(mechanics, 4) + ".")
    if isinstance(min_players, int) and isinstance(max_players, int):
        players = (
            f"{min_players} giocatori"
            if min_players == max_players
            else f"{min_players}–{max_players} giocatori"
        )
        facts.append("Pensato per " + players + ".")
    if isinstance(playing, int) and playing > 0:
        facts.append(f"Durata indicativa {playing} minuti.")
    if isinstance(weight, (int, float)) and weight > 0:
        facts.append(f"Complessità BGG {float(weight):.1f}/5.")

    description = _plain_description(metadata.get("description"))
    return {
        "summary": " ".join(facts),
        "setting": categories[:4],
        "mechanics": mechanics[:6],
        "source_description_available": bool(description),
    }


CACHE_SCHEMA_VERSION = 4
EDITORIAL_BATCH_SIZE = 10
CATALOG_PER_CATEGORY = 120
# Catalog titles admitted early (crowdfunding, upcoming) have a handful of
# votes and inflated averages: only ranked titles with real votes qualify.
CATALOG_MIN_VOTERS = 200


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def _player_counts(value: Any) -> set[int]:
    return {int(token) for token in re.findall(r"\d+", str(value or ""))}


def _is_recent(item: dict[str, Any]) -> bool:
    year = item.get("year_published")
    return isinstance(year, int) and year >= datetime.now(UTC).year - 2


def _is_light(item: dict[str, Any]) -> bool:
    weight = _number((item.get("bgg") or {}).get("average_weight"))
    playing = _number((item.get("play_time") or {}).get("playing"))
    return weight is not None and weight <= 2.2 and (playing is None or playing <= 60)


def _is_heavy(item: dict[str, Any]) -> bool:
    weight = _number((item.get("bgg") or {}).get("average_weight"))
    return weight is not None and weight >= 3.2


def _is_duo(item: dict[str, Any]) -> bool:
    players = item.get("players") or {}
    return 2 in _player_counts(players.get("best")) or (
        players.get("min") == 2 and players.get("max") == 2
    )


def _is_gem(item: dict[str, Any]) -> bool:
    bgg = item.get("bgg") or {}
    average = _number(bgg.get("average"))
    voters = bgg.get("users_rated")
    return (
        average is not None
        and average >= 7.3
        and isinstance(voters, int)
        and 0 < voters <= 4000
    )


def _score_key(item: dict[str, Any]) -> tuple[float, int]:
    return (-float(item.get("suggestion_score") or 0), int(item.get("hot_rank") or 10_000))


def _novelty_key(item: dict[str, Any]) -> tuple[float, float]:
    return (
        -float((item.get("score_parts") or {}).get("novelty") or 0),
        -float(item.get("suggestion_score") or 0),
    )


def _bgg_key(item: dict[str, Any]) -> tuple[float, float]:
    bgg = item.get("bgg") or {}
    return (-float(bgg.get("bayes_average") or 0), -float(bgg.get("average") or 0))


def _trending_key(item: dict[str, Any]) -> tuple[int, float]:
    return (int(item.get("hot_rank") or 10_000), -float(item.get("suggestion_score") or 0))


def _gem_key(item: dict[str, Any]) -> tuple[float, float]:
    parts = item.get("score_parts") or {}
    return (
        -(float(parts.get("quality") or 0) + float(parts.get("taste_fit") or 0)),
        -float(item.get("suggestion_score") or 0),
    )


# key -> (filter, ordering). Filters only narrow the same candidate pool.
SUGGESTION_CATEGORIES: dict[str, tuple[Any, Any]] = {
    "for_you": (None, _score_key),
    "novelty": (None, _novelty_key),
    "trending": (lambda item: bool(item.get("hot_rank")), _trending_key),
    "bgg": (None, _bgg_key),
    "gems": (_is_gem, _gem_key),
    "recent": (_is_recent, _score_key),
    "light": (_is_light, _score_key),
    "heavy": (_is_heavy, _score_key),
    "duo": (_is_duo, _score_key),
}


def category_items(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    accept, order = SUGGESTION_CATEGORIES.get(key) or SUGGESTION_CATEGORIES["for_you"]
    values = [item for item in items if accept is None or accept(item)]
    values.sort(key=order)
    return values


class SuggestionsService:
    """Grounded suggestions for games that are not already owned."""

    _proposed_lock = threading.Lock()

    def __init__(
        self,
        database: Database,
        client: BggApiClient | None,
        *,
        cache_path: Path,
        editorial_service: SuggestionEditorialService | None = None,
        cache_ttl_seconds: int = 24 * 60 * 60,
        candidate_limit: int = 50,
        candidate_pool_limit: int = 500,
    ) -> None:
        self.database = database
        self.client = client
        self.cache_path = Path(cache_path)
        self.editorial_service = editorial_service
        self.cache_ttl_seconds = int(cache_ttl_seconds)
        self.candidate_limit = max(20, min(int(candidate_limit), 100))
        self.candidate_pool_limit = max(
            self.candidate_limit,
            min(int(candidate_pool_limit), 1000),
        )
        # Titles already shown and set aside by "proponi alternative"; restorable.
        self.proposed_path = self.cache_path.with_name(
            self.cache_path.stem + "-proposed.json"
        )

    def _owned_ids(self) -> set[int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.bgg_id
                FROM board_games g
                JOIN collection_entries c ON c.board_game_id=g.id
                WHERE COALESCE(c.own,0)=1
                """
            ).fetchall()
        return {int(row["bgg_id"]) for row in rows}

    def _profile(self, owned: list[dict[str, Any]]) -> dict[str, Any]:
        categories: Counter[str] = Counter()
        mechanics: Counter[str] = Counter()
        weights: list[float] = []
        playing_times: list[float] = []

        for game in owned:
            categories.update(dict.fromkeys(game.get("categories") or []).keys())
            mechanics.update(dict.fromkeys(game.get("mechanics") or []).keys())
            weight = game.get("weight")
            if isinstance(weight, (int, float)) and weight > 0:
                weights.append(float(weight))
            time_data = game.get("minutes") or {}
            playing = time_data.get("playing") if isinstance(time_data, dict) else None
            if isinstance(playing, (int, float)) and playing > 0:
                playing_times.append(float(playing))

        return {
            "owned_standalone_count": len(owned),
            "top_categories": categories.most_common(12),
            "top_mechanics": mechanics.most_common(16),
            "average_weight": (
                sum(weights) / len(weights) if weights else None
            ),
            "average_playing_time": (
                sum(playing_times) / len(playing_times)
                if playing_times
                else None
            ),
        }

    @staticmethod
    def _comparison_anchors(
        metadata: dict[str, Any],
        owned: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidate_mechanics = {
            str(value) for value in metadata.get("mechanics") or [] if str(value)
        }
        candidate_categories = {
            str(value) for value in metadata.get("categories") or [] if str(value)
        }
        candidate_weight = metadata.get("bgg_average_weight")
        candidate_time = metadata.get("playing_time")

        ranked: list[tuple[float, dict[str, Any]]] = []
        for game in owned:
            mechanics = {
                str(value) for value in game.get("mechanics") or [] if str(value)
            }
            categories = {
                str(value) for value in game.get("categories") or [] if str(value)
            }
            shared_mechanics = sorted(candidate_mechanics & mechanics)
            shared_categories = sorted(candidate_categories & categories)

            mechanic_fit = (
                len(shared_mechanics) / max(1, len(candidate_mechanics))
                if candidate_mechanics
                else 0.0
            )
            category_fit = (
                len(shared_categories) / max(1, len(candidate_categories))
                if candidate_categories
                else 0.0
            )

            owned_weight = game.get("weight")
            if (
                isinstance(candidate_weight, (int, float))
                and isinstance(owned_weight, (int, float))
                and candidate_weight > 0
                and owned_weight > 0
            ):
                weight_fit = _clamp(
                    1.0 - abs(float(candidate_weight) - float(owned_weight)) / 2.5
                )
            else:
                weight_fit = 0.5

            minutes = game.get("minutes") or {}
            owned_time = minutes.get("playing") if isinstance(minutes, dict) else None
            if (
                isinstance(candidate_time, (int, float))
                and isinstance(owned_time, (int, float))
                and candidate_time > 0
                and owned_time > 0
            ):
                time_fit = _clamp(
                    1.0
                    - abs(float(candidate_time) - float(owned_time))
                    / max(float(candidate_time), float(owned_time), 30.0)
                )
            else:
                time_fit = 0.5

            similarity = (
                0.55 * mechanic_fit
                + 0.25 * category_fit
                + 0.12 * weight_fit
                + 0.08 * time_fit
            )
            if not shared_mechanics and not shared_categories and similarity < 0.3:
                continue
            ranked.append(
                (
                    similarity,
                    {
                        "bgg_id": game.get("bgg_id"),
                        "title": game.get("title"),
                        "shared_mechanics": shared_mechanics[:6],
                        "shared_categories": shared_categories[:4],
                        "weight": owned_weight,
                        "playing_time": owned_time,
                        "similarity": round(similarity, 4),
                    },
                )
            )

        ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("title") or "")))
        return [item for _, item in ranked[:5]]

    @staticmethod
    def _normalized_weights(pairs: list[tuple[str, int]]) -> dict[str, float]:
        if not pairs:
            return {}
        maximum = max(count for _, count in pairs) or 1
        return {name: count / maximum for name, count in pairs}

    def _score(
        self,
        metadata: dict[str, Any],
        *,
        hot_rank: int | None,
        profile: dict[str, Any],
    ) -> tuple[float, dict[str, float], list[str], list[str], list[str]]:
        category_weights = self._normalized_weights(profile["top_categories"])
        mechanic_weights = self._normalized_weights(profile["top_mechanics"])
        categories = [str(value) for value in metadata.get("categories") or []]
        mechanics = [str(value) for value in metadata.get("mechanics") or []]

        matched_categories = sorted(
            (name for name in categories if name in category_weights),
            key=lambda name: category_weights[name],
            reverse=True,
        )
        matched_mechanics = sorted(
            (name for name in mechanics if name in mechanic_weights),
            key=lambda name: mechanic_weights[name],
            reverse=True,
        )
        novel_mechanics = [
            name for name in mechanics if name not in mechanic_weights
        ]

        category_fit = _clamp(
            sum(category_weights[name] for name in matched_categories) / 3.0
        )
        mechanic_fit = _clamp(
            sum(mechanic_weights[name] for name in matched_mechanics) / 4.0
        )

        profile_weight = profile.get("average_weight")
        candidate_weight = metadata.get("bgg_average_weight")
        if (
            isinstance(profile_weight, (int, float))
            and isinstance(candidate_weight, (int, float))
            and profile_weight > 0
            and candidate_weight > 0
        ):
            weight_fit = _clamp(
                1.0
                - abs(float(candidate_weight) - float(profile_weight)) / 2.5
            )
        else:
            weight_fit = 0.5

        bayes = metadata.get("bgg_bayes_average")
        average = metadata.get("bgg_average")
        quality_value = (
            bayes
            if isinstance(bayes, (int, float)) and bayes > 0
            else average
        )
        quality = (
            _clamp((float(quality_value) - 5.0) / 4.0)
            if isinstance(quality_value, (int, float))
            else 0.4
        )
        novelty = _clamp(
            len(novel_mechanics) / max(2.0, float(len(mechanics) or 1))
        )
        hotness = (
            _clamp(
                1.0
                - (max(1, int(hot_rank)) - 1)
                / max(1.0, float(self.candidate_limit - 1))
            )
            if hot_rank
            else 0.0
        )

        taste_fit = (
            0.48 * mechanic_fit
            + 0.27 * category_fit
            + 0.25 * weight_fit
        )
        score = (
            0.48 * taste_fit
            + 0.27 * quality
            + 0.15 * novelty
            + 0.10 * hotness
        )
        return (
            round(_clamp(score) * 100.0, 1),
            {
                "taste_fit": round(taste_fit, 4),
                "quality": round(quality, 4),
                "novelty": round(novelty, 4),
                "hotness": round(hotness, 4),
            },
            matched_categories,
            matched_mechanics,
            novel_mechanics,
        )

    @staticmethod
    def _reason(
        metadata: dict[str, Any],
        *,
        matched_categories: list[str],
        matched_mechanics: list[str],
        novel_mechanics: list[str],
    ) -> str:
        phrases: list[str] = []
        if matched_categories:
            phrases.append(
                "Riprende temi che ricorrono spesso nella tua ludoteca, soprattutto "
                + ", ".join(matched_categories[:2])
                + "."
            )
        if matched_mechanics:
            phrases.append(
                "È vicino ai tuoi gusti per "
                + ", ".join(matched_mechanics[:2])
                + "."
            )
        if novel_mechanics:
            phrases.append(
                "Aggiunge varietà con "
                + ", ".join(novel_mechanics[:2])
                + "."
            )

        facts: list[str] = []
        rating = metadata.get("bgg_average")
        weight = metadata.get("bgg_average_weight")
        playing = metadata.get("playing_time")
        if isinstance(rating, (int, float)) and rating > 0:
            facts.append(f"rating BGG {float(rating):.1f}")
        if isinstance(weight, (int, float)) and weight > 0:
            facts.append(f"peso {float(weight):.1f}")
        if isinstance(playing, int) and playing > 0:
            facts.append(f"{playing} min")
        if facts:
            phrases.append("Dati BGG: " + ", ".join(facts) + ".")

        return (
            " ".join(phrases)
            or "Candidato BGG verificato e non presente nella tua ludoteca."
        )

    def _read_cache(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(
                self.cache_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError, TypeError):
            return None
        return (
            payload
            if isinstance(payload, dict)
            and payload.get("schema_version") in {2, 3, CACHE_SCHEMA_VERSION}
            and isinstance(payload.get("items"), list)
            else None
        )

    def _fresh(self, payload: dict[str, Any]) -> bool:
        # Older caches lack the catalog candidates: rebuild them once.
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return False
        generated = payload.get("generated_at")
        if not isinstance(generated, str):
            return False
        try:
            generated_at = datetime.fromisoformat(
                generated.replace("Z", "+00:00")
            )
        except ValueError:
            return False
        return (
            datetime.now(UTC) - generated_at
        ).total_seconds() < self.cache_ttl_seconds

    def _write_cache(self, payload: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(
            self.cache_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        temporary.replace(self.cache_path)

    @staticmethod
    def _cached_item_to_metadata(item: dict[str, Any]) -> dict[str, Any] | None:
        try:
            bgg_id = int(item["bgg_id"])
        except (KeyError, TypeError, ValueError):
            return None
        players = item.get("players") or {}
        play_time = item.get("play_time") or {}
        bgg = item.get("bgg") or {}
        return {
            "bgg_id": bgg_id,
            "title": item.get("title"),
            "year_published": item.get("year_published"),
            "parent_bgg_id": None,
            "cover_url": item.get("cover_url"),
            "min_players": players.get("min"),
            "max_players": players.get("max"),
            "playing_time": play_time.get("playing"),
            "min_play_time": play_time.get("min"),
            "max_play_time": play_time.get("max"),
            "bgg_average": bgg.get("average"),
            "bgg_bayes_average": bgg.get("bayes_average"),
            "bgg_average_weight": bgg.get("average_weight"),
            "bgg_rank": bgg.get("rank"),
            "bgg_users_rated": bgg.get("users_rated"),
            "bgg_best_players": players.get("best"),
            "player_poll": players.get("poll") or [],
            "bgg_recommended_age": item.get("age"),
            "bgg_language_dependence": item.get("language_dependence"),
            "bgg_recommended_players": players.get("recommended"),
            "categories": list(item.get("categories") or []),
            "mechanics": list(item.get("mechanics") or []),
            "description": item.get("source_description"),
        }

    def _refresh(self) -> dict[str, Any]:
        if self.client is None:
            raise SuggestionsError(
                "Configura il BGG Application Token "
                "per generare i suggerimenti."
            )

        owned_ids = self._owned_ids()
        owned_games = Catalog(self.database).assistant_candidates(limit=250)
        profile = self._profile(owned_games)
        previous = self._read_cache()
        previous_items = [
            item
            for item in (previous or {}).get("items", [])
            if isinstance(item, dict)
        ]

        try:
            hot = self.client.hot(limit=self.candidate_limit)
            current_hot_ids = [
                int(item["bgg_id"])
                for item in hot
                if int(item["bgg_id"]) not in owned_ids
            ]
            metadata_by_id: dict[int, dict[str, Any]] = {}
            for start in range(0, len(current_hot_ids), 20):
                metadata_by_id.update(
                    self.client.things(
                        current_hot_ids[start : start + 20]
                    )
                )
        except BggMetadataError as exc:
            raise SuggestionsError(str(exc)) from exc

        hot_by_id = {
            int(item["bgg_id"]): item
            for item in hot
        }

        history_order: list[int] = []
        historical_metadata: dict[int, dict[str, Any]] = {}
        for item in previous_items:
            # Catalog candidates are recomputed at every refresh, not retained.
            if item.get("origin") == "catalog":
                continue
            metadata = self._cached_item_to_metadata(item)
            if metadata is None:
                continue
            bgg_id = int(metadata["bgg_id"])
            if bgg_id in owned_ids or bgg_id in metadata_by_id:
                continue
            history_order.append(bgg_id)
            historical_metadata[bgg_id] = metadata

        pool_ids = list(dict.fromkeys([*current_hot_ids, *history_order]))
        pool_ids = pool_ids[: self.candidate_pool_limit]
        for bgg_id in pool_ids:
            if bgg_id not in metadata_by_id and bgg_id in historical_metadata:
                metadata_by_id[bgg_id] = historical_metadata[bgg_id]

        ranked: list[dict[str, Any]] = []
        for bgg_id in pool_ids:
            metadata = metadata_by_id.get(bgg_id)
            if not metadata:
                continue
            if metadata.get("parent_bgg_id") is not None:
                continue
            hot_rank = hot_by_id.get(bgg_id, {}).get("hot_rank")
            ranked.append(
                self._ranked_item(
                    metadata,
                    hot_rank=hot_rank,
                    profile=profile,
                    owned_games=owned_games,
                    origin="hot" if hot_rank else "history",
                )
            )

        catalog_items = self._catalog_candidates(
            owned_ids=owned_ids,
            excluded={int(item["bgg_id"]) for item in ranked},
            profile=profile,
            owned_games=owned_games,
        )
        ranked.extend(catalog_items)

        ranked.sort(
            key=lambda item: (
                -float(item["suggestion_score"]),
                int(item["hot_rank"] or 10_000),
                str(item["title"] or "").casefold(),
            )
        )
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "generated_at": (
                datetime.now(UTC)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "source": "bgg_xml_api2_hot_history_catalog",
            "candidate_count": len(ranked),
            "current_hot_count": len(hot),
            "catalog_candidate_count": len(catalog_items),
            "candidate_pool_limit": self.candidate_pool_limit,
            "history_retained_count": sum(
                1 for item in ranked if item.get("origin") == "history"
            ),
            "owned_excluded_count": sum(
                1
                for item in hot
                if int(item["bgg_id"]) in owned_ids
            ),
            "profile": profile,
            "items": ranked,
        }
        self._write_cache(payload)
        return payload

    def _ranked_item(
        self,
        metadata: dict[str, Any],
        *,
        hot_rank: int | None,
        profile: dict[str, Any],
        owned_games: list[dict[str, Any]] | None,
        origin: str,
    ) -> dict[str, Any]:
        """Candidate in cache shape; anchors only when owned games are given."""
        score, parts, matched_categories, matched_mechanics, novel_mechanics = self._score(
            metadata,
            hot_rank=hot_rank,
            profile=profile,
        )
        item = {
            "bgg_id": int(metadata["bgg_id"]),
            "title": metadata.get("title"),
            "year_published": metadata.get("year_published"),
            "cover_url": metadata.get("cover_url"),
            "origin": origin,
            "players": {
                "min": metadata.get("min_players"),
                "max": metadata.get("max_players"),
                "best": metadata.get("bgg_best_players"),
                "recommended": metadata.get("bgg_recommended_players"),
                "poll": metadata.get("player_poll") or [],
            },
            "age": metadata.get("bgg_recommended_age"),
            "language_dependence": metadata.get("bgg_language_dependence"),
            "play_time": {
                "playing": metadata.get("playing_time"),
                "min": metadata.get("min_play_time"),
                "max": metadata.get("max_play_time"),
            },
            "bgg": {
                "average": metadata.get("bgg_average"),
                "bayes_average": metadata.get("bgg_bayes_average"),
                "average_weight": metadata.get("bgg_average_weight"),
                "rank": metadata.get("bgg_rank"),
                "users_rated": metadata.get("bgg_users_rated"),
            },
            "categories": list(metadata.get("categories") or []),
            "mechanics": list(metadata.get("mechanics") or []),
            "source_description": _plain_description(
                metadata.get("description")
            )[:5000],
            "comparison_anchors": (
                self._comparison_anchors(metadata, owned_games)
                if owned_games is not None
                else []
            ),
            "overview": _game_overview(metadata),
            "hot_rank": hot_rank,
            "suggestion_score": score,
            "score_parts": parts,
            "reason": self._reason(
                metadata,
                matched_categories=matched_categories,
                matched_mechanics=matched_mechanics,
                novel_mechanics=novel_mechanics,
            ),
        }
        return item

    def _catalog_candidates(
        self,
        *,
        owned_ids: set[int],
        excluded: set[int],
        profile: dict[str, Any],
        owned_games: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Best catalog titles for every category, so alternatives never run dry.

        Uses the local BGG reference catalog already scanned for Esplora; only
        titles with stored /thing details (categories or mechanics) qualify.
        """
        from boardgamecompanion.bgg_reference import BggReferenceCatalog

        try:
            rows = BggReferenceCatalog(self.database).explore_rows()
        except Exception:  # catalog unavailable: hot candidates still work
            return []

        scored: list[dict[str, Any]] = []
        for row in rows:
            bgg_id = int(row["bgg_id"])
            if bgg_id in owned_ids or bgg_id in excluded:
                continue
            if not row.get("categories") and not row.get("mechanics"):
                continue
            if not row.get("rank") or int(row.get("users_rated") or 0) < CATALOG_MIN_VOTERS:
                continue
            metadata = {
                **row,
                "title": row.get("name"),
                "parent_bgg_id": None,
                "bgg_users_rated": row.get("users_rated"),
                "description": None,
            }
            scored.append(
                self._ranked_item(
                    metadata,
                    hot_rank=None,
                    profile=profile,
                    owned_games=None,
                    origin="catalog",
                )
            )

        selected: dict[int, dict[str, Any]] = {}
        for key in SUGGESTION_CATEGORIES:
            if key == "trending":
                continue
            for item in category_items(scored, key)[:CATALOG_PER_CATEGORY]:
                selected.setdefault(int(item["bgg_id"]), item)
        if not selected:
            return []

        ids = list(selected)
        descriptions: dict[int, str] = {}
        with self.database.connect() as connection:
            for start in range(0, len(ids), 500):
                chunk = ids[start : start + 500]
                for row in connection.execute(
                    "SELECT bgg_id, description FROM bgg_reference_games "
                    f"WHERE bgg_id IN ({','.join('?' * len(chunk))})",
                    chunk,
                ).fetchall():
                    descriptions[int(row["bgg_id"])] = row["description"] or ""

        result = []
        for bgg_id, item in selected.items():
            metadata = self._cached_item_to_metadata(item) or {}
            item["source_description"] = _plain_description(
                descriptions.get(bgg_id)
            )[:5000]
            item["overview"]["source_description_available"] = bool(
                item["source_description"]
            )
            item["comparison_anchors"] = self._comparison_anchors(metadata, owned_games)
            result.append(item)
        return result

    def _read_proposed(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.proposed_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            payload = None
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), dict):
            return {"version": 1, "round": 0, "items": {}}
        return payload

    def _write_proposed(self, payload: dict[str, Any]) -> None:
        self.proposed_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.proposed_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.proposed_path)

    def mark_proposed(self, bgg_ids: list[int], *, sort: str = "for_you") -> dict[str, Any]:
        """Set shown titles aside so the next request proposes alternatives."""
        with self._proposed_lock:
            payload = self._read_proposed()
            payload["round"] = int(payload.get("round") or 0) + 1
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            for bgg_id in dict.fromkeys(int(value) for value in bgg_ids):
                payload["items"].setdefault(
                    str(bgg_id),
                    {"round": payload["round"], "sort": sort, "at": now},
                )
            self._write_proposed(payload)
        return {"proposed_count": len(payload["items"]), "round": payload["round"]}

    def restore_proposed(self, bgg_ids: list[int] | None = None) -> dict[str, Any]:
        """Bring set-aside titles back; all of them when no ids are given."""
        with self._proposed_lock:
            payload = self._read_proposed()
            if bgg_ids is None:
                restored = len(payload["items"])
                payload["items"] = {}
            else:
                keys = {str(int(value)) for value in bgg_ids}
                restored = sum(1 for key in keys if key in payload["items"])
                payload["items"] = {
                    key: value
                    for key, value in payload["items"].items()
                    if key not in keys
                }
            self._write_proposed(payload)
        return {"restored": restored, "proposed_count": len(payload["items"])}

    def _enrich(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected = [dict(item) for item in items]
        if self.editorial_service is not None:
            # Same generation, requested in small batches so long lists stay responsive.
            enriched: list[dict[str, Any]] = []
            for start in range(0, len(selected), EDITORIAL_BATCH_SIZE):
                enriched.extend(
                    self.editorial_service.enrich(
                        selected[start : start + EDITORIAL_BATCH_SIZE]
                    )
                )
            selected = enriched
        for item in selected:
            item.pop("source_description", None)
            item.pop("comparison_anchors", None)
        return selected

    def list_suggestions(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
        refresh: bool = False,
        sort: str = "for_you",
        view: str = "new",
    ) -> dict[str, Any]:
        cap = max(1, min(int(limit), 50))
        start = max(0, int(offset))
        sort_mode = sort if sort in SUGGESTION_CATEGORIES else "for_you"
        view_mode = view if view in {"new", "proposed"} else "new"

        cached = self._read_cache()
        if cached is not None and not refresh and self._fresh(cached):
            payload, state = cached, "fresh"
        else:
            try:
                payload = self._refresh()
                state = "refreshed"
            except SuggestionsError:
                if cached is None:
                    raise
                payload, state = cached, "stale"

        proposed = self._read_proposed()["items"]
        items = [item for item in payload["items"] if isinstance(item, dict)]
        fresh_items = [item for item in items if str(item.get("bgg_id")) not in proposed]
        category_counts = {
            key: len(category_items(fresh_items, key)) for key in SUGGESTION_CATEGORIES
        }
        if view_mode == "proposed":
            pool = [item for item in items if str(item.get("bgg_id")) in proposed]
            # Most recently set aside first; the category ordering within a round.
            ordered = category_items(pool, sort_mode)
            position = {id(item): index for index, item in enumerate(ordered)}
            ordered.sort(
                key=lambda item: (
                    -int(proposed[str(item["bgg_id"])].get("round") or 0),
                    position[id(item)],
                )
            )
        else:
            ordered = category_items(fresh_items, sort_mode)

        selected = self._enrich(ordered[start : start + cap])
        if view_mode == "proposed":
            for item in selected:
                item["proposed"] = proposed.get(str(item["bgg_id"]))
        return {
            **{key: value for key, value in payload.items() if key != "items"},
            "cache_state": state,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "items": selected,
            "sort": sort_mode,
            "view": view_mode,
            "offset": start,
            "limit": cap,
            "total_available": len(ordered),
            "category_counts": category_counts,
            "proposed_count": sum(
                1 for item in items if str(item.get("bgg_id")) in proposed
            ),
        }
