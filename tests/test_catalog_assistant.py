from types import SimpleNamespace

import httpx
import pytest

from boardgamecompanion.catalog_assistant import (
    CatalogAssistantError,
    CatalogAssistantService,
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
