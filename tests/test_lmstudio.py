from __future__ import annotations

import json

import httpx
import pytest
from fastapi import HTTPException

from boardgamecompanion.answer_generation import LMStudioGenerationProvider
from boardgamecompanion.embedding_retrieval import LMStudioEmbeddingProvider
from boardgamecompanion.lmstudio import model_fingerprint
from boardgamecompanion.main import (
    get_answer_generation_service,
    get_embedding_retrieval_service,
)
from boardgamecompanion.settings import settings


def _native_models() -> dict:
    return {
        "models": [
            {
                "type": "llm",
                "publisher": "unsloth",
                "key": "qwen3-14b",
                "display_name": "Qwen3 14B UD",
                "architecture": "qwen3",
                "quantization": {
                    "name": "Q4_K_XL",
                    "bits_per_weight": 4,
                },
                "size_bytes": 9_159_819_378,
                "params_string": "14B",
                "loaded_instances": [
                    {
                        "id": "qwen3-14b",
                        "config": {
                            "context_length": 8192,
                            "flash_attention": True,
                        },
                        "remaining_ttl_seconds": 120,
                    }
                ],
                "max_context_length": 40960,
                "format": "gguf",
                "capabilities": {
                    "vision": False,
                    "trained_for_tool_use": True,
                    "reasoning": {
                        "allowed_options": ["off", "on"],
                        "default": "on",
                    },
                },
            },
            {
                "type": "embedding",
                "publisher": "Qwen",
                "key": "text-embedding-qwen3-embedding-0.6b",
                "display_name": "Qwen3 Embedding 0.6B",
                "quantization": {
                    "name": "Q8_0",
                    "bits_per_weight": 8,
                },
                "size_bytes": 639_150_592,
                "params_string": "0.6B",
                "loaded_instances": [
                    {
                        "id": "text-embedding-qwen3-embedding-0.6b",
                        "config": {"context_length": 8192},
                    }
                ],
                "max_context_length": 32768,
                "format": "gguf",
            },
        ]
    }


def test_lmstudio_model_fingerprint_ignores_runtime_instance_state() -> None:
    item = _native_models()["models"][0]
    first = model_fingerprint(item)
    changed_runtime = json.loads(json.dumps(item))
    changed_runtime["loaded_instances"][0]["remaining_ttl_seconds"] = 1
    changed_runtime["loaded_instances"][0]["config"]["context_length"] = 4096
    second = model_fingerprint(changed_runtime)
    changed_file = json.loads(json.dumps(item))
    changed_file["size_bytes"] += 1
    third = model_fingerprint(changed_file)

    assert len(first) == 64
    assert first == second
    assert first != third


def test_lmstudio_embedding_provider_uses_native_metadata_and_openai_embeddings() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer secret"
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json=_native_models())
        if request.url.path == "/v1/embeddings":
            body = json.loads(request.content)
            assert body == {
                "model": "text-embedding-qwen3-embedding-0.6b",
                "input": ["first", "second"],
            }
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "model": body["model"],
                    "data": [
                        {"index": 1, "embedding": [0.0, 5.0]},
                        {"index": 0, "embedding": [3.0, 4.0]},
                    ],
                    "usage": {"prompt_tokens": 2, "total_tokens": 2},
                },
            )
        return httpx.Response(404)

    client = httpx.Client(
        base_url="http://lmstudio.test",
        transport=httpx.MockTransport(handler),
    )
    provider = LMStudioEmbeddingProvider(
        base_url="http://lmstudio.test",
        model="text-embedding-qwen3-embedding-0.6b",
        requested_dimensions=None,
        timeout_seconds=5.0,
        verify_tls=True,
        api_key="secret",
        client=client,
    )
    descriptor = provider.describe()
    vectors = provider.embed(["first", "second"], descriptor)

    assert descriptor.provider == "lmstudio"
    assert descriptor.model == "text-embedding-qwen3-embedding-0.6b"
    assert len(descriptor.model_digest) == 64
    assert vectors[0] == pytest.approx([0.6, 0.8])
    assert vectors[1] == pytest.approx([0.0, 1.0])
    assert [request.url.path for request in requests] == [
        "/api/v1/models",
        "/v1/embeddings",
    ]


def test_lmstudio_generation_provider_uses_json_schema_chat_completion() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json=_native_models())
        if request.url.path == "/v1/chat/completions":
            body = json.loads(request.content)
            assert body["model"] == "qwen3-14b"
            assert body["temperature"] == 0.0
            assert body["stream"] is False
            schema = body["response_format"]["json_schema"]["schema"]
            assert schema["properties"]["status"]["enum"] == [
                "answer",
                "not_found",
            ]
            assert "untrusted quoted data" in body["messages"][0]["content"]
            user_payload = json.loads(body["messages"][1]["content"])
            assert user_payload["question"] == "Question"
            assert user_payload["evidence"][0]["evidence_id"] == "E1"
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "status": "not_found",
                                        "claims": [],
                                    }
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
        return httpx.Response(404)

    client = httpx.Client(
        base_url="http://lmstudio.test",
        transport=httpx.MockTransport(handler),
    )
    provider = LMStudioGenerationProvider(
        base_url="http://lmstudio.test",
        model="qwen3-14b",
        timeout_seconds=5.0,
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
                "text": "Quoted evidence.",
                "document": {"id": "doc"},
                "page": {"number": 1},
            }
        ],
        descriptor=descriptor,
        max_claims=12,
    )

    assert descriptor.provider == "lmstudio"
    assert descriptor.model == "qwen3-14b"
    assert len(descriptor.model_digest) == 64
    assert result == {"status": "not_found", "claims": []}
    assert [request.url.path for request in requests] == [
        "/api/v1/models",
        "/v1/chat/completions",
    ]


def test_runtime_selects_lmstudio_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    monkeypatch.setattr(settings, "rag_provider", "lmstudio")
    monkeypatch.setattr(settings, "lmstudio_url", "http://lmstudio.test")
    monkeypatch.setattr(
        settings,
        "lmstudio_embedding_model",
        "text-embedding-qwen3-embedding-0.6b",
    )
    monkeypatch.setattr(settings, "lmstudio_generation_model", "qwen3-14b")
    monkeypatch.setattr(settings, "lmstudio_api_key", None)

    retrieval = get_embedding_retrieval_service()
    answer = get_answer_generation_service()

    assert isinstance(retrieval.provider, LMStudioEmbeddingProvider)
    assert isinstance(answer.provider, LMStudioGenerationProvider)
    assert isinstance(answer.retrieval.provider, LMStudioEmbeddingProvider)


def test_lmstudio_configuration_errors_are_explicit(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    monkeypatch.setattr(settings, "rag_provider", "lmstudio")
    monkeypatch.setattr(settings, "lmstudio_url", None)
    monkeypatch.setattr(settings, "lmstudio_embedding_model", None)
    monkeypatch.setattr(settings, "lmstudio_generation_model", None)

    with pytest.raises(HTTPException) as embedding_error:
        get_embedding_retrieval_service()
    assert embedding_error.value.status_code == 503
    assert "BGC_LMSTUDIO_URL" in str(embedding_error.value.detail)

    with pytest.raises(HTTPException) as answer_error:
        get_answer_generation_service()
    assert answer_error.value.status_code == 503
    assert "BGC_LMSTUDIO_GENERATION_MODEL" in str(answer_error.value.detail)
