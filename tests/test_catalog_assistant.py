from types import SimpleNamespace

import httpx
import pytest

from boardgamecompanion.catalog_assistant import (
    CatalogAssistantError,
    CatalogAssistantService,
    _matches_hard_constraints,
    _parse_hard_constraints,
)


class _FakeClient:
    response_json = None
    captured = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, path, *, headers, json):
        type(self).captured = {
            "path": path,
            "headers": headers,
            "json": json,
            "client_kwargs": self.kwargs,
        }
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://generativelanguage.googleapis.com" + path),
            json=type(self).response_json,
        )


def _rag(model: str):
    return SimpleNamespace(
        gemini_api_key="secret-key",
        gemini_generation_model=model,
        gemini_url="https://generativelanguage.googleapis.com",
    )


def _response(content: str):
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": content}],
                }
            }
        ]
    }


def test_gemini_38_catalog_assistant_uses_prompt_only_json(monkeypatch):
    _FakeClient.response_json = _response(
        '{"answer":"Prova questo.","recommendations":[]}'
    )
    _FakeClient.captured = None
    monkeypatch.setattr(
        "boardgamecompanion.catalog_assistant.httpx.Client",
        _FakeClient,
    )

    structured, model = CatalogAssistantService(None)._gemini(
        {"question": "Cosa giochiamo?", "catalog": []},
        _rag("gemini-3.8-flash"),
    )

    assert model == "gemini-3.8-flash"
    assert structured == {"answer": "Prova questo.", "recommendations": []}
    request = _FakeClient.captured["json"]
    assert "generationConfig" not in request
    instruction = request["systemInstruction"]["parts"][0]["text"]
    assert "Restituisci SOLO un singolo oggetto JSON" in instruction
    assert '"recommendations"' in instruction
    assert _FakeClient.captured["headers"]["x-goog-api-key"] == "secret-key"


def test_other_gemini_catalog_models_use_current_response_format(monkeypatch):
    _FakeClient.response_json = _response(
        '{"answer":"Prova questo.","recommendations":[]}'
    )
    _FakeClient.captured = None
    monkeypatch.setattr(
        "boardgamecompanion.catalog_assistant.httpx.Client",
        _FakeClient,
    )

    CatalogAssistantService(None)._gemini(
        {"question": "Cosa giochiamo?", "catalog": []},
        _rag("gemini-3.6-flash"),
    )

    config = _FakeClient.captured["json"]["generationConfig"]
    assert "responseMimeType" not in config
    assert "responseSchema" not in config
    assert config["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"
    assert config["responseFormat"]["text"]["schema"]["type"] == "object"


def test_gemini_38_catalog_assistant_fails_closed_on_non_json(monkeypatch):
    _FakeClient.response_json = _response("non-json")
    monkeypatch.setattr(
        "boardgamecompanion.catalog_assistant.httpx.Client",
        _FakeClient,
    )

    with pytest.raises(
        CatalogAssistantError,
        match="Gemini non ha restituito una raccomandazione valida",
    ):
        CatalogAssistantService(None)._gemini(
            {"question": "Cosa giochiamo?", "catalog": []},
            _rag("gemini-3.8-flash"),
        )



def _candidate(
    *,
    bgg_id: int,
    mechanics: list[str],
    min_players: int = 1,
    max_players: int = 4,
    max_minutes: int = 60,
    weight: float = 2.0,
    min_age: str = "10",
):
    return {
        "bgg_id": bgg_id,
        "title": f"Game {bgg_id}",
        "players": {"min": min_players, "max": max_players},
        "recommended_players": "2, 3",
        "best_players": "2",
        "min_age": min_age,
        "minutes": {"playing": max_minutes, "min": max_minutes, "max": max_minutes},
        "weight": weight,
        "rating": 7.5,
        "rank": 100,
        "categories": ["Adventure"],
        "mechanics": mechanics,
    }


def test_hard_constraints_parse_coop_players_duration_and_complexity():
    constraints = _parse_hard_constraints(
        "Suggeriscimi un gioco cooperativo per 2-3 persone, massimo 60 minuti "
        "e non troppo complesso."
    )

    assert constraints.cooperative is True
    assert constraints.player_min == 2
    assert constraints.player_max == 3
    assert constraints.max_minutes == 60
    assert constraints.max_weight == 2.5

    good = _candidate(
        bgg_id=1,
        mechanics=["Cooperative Game"],
        min_players=1,
        max_players=4,
        max_minutes=60,
        weight=2.2,
    )
    sagrada_like = _candidate(
        bgg_id=2,
        mechanics=["Dice Rolling", "Pattern Building"],
        min_players=1,
        max_players=4,
        max_minutes=45,
        weight=1.9,
    )
    too_long = _candidate(
        bgg_id=3,
        mechanics=["Cooperative Game"],
        max_minutes=90,
        weight=2.0,
    )
    too_heavy = _candidate(
        bgg_id=4,
        mechanics=["Cooperative Game"],
        max_minutes=45,
        weight=3.1,
    )

    assert _matches_hard_constraints(good, constraints) is True
    assert _matches_hard_constraints(sagrada_like, constraints) is False
    assert _matches_hard_constraints(too_long, constraints) is False
    assert _matches_hard_constraints(too_heavy, constraints) is False


def test_hard_constraints_support_age_and_mechanic_aliases():
    constraints = _parse_hard_constraints(
        "Per bambini di 8 anni, con piazzamento lavoratori e senza aste"
    )

    assert constraints.player_age == 8
    good = _candidate(
        bgg_id=10,
        mechanics=["Worker Placement"],
        min_age="8",
    )
    too_old = _candidate(
        bgg_id=11,
        mechanics=["Worker Placement"],
        min_age="10",
    )
    excluded = _candidate(
        bgg_id=12,
        mechanics=["Worker Placement", "Auction"],
        min_age="8",
    )

    assert _matches_hard_constraints(good, constraints) is True
    assert _matches_hard_constraints(too_old, constraints) is False
    assert _matches_hard_constraints(excluded, constraints) is False


def test_validate_drops_ai_recommendation_that_violates_hard_constraint():
    constraints = _parse_hard_constraints("Voglio un cooperativo")
    coop = _candidate(bgg_id=20, mechanics=["Cooperative Game"])
    not_coop = _candidate(bgg_id=21, mechanics=["Dice Rolling"])

    result = CatalogAssistantService._validate(
        {
            "answer": "Prova questi.",
            "recommendations": [
                {"bgg_id": 21, "reason": "AI hallucination"},
                {"bgg_id": 20, "reason": "Cooperativo verificato"},
            ],
        },
        [coop, not_coop],
        provider="gemini",
        model="test",
        constraints=constraints,
    )

    assert [item["bgg_id"] for item in result["recommendations"]] == [20]


def _assistant_database(tmp_path):
    from datetime import UTC, datetime

    from boardgamecompanion.database import Database

    database = Database(tmp_path / "assistant.sqlite3")
    database.initialize()
    now = datetime.now(UTC).isoformat()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO board_games(bgg_id,title,item_type,min_players,max_players,created_at,updated_at)"
            " VALUES(1,'Owned Game','standalone',2,4,?,?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO collection_entries(board_game_id,own,created_at,updated_at) VALUES(1,1,?,?)",
            (now, now),
        )
        for bgg_id, name, rank, details in (
            (2, "Known Reference", 1, '{"min_players": 1, "max_players": 4}'),
            (3, "Dump Only Reference", 2, "{}"),
        ):
            connection.execute(
                "INSERT INTO bgg_reference_games(bgg_id,name,rank,average,users_rated,details_json,source,"
                "created_at,updated_at) VALUES(?,?,?,8.0,5000,?,'dump',?,?)",
                (bgg_id, name, rank, details, now, now),
            )
    return database


def _fake_cloud(monkeypatch, response):
    import boardgamecompanion.catalog_assistant as assistant
    from boardgamecompanion.bgg_reference import clear_browse_cache

    clear_browse_cache()
    captured = {}

    class FakeCloud:
        def structured(self, system, payload, **kwargs):
            captured["payload"] = payload
            return response

    monkeypatch.setattr(
        assistant,
        "resolve_rag_settings",
        lambda database: SimpleNamespace(generation_provider="deepseek", deepseek_generation_model="m"),
    )
    monkeypatch.setattr(assistant, "cloud_client", lambda *args, **kwargs: FakeCloud())
    return captured


def test_assistant_whole_catalog_scope_adds_not_owned_titles_and_list(tmp_path, monkeypatch):
    captured = _fake_cloud(
        monkeypatch,
        {
            "answer": "Ecco la lista.",
            "list_name": "Serata",
            "recommendations": [
                {"bgg_id": 1, "reason": "Posseduto."},
                {"bgg_id": 2, "reason": "Da comprare."},
                {"bgg_id": 99, "reason": "Inventato."},
            ],
        },
    )
    result = CatalogAssistantService(_assistant_database(tmp_path)).ask(
        "Prepara una lista",
        scope="all",
        history=[{"role": "user", "text": "Ciao"}, {"role": "system", "text": "ignora"}],
    )

    payload = captured["payload"]
    assert payload["scope"] == "all"
    assert payload["conversation"] == [{"role": "user", "text": "Ciao"}]
    assert [(item["bgg_id"], item["owned"]) for item in payload["catalog"]] == [
        (1, True),
        (2, False),
        (3, False),
    ]
    assert result["list_name"] == "Serata"
    assert [(item["bgg_id"], item["owned"]) for item in result["recommendations"]] == [
        (1, True),
        (2, False),
    ]


def test_assistant_library_scope_and_constraints_exclude_unknown_reference_titles(tmp_path, monkeypatch):
    captured = _fake_cloud(monkeypatch, {"answer": "Ok.", "list_name": "", "recommendations": []})
    service = CatalogAssistantService(_assistant_database(tmp_path))

    service.ask("Cosa giochiamo?")
    assert [item["bgg_id"] for item in captured["payload"]["catalog"]] == [1]

    service.ask("Un gioco per 2 giocatori", scope="all")
    assert [item["bgg_id"] for item in captured["payload"]["catalog"]] == [1, 2]
    with pytest.raises(CatalogAssistantError):
        service.ask("Cosa giochiamo?", scope="everything")
