from __future__ import annotations

from pathlib import Path

from boardgamecompanion.database import Database
from boardgamecompanion.suggestion_editorial import SuggestionEditorialService


class FakeEditorialGenerator(SuggestionEditorialService):
    def __init__(self, database: Database, *, cache_path: Path) -> None:
        super().__init__(database, cache_path=cache_path)
        self.calls = 0

    def _generate(self, items):
        self.calls += 1
        return (
            {
                int(item["bgg_id"]): {
                    "game_summary_it": "Un'avventura cooperativa sintetizzata dalla descrizione BGG.",
                    "why_it_fits": "Condivide il deck building con Owned Game, ma propone un'esperienza diversa.",
                }
                for item in items
            },
            "fake",
            "fake-model",
        )


def test_editorial_copy_is_cached_by_grounding_payload(tmp_path: Path) -> None:
    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    service = FakeEditorialGenerator(
        database,
        cache_path=tmp_path / "editorial.json",
    )
    item = {
        "bgg_id": 200,
        "title": "Candidate",
        "source_description": "A cooperative fantasy adventure.",
        "categories": ["Fantasy"],
        "mechanics": ["Deck Building"],
        "players": {"min": 1, "max": 4},
        "play_time": {"playing": 60},
        "bgg": {"average_weight": 2.5},
        "comparison_anchors": [
            {
                "bgg_id": 100,
                "title": "Owned Game",
                "shared_mechanics": ["Deck Building"],
                "shared_categories": ["Fantasy"],
                "weight": 2.7,
                "playing_time": 70,
                "similarity": 0.8,
            }
        ],
        "overview": {"summary": "fallback"},
        "reason": "fallback reason",
    }

    first = service.enrich([item])
    second = service.enrich([item])

    assert service.calls == 1
    assert first == second
    assert first[0]["editorial_status"] == "ready"
    assert first[0]["editorial_provider"] == "fake"
    assert "Owned Game" in first[0]["why_it_fits"]


def test_editorial_copy_regenerates_when_grounding_changes(tmp_path: Path) -> None:
    database = Database(tmp_path / "bgc.sqlite3")
    database.initialize()
    service = FakeEditorialGenerator(
        database,
        cache_path=tmp_path / "editorial.json",
    )
    item = {
        "bgg_id": 200,
        "title": "Candidate",
        "source_description": "First description.",
        "categories": ["Fantasy"],
        "mechanics": ["Deck Building"],
        "players": {},
        "play_time": {},
        "bgg": {"average_weight": 2.5},
        "comparison_anchors": [],
        "overview": {"summary": "fallback"},
        "reason": "fallback reason",
    }

    service.enrich([item])
    changed = dict(item)
    changed["source_description"] = "Updated description."
    service.enrich([changed])

    assert service.calls == 2
