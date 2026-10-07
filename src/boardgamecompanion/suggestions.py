from __future__ import annotations

import json
import re
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


class SuggestionsService:
    """Grounded suggestions for games that are not already owned."""

    def __init__(
        self,
        database: Database,
        client: BggApiClient | None,
        *,
        cache_path: Path,
        editorial_service: SuggestionEditorialService | None = None,
        cache_ttl_seconds: int = 24 * 60 * 60,
        candidate_limit: int = 50,
    ) -> None:
        self.database = database
        self.client = client
        self.cache_path = Path(cache_path)
        self.editorial_service = editorial_service
        self.cache_ttl_seconds = int(cache_ttl_seconds)
        self.candidate_limit = max(20, min(int(candidate_limit), 100))

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
        return [item for _, item in ranked[:3]]

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
            and isinstance(payload.get("items"), list)
            else None
        )

    def _fresh(self, payload: dict[str, Any]) -> bool:
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

    def _refresh(self) -> dict[str, Any]:
        if self.client is None:
            raise SuggestionsError(
                "Configura il BGG Application Token "
                "per generare i suggerimenti."
            )

        owned_ids = self._owned_ids()
        owned_games = Catalog(self.database).assistant_candidates(limit=250)
        profile = self._profile(owned_games)
        try:
            hot = self.client.hot(limit=self.candidate_limit)
            candidate_ids = [
                int(item["bgg_id"])
                for item in hot
                if int(item["bgg_id"]) not in owned_ids
            ]
            metadata_by_id: dict[int, dict[str, Any]] = {}
            for start in range(0, len(candidate_ids), 20):
                metadata_by_id.update(
                    self.client.things(
                        candidate_ids[start : start + 20]
                    )
                )
        except BggMetadataError as exc:
            raise SuggestionsError(str(exc)) from exc

        hot_by_id = {
            int(item["bgg_id"]): item
            for item in hot
        }
        ranked: list[dict[str, Any]] = []
        for bgg_id in candidate_ids:
            metadata = metadata_by_id.get(bgg_id)
            if not metadata:
                continue
            if metadata.get("parent_bgg_id") is not None:
                continue

            score, parts, matched_categories, matched_mechanics, novel_mechanics = self._score(
                metadata,
                hot_rank=hot_by_id.get(bgg_id, {}).get("hot_rank"),
                profile=profile,
            )
            ranked.append(
                {
                    "bgg_id": bgg_id,
                    "title": metadata.get("title"),
                    "year_published": metadata.get("year_published"),
                    "cover_url": metadata.get("cover_url"),
                    "players": {
                        "min": metadata.get("min_players"),
                        "max": metadata.get("max_players"),
                        "best": metadata.get("bgg_best_players"),
                        "recommended": metadata.get(
                            "bgg_recommended_players"
                        ),
                    },
                    "play_time": {
                        "playing": metadata.get("playing_time"),
                        "min": metadata.get("min_play_time"),
                        "max": metadata.get("max_play_time"),
                    },
                    "bgg": {
                        "average": metadata.get("bgg_average"),
                        "bayes_average": metadata.get(
                            "bgg_bayes_average"
                        ),
                        "average_weight": metadata.get(
                            "bgg_average_weight"
                        ),
                        "rank": metadata.get("bgg_rank"),
                    },
                    "categories": list(
                        metadata.get("categories") or []
                    ),
                    "mechanics": list(
                        metadata.get("mechanics") or []
                    ),
                    "source_description": _plain_description(
                        metadata.get("description")
                    )[:8000],
                    "comparison_anchors": self._comparison_anchors(
                        metadata,
                        owned_games,
                    ),
                    "overview": _game_overview(metadata),
                    "hot_rank": hot_by_id.get(
                        bgg_id, {}
                    ).get("hot_rank"),
                    "suggestion_score": score,
                    "score_parts": parts,
                    "reason": self._reason(
                        metadata,
                        matched_categories=matched_categories,
                        matched_mechanics=matched_mechanics,
                        novel_mechanics=novel_mechanics,
                    ),
                }
            )

        ranked.sort(
            key=lambda item: (
                -float(item["suggestion_score"]),
                int(item["hot_rank"] or 10_000),
                str(item["title"] or "").casefold(),
            )
        )
        payload = {
            "generated_at": (
                datetime.now(UTC)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "source": "bgg_xml_api2_hot",
            "candidate_count": len(hot),
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

    def list_suggestions(
        self,
        *,
        limit: int = 10,
        refresh: bool = False,
        sort: str = "for_you",
    ) -> dict[str, Any]:
        cap = max(1, min(int(limit), 25))
        sort_mode = sort if sort in {"for_you", "novelty", "bgg"} else "for_you"

        def ordered(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            values = list(items)
            if sort_mode == "novelty":
                values.sort(
                    key=lambda item: (
                        -float((item.get("score_parts") or {}).get("novelty") or 0),
                        -float(item.get("suggestion_score") or 0),
                    )
                )
            elif sort_mode == "bgg":
                values.sort(
                    key=lambda item: (
                        -float((item.get("bgg") or {}).get("bayes_average") or 0),
                        -float((item.get("bgg") or {}).get("average") or 0),
                    )
                )
            else:
                values.sort(
                    key=lambda item: (
                        -float(item.get("suggestion_score") or 0),
                        int(item.get("hot_rank") or 10_000),
                    )
                )
            return values

        cached = self._read_cache()
        if (
            cached is not None
            and not refresh
            and self._fresh(cached)
        ):
            selected = ordered(cached["items"])[:cap]
            if self.editorial_service is not None:
                selected = self.editorial_service.enrich(selected)
            for item in selected:
                item.pop("source_description", None)
                item.pop("comparison_anchors", None)
            return {
                **cached,
                "cache_state": "fresh",
                "cache_ttl_seconds": self.cache_ttl_seconds,
                "items": selected,
                "sort": sort_mode,
                "total_available": len(cached["items"]),
            }

        try:
            payload = self._refresh()
            state = "refreshed"
        except SuggestionsError:
            if cached is None:
                raise
            payload = cached
            state = "stale"

        selected = ordered(payload["items"])[:cap]
        if self.editorial_service is not None:
            selected = self.editorial_service.enrich(selected)
        for item in selected:
            item.pop("source_description", None)
            item.pop("comparison_anchors", None)
        return {
            **payload,
            "cache_state": state,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "items": selected,
            "sort": sort_mode,
            "total_available": len(payload["items"]),
        }
