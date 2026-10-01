from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from fastapi import HTTPException

from boardgamecompanion.answer_generation import (
    AnswerProtocolError,
    AnswerProviderError,
    GeminiGenerationProvider,
    _validate_generation,
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
        assert "temperature" not in body["generationConfig"]
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



def test_gemini_generation_recovers_from_temporary_503_with_bounded_backoff(
    monkeypatch,
) -> None:
    attempts = []
    sleeps = []
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.random.uniform",
        lambda low, high: 0.0,
    )
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep",
        sleeps.append,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) <= 2:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        return httpx.Response(
            200,
            json={
                "candidates": [{
                    "content": {
                        "parts": [{"text": '{"status":"not_found","claims":[]}'}]
                    },
                }],
            },
        )

    provider = GeminiGenerationProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.8-flash",
        api_key="secret",
        timeout_seconds=30,
        verify_tls=True,
        temperature=0.0,
        client=httpx.Client(
            base_url="https://generativelanguage.googleapis.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    result = provider.generate(
        query="Question",
        evidence=[{"evidence_id": "E1", "text": "Evidence."}],
        descriptor=type("Descriptor", (), {"model": "gemini-3.8-flash"})(),
        max_claims=4,
    )
    assert result == {"status": "not_found", "claims": []}
    assert len(attempts) == 3
    assert sleeps == [1.0, 2.0]
    assert all(x.headers["x-goog-api-key"] == "secret" for x in attempts)


def test_gemini_503_retries_end_after_fixed_budget(monkeypatch) -> None:
    requests = []
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.random.uniform",
        lambda low, high: 0.0,
    )
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep",
        lambda _: None,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503)

    provider = GeminiGenerationProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.8-flash",
        api_key="secret",
        timeout_seconds=30,
        verify_tls=True,
        temperature=0.0,
        client=httpx.Client(
            base_url="https://generativelanguage.googleapis.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(AnswerProviderError, match="HTTP 503"):
        provider.describe()
    assert len(requests) == 4


def test_gemini_401_is_not_retried(monkeypatch) -> None:
    requests = []
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep",
        lambda _: pytest.fail("Authentication error must not back off"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(401)

    provider = GeminiGenerationProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.8-flash",
        api_key="secret",
        timeout_seconds=30,
        verify_tls=True,
        temperature=0.0,
        client=httpx.Client(
            base_url="https://generativelanguage.googleapis.com",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(AnswerProviderError, match="HTTP 401"):
        provider.describe()
    assert len(requests) == 1


def _gemini_test_provider(handler, *, model="gemini-3.8-flash"):
    return GeminiGenerationProvider(
        base_url="https://generativelanguage.googleapis.com",
        model=model,
        api_key="private-test-key",
        timeout_seconds=45,
        verify_tls=True,
        temperature=0.0,
        client=httpx.Client(
            base_url="https://generativelanguage.googleapis.com",
            transport=httpx.MockTransport(handler),
        ),
    )


def _gemini_text_response(content):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"content": {"parts": [{"text": content}]}}
            ],
        },
    )


def test_gemini_38_503_fallback_uses_plain_generation_and_strict_shape(monkeypatch):
    requests = []
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep", lambda _: None
    )
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.random.uniform",
        lambda _min, _max: 0.0,
    )

    def handler(request):
        requests.append(request)
        assert request.headers["x-goog-api-key"] == "private-test-key"
        if request.method == "GET":
            return httpx.Response(
                200, json=_metadata("gemini-3.8-flash", "generateContent")
            )
        payload = json.loads(request.content)
        if "generationConfig" in payload:
            assert "temperature" not in payload["generationConfig"]
            assert "responseFormat" in payload["generationConfig"]
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})
        assert "generationConfig" not in payload
        system_prompt = payload["systemInstruction"]["parts"][0]["text"]
        assert "untrusted quoted data" in system_prompt
        assert '"not_found"' in system_prompt
        assert '"supports"' in system_prompt
        assert "markdown fences" in system_prompt
        assert json.loads(payload["contents"][0]["parts"][0]["text"]) == {
            "question": "Question",
            "maximum_claims": 12,
            "evidence": [{"evidence_id": "E1", "text": "Evidence."}],
        }
        return _gemini_text_response('{"status":"not_found","claims":[]}')

    provider = _gemini_test_provider(handler)
    descriptor = provider.describe()
    recorded_deadlines = []
    genuine_request = provider._request

    def observe_request(method, path, **kwargs):
        recorded_deadlines.append(kwargs.get("deadline"))
        return genuine_request(method, path, **kwargs)

    provider._request = observe_request
    raw = provider.generate(
        query="Question",
        evidence=[{"evidence_id": "E1", "text": "Evidence."}],
        descriptor=descriptor,
        max_claims=12,
    )
    assert raw == {"status": "not_found", "claims": []}
    assert _validate_generation(
        raw, evidence_by_id={"E1": {"text": "Evidence."}}, max_claims=12
    ) == ("not_found", [])
    posts = [req for req in requests if req.method == "POST"]
    assert len(posts) == 5
    assert all("generationConfig" in json.loads(req.content) for req in posts[:4])
    assert "generationConfig" not in json.loads(posts[-1].content)
    assert len(recorded_deadlines) == 2
    assert recorded_deadlines[0] is not None
    assert recorded_deadlines[0] == recorded_deadlines[1]
    assert "private-test-key" not in repr(raw)


@pytest.mark.parametrize("raw", ["not JSON", "\x60\x60\x60json\n{}\n\x60\x60\x60", "[]"])
def test_gemini_38_plain_fallback_must_still_parse_json(monkeypatch, raw):
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep", lambda _: None
    )
    requests = []

    def handler(request):
        requests.append(request)
        if "generationConfig" in json.loads(request.content):
            return httpx.Response(503)
        return _gemini_text_response(raw)

    provider = _gemini_test_provider(handler)
    descriptor = type("Descriptor", (), {"model": "gemini-3.8-flash"})()
    with pytest.raises(AnswerProtocolError, match="invalid JSON|not an object"):
        provider.generate(
            query="Question",
            evidence=[{"evidence_id": "E1", "text": "Evidence."}],
            descriptor=descriptor,
            max_claims=12,
        )
    assert len(requests) == 5


def test_gemini_38_plain_fallback_never_approves_fabricated_quote(monkeypatch):
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep", lambda _: None
    )

    def handler(request):
        if "generationConfig" in json.loads(request.content):
            return httpx.Response(503)
        return _gemini_text_response(json.dumps({
            "status": "answer",
            "claims": [{"text": "Unsupported rule.",
                        "supports": [{"evidence_id": "E1",
                                      "quote": "This quote is not present."}]}],
        }))

    provider = _gemini_test_provider(handler)
    raw = provider.generate(
        query="Question",
        evidence=[{"evidence_id": "E1", "text": "Evidence."}],
        descriptor=type("Descriptor", (), {"model": "gemini-3.8-flash"})(),
        max_claims=12,
    )
    with pytest.raises(AnswerProtocolError, match="not present in cited evidence"):
        _validate_generation(
            raw, evidence_by_id={"E1": {"text": "Evidence."}}, max_claims=12
        )


@pytest.mark.parametrize(("status", "attempts"), [(400, 1), (401, 1), (429, 4)])
def test_gemini_38_never_falls_back_on_unrelated_http_statuses(
    monkeypatch, status, attempts
):
    seen = []
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep", lambda _: None
    )

    def handler(request):
        seen.append(request)
        assert "responseFormat" in json.loads(request.content)["generationConfig"]
        return httpx.Response(status)

    provider = _gemini_test_provider(handler)
    with pytest.raises(AnswerProviderError, match=f"HTTP {status}") as caught:
        provider.generate(
            query="Question",
            evidence=[],
            descriptor=type("Descriptor", (), {"model": "gemini-3.8-flash"})(),
            max_claims=12,
        )
    assert len(seen) == attempts
    assert "private-test-key" not in str(caught.value)


def test_other_gemini_model_retains_sampling_and_never_uses_38_fallback(
    monkeypatch,
):
    attempts = []
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep", lambda _: None
    )

    def handler(request):
        attempts.append(request)
        conf = json.loads(request.content)["generationConfig"]
        assert conf["temperature"] == 0.0
        return httpx.Response(503)

    provider = _gemini_test_provider(handler, model="gemini-2.5-flash")
    with pytest.raises(AnswerProviderError, match="HTTP 503"):
        provider.generate(
            query="Question",
            evidence=[],
            descriptor=type("Descriptor", (), {"model": "gemini-2.5-flash"})(),
            max_claims=12,
        )
    assert len(attempts) == 4


def test_gemini_38_double_503_fails_closed_and_preserves_retry_bounds(
    monkeypatch,
):
    attempts = []
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep", lambda _: None
    )

    def handler(request):
        attempts.append(request)
        return httpx.Response(503)

    provider = _gemini_test_provider(handler)
    with pytest.raises(AnswerProviderError, match="HTTP 503"):
        provider.generate(
            query="Question",
            evidence=[],
            descriptor=type("Descriptor", (), {"model": "gemini-3.8-flash"})(),
            max_claims=12,
        )
    assert len(attempts) == 8
    assert sum(
        "generationConfig" in json.loads(req.content) for req in attempts
    ) == 4



def test_gemini_deadline_rejects_slow_fallback_200(monkeypatch):
    """A late HTTP 200 must never defeat the shared generation deadline."""
    genuine_sleep = time.sleep
    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.time.sleep", lambda _: None
    )
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        if "generationConfig" in seen[-1]:
            return httpx.Response(503)
        genuine_sleep(0.080)  # Simulates a transport ignoring HTTPX timeout.
        return _gemini_text_response('{"status":"not_found","claims":[]}')

    provider = _gemini_test_provider(handler)
    provider.timeout_seconds = 0.040
    with pytest.raises(AnswerProviderError, match="timed out"):
        provider.generate(
            query="Question",
            evidence=[{"evidence_id": "E1", "text": "Evidence."}],
            descriptor=type("Descriptor", (), {"model": "gemini-3.8-flash"})(),
            max_claims=12,
        )
    # The 40 ms budget correctly stops structured retries before backoff.
    # One structured 503 then one slow fallback 200 is sufficient for F1.
    assert len(seen) == 2
    assert "generationConfig" in seen[0]
    assert "generationConfig" not in seen[-1]


def test_gemini_deadline_interrupts_slow_async_response_body(monkeypatch):
    """HTTPX read timeout is per chunk; asyncio.wait_for bounds the WHOLE read."""
    original_async_client = httpx.AsyncClient
    opened = []

    class SlowTrickle(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"candidates":'
            await asyncio.sleep(0.500)  # A slow-but-live response body.
            yield b'[]}'

        async def aclose(self):
            pass

    async def handler(request):
        opened.append(request)
        return httpx.Response(200, stream=SlowTrickle())

    def offline_async_client(*args, **kwargs):
        return original_async_client(
            *args, **kwargs, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(
        "boardgamecompanion.answer_generation.httpx.AsyncClient",
        offline_async_client,
    )
    provider = GeminiGenerationProvider(
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-3.8-flash",
        api_key="private-test-key",
        timeout_seconds=0.050,
        verify_tls=True,
        temperature=0.0,
    )
    started = time.monotonic()
    with pytest.raises(AnswerProviderError, match="timed out"):
        provider._request(
            "POST", "/v1beta/models/gemini-3.8-flash:generateContent",
            json={"contents": [{"parts": [{"text": "synthetic"}]}]},
        )
    assert time.monotonic() - started < 0.400
    assert len(opened) == 1
    assert opened[0].headers["x-goog-api-key"] == "private-test-key"


def test_gemini_deadline_rejects_slow_primary_200(monkeypatch):
    """A late first-strategy success must be rejected without fallback."""
    genuine_sleep = time.sleep
    seen = []

    def handler(request):
        seen.append(request)
        genuine_sleep(0.080)
        return _gemini_text_response('{"status":"not_found","claims":[]}')

    provider = _gemini_test_provider(handler)
    provider.timeout_seconds = 0.040
    with pytest.raises(AnswerProviderError, match="timed out"):
        provider.generate(
            query="Question",
            evidence=[],
            descriptor=type("Descriptor", (), {"model": "gemini-3.8-flash"})(),
            max_claims=12,
        )
    assert len(seen) == 1  # Never trigger fallback on an expired 200.
