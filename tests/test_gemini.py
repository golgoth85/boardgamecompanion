from __future__ import annotations

import json

import httpx
import pytest
from fastapi import HTTPException

from boardgamecompanion.answer_generation import (
    AnswerProtocolError,
    AnswerProviderError,
    GeminiGenerationProvider,
)
from boardgamecompanion.embedding_retrieval import (
    EmbeddingProviderError,
    GeminiEmbeddingProvider,
)
from boardgamecompanion.gemini import resolve_model
from boardgamecompanion.main import (
    get_answer_generation_service,
    get_embedding_retrieval_service,
)
from boardgamecompanion.settings import settings


def _metadata(model: str, method: str, version: str = "001") -> dict:
    return {
        "name": f"models/{model}",
        "baseModelId": model,
        "version": version,
        "displayName": model,
        "inputTokenLimit": 1048576,
        "outputTokenLimit": 65536,
        "supportedGenerationMethods": [method],
    }


def test_gemini_model_fingerprint_tracks_version() -> None:
    _, first = resolve_model(
        _metadata("gemini-3.8-flash", "generateContent", "001"),
        configured_model="gemini-3.8-flash",
        required_method="generateContent",
    )
    _, same = resolve_model(
        _metadata("gemini-3.8-flash", "generateContent", "001"),
        configured_model="gemini-3.8-flash",
        required_method="generateContent",
    )
    _, changed = resolve_model(
        _metadata("gemini-3.8-flash", "generateContent", "002"),
        configured_model="gemini-3.8-flash",
        required_method="generateContent",
    )
    assert len(first) == 64
    assert first == same
    assert first != changed


def test_gemini_embedding_provider_uses_auth_metadata_and_batch_embeddings() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["x-goog-api-key"] == "test-key"
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_metadata("gemini-embedding-2", "embedContent"),
            )
        body = json.loads(request.content)
        assert request.url.path.endswith(
            "/models/gemini-embedding-2:batchEmbedContents"
        )
        assert len(body["requests"]) == 2
        assert body["requests"][0]["model"] == "models/gemini-embedding-2"
        assert body["requests"][0]["embedContentConfig"] == {
            "outputDimensionality": 768
        }
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    {"values": [3.0, 4.0]},
                    {"values": [0.0, 5.0]},
                ]
            },
        )

    client = httpx.Client(
        base_url="https://generativelanguage.googleapis.com",
        transport=httpx.MockTransport(handler),
    )
    provider = GeminiEmbeddingProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-embedding-2",
        api_key="test-key",
        requested_dimensions=768,
        timeout_seconds=5,
        verify_tls=True,
        client=client,
    )
    descriptor = provider.describe()
    vectors = provider.embed(["first", "second"], descriptor)

    assert descriptor.provider == "gemini"
    assert descriptor.requested_dimensions == 768
    assert vectors[0] == pytest.approx([0.6, 0.8])
    assert vectors[1] == pytest.approx([0.0, 1.0])
    assert [request.method for request in requests] == ["GET", "POST"]


def test_gemini_generation_provider_uses_structured_output_without_leaking_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["x-goog-api-key"] == "secret-key"
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_metadata("gemini-3.8-flash", "generateContent"),
            )
        body = json.loads(request.content)
        assert body["generationConfig"]["temperature"] == 0.0
        fmt = body["generationConfig"]["responseFormat"]["text"]
        assert fmt["mimeType"] == "APPLICATION_JSON"
        assert fmt["schema"]["properties"]["status"]["enum"] == [
            "answer",
            "not_found",
        ]
        assert "untrusted quoted data" in body["systemInstruction"]["parts"][0]["text"]
        user_payload = json.loads(body["contents"][0]["parts"][0]["text"])
        assert user_payload["question"] == "Question"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {"status": "not_found", "claims": []}
                                    )
                                }
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    client = httpx.Client(
        base_url="https://generativelanguage.googleapis.com",
        transport=httpx.MockTransport(handler),
    )
    provider = GeminiGenerationProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.8-flash",
        api_key="secret-key",
        timeout_seconds=5,
        verify_tls=True,
        temperature=0.0,
        client=client,
    )
    descriptor = provider.describe()
    result = provider.generate(
        query="Question",
        evidence=[
            {
                "evidence_id": "E1",
                "text": "Evidence.",
                "document": {"id": "doc"},
                "page": {"number": 1},
            }
        ],
        descriptor=descriptor,
        max_claims=12,
    )
    assert descriptor.provider == "gemini"
    assert result == {"status": "not_found", "claims": []}
    assert "secret-key" not in repr(result)


def test_gemini_generation_malformed_json_is_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=_metadata("gemini-3.8-flash", "generateContent"),
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "{not json"}]}}
                ]
            },
        )

    provider = GeminiGenerationProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.8-flash",
        api_key="secret",
        timeout_seconds=5,
        verify_tls=True,
        temperature=0.0,
        client=httpx.Client(
            base_url="https://generativelanguage.googleapis.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    descriptor = provider.describe()
    with pytest.raises(AnswerProtocolError, match="invalid JSON"):
        provider.generate(
            query="Question",
            evidence=[],
            descriptor=descriptor,
            max_claims=12,
        )


@pytest.mark.parametrize(
    ("kind", "error_type", "message"),
    [
        ("generation", AnswerProviderError, "timed out"),
        ("embedding", EmbeddingProviderError, "timed out"),
    ],
)
def test_gemini_timeout_is_explicit(kind, error_type, message) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = httpx.Client(
        base_url="https://generativelanguage.googleapis.com",
        transport=httpx.MockTransport(handler),
    )
    if kind == "generation":
        provider = GeminiGenerationProvider(
            base_url="https://generativelanguage.googleapis.com",
            model="gemini-3.8-flash",
            api_key="never-log-this",
            timeout_seconds=1,
            verify_tls=True,
            temperature=0.0,
            client=client,
        )
    else:
        provider = GeminiEmbeddingProvider(
            base_url="https://generativelanguage.googleapis.com",
            model="gemini-embedding-2",
            api_key="never-log-this",
            requested_dimensions=768,
            timeout_seconds=1,
            verify_tls=True,
            client=client,
        )
    with pytest.raises(error_type, match=message) as exc:
        provider.describe()
    assert "never-log-this" not in str(exc.value)


def test_gemini_http_auth_failure_does_not_echo_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    provider = GeminiGenerationProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.8-flash",
        api_key="sensitive-key",
        timeout_seconds=5,
        verify_tls=True,
        temperature=0.0,
        client=httpx.Client(
            base_url="https://generativelanguage.googleapis.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(AnswerProviderError, match="HTTP 401") as exc:
        provider.describe()
    assert "sensitive-key" not in str(exc.value)


def test_runtime_selects_embedding_and_generation_providers_independently(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    monkeypatch.setattr(settings, "rag_provider", "ollama")
    monkeypatch.setattr(settings, "embedding_provider", "lmstudio")
    monkeypatch.setattr(settings, "generation_provider", "gemini")
    monkeypatch.setattr(settings, "lmstudio_url", "http://lmstudio.test")
    monkeypatch.setattr(
        settings,
        "lmstudio_embedding_model",
        "text-embedding-qwen3-embedding-0.6b",
    )
    monkeypatch.setattr(settings, "gemini_api_key", "secret")

    retrieval = get_embedding_retrieval_service()
    answer = get_answer_generation_service()

    from boardgamecompanion.answer_generation import GeminiGenerationProvider
    from boardgamecompanion.embedding_retrieval import LMStudioEmbeddingProvider

    assert isinstance(retrieval.provider, LMStudioEmbeddingProvider)
    assert isinstance(answer.provider, GeminiGenerationProvider)
    assert isinstance(answer.retrieval.provider, LMStudioEmbeddingProvider)


def test_legacy_rag_provider_remains_backward_compatible(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    monkeypatch.setattr(settings, "embedding_provider", None)
    monkeypatch.setattr(settings, "generation_provider", None)
    monkeypatch.setattr(settings, "rag_provider", "lmstudio")
    monkeypatch.setattr(settings, "lmstudio_url", "http://lmstudio.test")
    monkeypatch.setattr(
        settings,
        "lmstudio_embedding_model",
        "text-embedding-qwen3-embedding-0.6b",
    )
    monkeypatch.setattr(settings, "lmstudio_generation_model", "qwen3-14b")
    monkeypatch.setattr(settings, "lmstudio_api_key", None)

    from boardgamecompanion.answer_generation import LMStudioGenerationProvider
    from boardgamecompanion.embedding_retrieval import LMStudioEmbeddingProvider

    retrieval = get_embedding_retrieval_service()
    answer = get_answer_generation_service()
    assert isinstance(retrieval.provider, LMStudioEmbeddingProvider)
    assert isinstance(answer.provider, LMStudioGenerationProvider)


def test_gemini_selected_without_api_key_is_explicit(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    monkeypatch.setattr(settings, "embedding_provider", "gemini")
    monkeypatch.setattr(settings, "generation_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", None)

    with pytest.raises(HTTPException) as embedding_error:
        get_embedding_retrieval_service()
    assert embedding_error.value.status_code == 503
    assert "BGC_GEMINI_API_KEY" in str(embedding_error.value.detail)

    with pytest.raises(HTTPException) as generation_error:
        get_answer_generation_service()
    assert generation_error.value.status_code == 503
    assert "BGC_GEMINI_API_KEY" in str(generation_error.value.detail)
