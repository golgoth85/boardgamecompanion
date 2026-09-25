from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.chunk_index import ChunkIndexService
from boardgamecompanion.database import Database
from boardgamecompanion.embedding_retrieval import (
    EmbeddingConflict,
    EmbeddingCorruptRecord,
    EmbeddingDescriptor,
    EmbeddingProviderError,
    EmbeddingRetrievalService,
    OllamaEmbeddingProvider,
    _descriptor_config,
)
from boardgamecompanion.main import app
from boardgamecompanion.settings import settings
FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def _pdf_with_pages(*texts: str) -> bytes:
    objects: list[bytes] = []
    page_ids: list[int] = []
    content_ids: list[int] = []
    next_id = 3
    for _ in texts:
        page_ids.append(next_id)
        content_ids.append(next_id + 1)
        next_id += 2
    font_id = next_id

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(texts)} >>".encode()
    )
    for page_id, content_id, text in zip(page_ids, content_ids, texts, strict=True):
        assert len(objects) + 1 == page_id
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode()
        )
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode()
            + stream
            + b"\nendstream"
        )
    assert len(objects) + 1 == font_id
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj_id, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{obj_id} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(out)


def _configure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    monkeypatch.setattr(settings, "max_document_bytes", 1024 * 1024)
    monkeypatch.setattr(settings, "pdf_parse_timeout_seconds", 20.0)
    monkeypatch.setattr(settings, "pdf_parse_max_pages", 20)
    monkeypatch.setattr(settings, "pdf_parse_max_chars_per_page", 100_000)
    monkeypatch.setattr(settings, "pdf_parse_max_total_chars", 500_000)
    monkeypatch.setattr(settings, "pdf_parse_memory_mb", 512)
    monkeypatch.setattr(settings, "chunk_max_chars", 200)
    monkeypatch.setattr(settings, "chunk_overlap_chars", 20)
    monkeypatch.setattr(settings, "chunk_min_break_chars", 100)


def _import_game(client: TestClient) -> None:
    with FIXTURE.open("rb") as handle:
        response = client.post(
            "/api/imports/bgg-csv",
            files={"file": ("collection.csv", handle, "text/csv")},
        )
    assert response.status_code == 200


def _long_page(label: str) -> str:
    sentences = [
        f"{label} rule {number}: perform this exact action before the next step."
        for number in range(1, 10)
    ]
    return " ".join(sentences)


class FakeProvider:
    def __init__(self, *, digest: str = "d" * 64, dimensions: int = 4) -> None:
        self.digest = digest
        self.dimensions = dimensions
        self.calls: list[list[str]] = []

    def describe(self) -> EmbeddingDescriptor:
        return EmbeddingDescriptor(
            provider="fake",
            model="deterministic-v1",
            model_digest=self.digest,
            requested_dimensions=self.dimensions,
            endpoint="in-process",
        )

    def embed(
        self,
        texts: list[str],
        descriptor: EmbeddingDescriptor,
    ) -> list[list[float]]:
        assert descriptor == self.describe()
        self.calls.append(list(texts))
        return [_semantic_vector(text, self.dimensions) for text in texts]


def _semantic_vector(text: str, dimensions: int) -> list[float]:
    lower = text.lower()
    values = [
        4.0 if "setup" in lower else 0.2,
        4.0 if "score" in lower else 0.2,
        4.0 if "combat" in lower else 0.2,
        1.0,
    ]
    values = values[:dimensions]
    while len(values) < dimensions:
        values.append(0.1)
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def _service(provider: FakeProvider) -> EmbeddingRetrievalService:
    database = Database(settings.database_path)
    database.initialize()
    chunks = ChunkIndexService(
        database,
        settings.manuals_dir,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
        min_break_chars=settings.chunk_min_break_chars,
    )
    return EmbeddingRetrievalService(
        database,
        chunks,
        provider,
        batch_size=2,
        max_candidates=1000,
    )


def _upload(
    client: TestClient,
    payload: bytes,
    *,
    language: str = "it",
    version_label: str = "v2",
    edition: str = "Retail IT",
    official: bool = True,
    source_url: str = "https://publisher.example/rules.pdf",
) -> dict:
    response = client.post(
        "/api/games/900001/documents",
        data={
            "document_type": "rulebook",
            "language": language,
            "title": f"Rules {language} {version_label}",
            "version_label": version_label,
            "edition": edition,
            "source_url": source_url,
            "is_official": "true" if official else "false",
        },
        files={"file": ("rules.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()["document"]


def _prepare_document(
    client: TestClient,
    *,
    text: str,
    language: str = "it",
    version_label: str = "v2",
    edition: str = "Retail IT",
    official: bool = True,
    source_url: str = "https://publisher.example/rules.pdf",
) -> dict:
    document = _upload(
        client,
        _pdf_with_pages(text),
        language=language,
        version_label=version_label,
        edition=edition,
        official=official,
        source_url=source_url,
    )
    assert client.post(f"/api/documents/{document['id']}/ingest").status_code == 200
    assert client.post(f"/api/documents/{document['id']}/chunks/build").status_code == 200
    return document


def test_embedding_build_is_idempotent_and_pins_model_digest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        document = _prepare_document(
            client,
            text=_long_page("Setup") + " " + _long_page("Score"),
        )

    service = _service(provider)
    first = service.build(document["id"])
    assert first["created"] is True
    index = first["embedding_index"]
    assert index["provider"] == "fake"
    assert index["model"] == "deterministic-v1"
    assert index["model_digest"] == "d" * 64
    assert index["dimensions"] == 4
    assert index["chunk_count"] > 1

    second = service.build(document["id"])
    assert second["created"] is False
    assert second["embedding_index"]["id"] == index["id"]

    with Database(settings.database_path).connect() as connection:
        vectors = connection.execute(
            """
            SELECT dimensions, length(vector_blob) AS bytes, vector_sha256
            FROM chunk_embeddings
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchall()
    assert len(vectors) == index["chunk_count"]
    assert all(row["dimensions"] == 4 and row["bytes"] == 16 for row in vectors)
    assert all(len(row["vector_sha256"]) == 64 for row in vectors)


def test_model_digest_change_requires_a_new_embedding_index(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _prepare_document(client, text=_long_page("Setup"))

    first = _service(FakeProvider(digest="a" * 64)).build(document["id"])
    changed = _service(FakeProvider(digest="b" * 64))
    status = changed.status(document["id"])
    assert status["current"] is None
    assert status["latest_run"]["id"] == first["embedding_index"]["id"]

    second = changed.build(document["id"])
    assert second["created"] is True
    assert second["embedding_index"]["model_digest"] == "b" * 64
    assert second["embedding_index"]["id"] != first["embedding_index"]["id"]


def test_retrieval_prefers_requested_official_language_and_keeps_one_cohort(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        italian_v2 = _prepare_document(
            client,
            text=_long_page("Setup current"),
            language="it",
            version_label="v2",
            edition="Retail IT",
            source_url="https://publisher.example/it-v2.pdf",
        )
        italian_v1 = _prepare_document(
            client,
            text=_long_page("Setup legacy"),
            language="it",
            version_label="v1",
            edition="Retail IT",
            source_url="https://publisher.example/it-v1.pdf",
        )
        english = _prepare_document(
            client,
            text=_long_page("Setup English"),
            language="en",
            version_label="v3",
            edition="Retail EN",
            source_url="https://publisher.example/en-v3.pdf",
        )

    service = _service(provider)
    for document in (italian_v2, italian_v1, english):
        service.build(document["id"])

    result = service.retrieve(
        bgg_id=900001,
        query="setup procedure",
        requested_language="it",
        document_type="rulebook",
        version_label=None,
        edition=None,
        top_k=20,
        min_score=-1.0,
    )
    assert result["results"]
    assert result["policy"]["selected_tier"]["name"] == "official-requested-language"
    assert all(item["document"]["language"] == "it" for item in result["results"])
    cohorts = {
        (item["document"]["version_label"], item["document"]["edition"])
        for item in result["results"]
    }
    assert len(cohorts) == 1
    assert result["policy"]["excluded_conflicting_cohorts"]


def test_retrieval_falls_back_to_official_english(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        english = _prepare_document(
            client,
            text=_long_page("Combat"),
            language="en",
            version_label="v1",
            edition="EN",
            source_url="https://publisher.example/en.pdf",
        )

    service = _service(provider)
    service.build(english["id"])
    result = service.retrieve(
        bgg_id=900001,
        query="combat",
        requested_language="it",
        document_type="rulebook",
        version_label=None,
        edition=None,
        top_k=5,
        min_score=-1.0,
    )
    assert result["results"]
    assert result["policy"]["selected_tier"]["name"] == "official-english"
    assert all(item["document"]["language"] == "en" for item in result["results"])


def test_p7b_rebuild_cascades_embeddings_and_requires_reembedding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        document = _prepare_document(client, text=_long_page("Score"))

    service = _service(provider)
    first = service.build(document["id"])
    assert first["embedding_index"]["chunk_count"] > 0

    database = Database(settings.database_path)
    chunks = service.chunk_service
    chunks.build(document["id"], force=True)

    with database.connect() as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) AS count FROM chunk_embeddings WHERE document_id = ?",
            (document["id"],),
        ).fetchone()["count"]
    assert remaining == 0
    assert service.status(document["id"])["current"] is None
    rebuilt = service.build(document["id"])
    assert rebuilt["created"] is True


def test_corrupt_vector_is_rejected_before_retrieval(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        document = _prepare_document(client, text=_long_page("Combat"))

    service = _service(provider)
    service.build(document["id"])
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            """
            UPDATE chunk_embeddings
            SET vector_blob = zeroblob(length(vector_blob))
            WHERE document_id = ?
            """,
            (document["id"],),
        )
        connection.commit()

    with pytest.raises(EmbeddingCorruptRecord, match="digest"):
        service.retrieve(
            bgg_id=900001,
            query="combat",
            requested_language="it",
            document_type="rulebook",
            version_label=None,
            edition=None,
            top_k=5,
            min_score=-1.0,
        )


def test_embedding_build_revalidates_chunk_set_after_provider_work(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _prepare_document(client, text=_long_page("Setup"))

    class MutatingProvider(FakeProvider):
        mutated = False

        def embed(self, texts, descriptor):
            result = super().embed(texts, descriptor)
            if not self.mutated:
                self.mutated = True
                service.chunk_service.build(document["id"], force=True)
            return result

    provider = MutatingProvider()
    service = _service(provider)

    with pytest.raises(EmbeddingConflict, match="changed"):
        service.build(document["id"])

    with Database(settings.database_path).connect() as connection:
        run_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM document_embedding_runs
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()["count"]
    assert run_count == 0


def test_ollama_provider_pins_digest_and_uses_non_truncating_batch_embed() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "embed-test:latest",
                            "model": "embed-test:latest",
                            "digest": "f" * 64,
                        }
                    ]
                },
            )
        if request.url.path == "/api/embed":
            payload = json.loads(request.content)
            assert payload["model"] == "embed-test:latest"
            assert payload["input"] == ["alpha", "beta"]
            assert payload["truncate"] is False
            assert payload["dimensions"] == 4
            return httpx.Response(
                200,
                json={
                    "embeddings": [
                        [2.0, 0.0, 0.0, 0.0],
                        [0.0, 3.0, 0.0, 0.0],
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )
    provider = OllamaEmbeddingProvider(
        base_url="http://ollama.test",
        model="embed-test",
        requested_dimensions=4,
        timeout_seconds=5.0,
        verify_tls=True,
        client=client,
    )
    descriptor = provider.describe()
    assert descriptor.model == "embed-test:latest"
    assert descriptor.model_digest == "f" * 64
    vectors = provider.embed(["alpha", "beta"], descriptor)
    assert vectors == [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
    assert [request.url.path for request in requests] == ["/api/tags", "/api/embed"]


def test_ollama_provider_rejects_missing_model() -> None:
    client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"models": []})
        ),
    )
    provider = OllamaEmbeddingProvider(
        base_url="http://ollama.test",
        model="missing",
        requested_dimensions=None,
        timeout_seconds=5.0,
        verify_tls=True,
        client=client,
    )
    with pytest.raises(EmbeddingProviderError, match="not installed"):
        provider.describe()


def test_embedding_api_is_explicitly_unconfigured_without_model(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "ollama_url", None)
    monkeypatch.setattr(settings, "ollama_embedding_model", None)
    with TestClient(app) as client:
        _import_game(client)
        response = client.post(
            "/api/games/900001/retrieve",
            json={"query": "setup"},
        )
    assert response.status_code == 503
    assert "BGC_OLLAMA_URL" in response.json()["detail"]


def test_retrieval_coverage_respects_document_filters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        selected = _prepare_document(
            client,
            text=_long_page("Setup selected"),
            version_label="v2",
            edition="Retail IT",
            source_url="https://publisher.example/selected.pdf",
        )
        excluded = _prepare_document(
            client,
            text=_long_page("Setup excluded"),
            version_label="v1",
            edition="Legacy IT",
            source_url="https://publisher.example/excluded.pdf",
        )

    service = _service(provider)
    service.build(selected["id"])

    result = service.retrieve(
        bgg_id=900001,
        query="setup",
        requested_language="it",
        document_type="rulebook",
        version_label="v2",
        edition="Retail IT",
        top_k=5,
        min_score=-1.0,
    )
    assert result["coverage"] == {
        "current_document_count": 1,
        "embedded_document_count": 1,
        "missing_document_ids": [],
    }
    assert excluded["id"] not in result["coverage"]["missing_document_ids"]


def test_non_force_concurrent_embedding_builds_are_idempotent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _prepare_document(client, text=_long_page("Concurrent embed"))

    barrier = threading.Barrier(2)

    class BarrierProvider(FakeProvider):
        def embed(self, texts, descriptor):
            result = super().embed(texts, descriptor)
            barrier.wait(timeout=5)
            return result

    def build_once():
        return _service(BarrierProvider()).build(document["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(build_once), executor.submit(build_once)]
        results = [future.result(timeout=10) for future in futures]

    assert sorted(result["created"] for result in results) == [False, True]
    run_ids = {result["embedding_index"]["id"] for result in results}
    assert len(run_ids) == 1

    with Database(settings.database_path).connect() as connection:
        run_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM document_embedding_runs
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()["count"]
        vector_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM chunk_embeddings
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()["count"]
        expected = connection.execute(
            """
            SELECT chunk_count
            FROM document_embedding_runs
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()["chunk_count"]

    assert run_count == 1
    assert vector_count == expected


def test_direct_chunk_mutation_invalidates_embeddings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        document = _prepare_document(client, text=_long_page("Mutable"))

    service = _service(provider)
    built = service.build(document["id"])
    assert built["embedding_index"]["chunk_count"] > 0

    with sqlite3.connect(settings.database_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM document_chunks
            WHERE document_id = ?
            ORDER BY chunk_index
            LIMIT 1
            """,
            (document["id"],),
        ).fetchone()
        connection.execute(
            """
            UPDATE document_chunks
            SET language = 'tampered'
            WHERE id = ?
            """,
            (row[0],),
        )
        connection.commit()

    with Database(settings.database_path).connect() as connection:
        remaining = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM chunk_embeddings
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()["count"]
    assert remaining < built["embedding_index"]["chunk_count"]

    with pytest.raises(
        EmbeddingCorruptRecord,
        match="metadata digest",
    ):
        service.retrieve(
            bgg_id=900001,
            query="mutable",
            requested_language="it",
            document_type="rulebook",
            version_label=None,
            edition=None,
            top_k=5,
            min_score=-1.0,
        )


class MutatingQueryProvider(FakeProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.on_query = None

    def embed(
        self,
        texts: list[str],
        descriptor: EmbeddingDescriptor,
    ) -> list[list[float]]:
        vectors = super().embed(texts, descriptor)
        if self.on_query is not None and texts == ["trigger retrieval race"]:
            self.on_query()
        return vectors


def test_coverage_includes_eligible_document_without_current_chunks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        ready = _prepare_document(
            client,
            text=_long_page("Setup ready"),
            source_url="https://publisher.example/ready.pdf",
        )
        missing = _upload(
            client,
            _pdf_with_pages(_long_page("Setup new")),
            source_url="https://publisher.example/new.pdf",
        )

    service = _service(provider)
    service.build(ready["id"])
    result = service.retrieve(
        bgg_id=900001,
        query="setup",
        requested_language="it",
        document_type="rulebook",
        version_label=None,
        edition=None,
        top_k=5,
        min_score=-1.0,
    )

    assert result["coverage"]["current_document_count"] == 2
    assert result["coverage"]["embedded_document_count"] == 1
    assert result["coverage"]["missing_document_ids"] == [missing["id"]]


def test_invalidated_official_document_stays_missing_during_lower_trust_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        official = _prepare_document(
            client,
            text=_long_page("Setup official"),
            language="it",
            source_url="https://publisher.example/official.pdf",
        )
        community = _upload(
            client,
            _pdf_with_pages(_long_page("Setup community")),
            language="it",
            version_label="community-v1",
            edition="Community",
            official=False,
            source_url="https://community.example/rules.pdf",
        )
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute(
                """
                UPDATE game_documents
                SET source_kind = 'community',
                    source_provider = 'community-test'
                WHERE id = ?
                """,
                (community["id"],),
            )
            connection.commit()
        assert client.post(
            f"/api/documents/{community['id']}/ingest"
        ).status_code == 200
        assert client.post(
            f"/api/documents/{community['id']}/chunks/build"
        ).status_code == 200

    service = _service(provider)
    service.build(official["id"])
    service.build(community["id"])

    with TestClient(app) as client:
        forced = client.post(
            f"/api/documents/{official['id']}/ingest?force=true"
        )
        assert forced.status_code == 200

    result = service.retrieve(
        bgg_id=900001,
        query="setup",
        requested_language="it",
        document_type="rulebook",
        version_label=None,
        edition=None,
        top_k=5,
        min_score=-1.0,
    )
    assert official["id"] in result["coverage"]["missing_document_ids"]
    assert result["coverage"]["embedded_document_count"] == 1
    assert result["results"]
    assert {
        item["document"]["id"] for item in result["results"]
    } == {community["id"]}
    assert result["policy"]["selected_tier"]["name"] == (
        "community-requested-language"
    )


def test_retrieval_aborts_if_source_changes_during_query_embedding(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = MutatingQueryProvider()
    with TestClient(app) as client:
        _import_game(client)
        document = _prepare_document(
            client,
            text=_long_page("Setup race"),
            source_url="https://publisher.example/race.pdf",
        )

    service = _service(provider)
    service.build(document["id"])

    def invalidate_source() -> None:
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute(
                "UPDATE game_documents SET language = 'en' WHERE id = ?",
                (document["id"],),
            )
            connection.commit()

    provider.on_query = invalidate_source
    with pytest.raises(EmbeddingConflict, match="Retrieval source changed"):
        service.retrieve(
            bgg_id=900001,
            query="trigger retrieval race",
            requested_language="it",
            document_type="rulebook",
            version_label=None,
            edition=None,
            top_k=5,
            min_score=-1.0,
        )


def test_atomic_snapshot_blocks_new_eligible_document_between_coverage_and_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    provider = FakeProvider()
    with TestClient(app) as client:
        _import_game(client)
        ready = _prepare_document(
            client,
            text=_long_page("Atomic snapshot"),
            source_url="https://publisher.example/atomic.pdf",
        )

    service = _service(provider)
    service.build(ready["id"])
    descriptor = provider.describe()
    _, config_sha256 = _descriptor_config(descriptor)

    writer_started = threading.Event()
    writer_committed = threading.Event()
    writer_thread: list[threading.Thread] = []
    original_candidate_rows = service._candidate_rows

    def writer() -> None:
        writer_started.set()
        with sqlite3.connect(settings.database_path, timeout=10) as connection:
            connection.execute(
                """
                INSERT INTO game_documents (
                    id, board_game_id, document_type, language, title,
                    original_filename, storage_path, sha256, size_bytes,
                    mime_type, source_kind, source_provider, source_url,
                    is_official, version_label, edition, published_at,
                    provenance_json, created_at, updated_at
                )
                SELECT
                    'atomic-race-doc', board_game_id, document_type, language,
                    'Atomic race doc', 'atomic-race.pdf',
                    '900001/atomic-race.pdf',
                    ?, size_bytes, mime_type, source_kind, source_provider,
                    source_url, is_official, version_label, edition,
                    published_at, provenance_json, created_at, updated_at
                FROM game_documents
                WHERE id = ?
                """,
                ("f" * 64, ready["id"]),
            )
            connection.commit()
        writer_committed.set()

    started_once = False

    def candidate_rows_with_writer(**kwargs):
        nonlocal started_once
        if not started_once:
            started_once = True
            thread = threading.Thread(target=writer)
            writer_thread.append(thread)
            thread.start()
            assert writer_started.wait(timeout=5)
            time.sleep(0.1)
            assert not writer_committed.is_set()
        return original_candidate_rows(**kwargs)

    monkeypatch.setattr(service, "_candidate_rows", candidate_rows_with_writer)
    coverage, _, _, _ = service._snapshot_state(
        board_game_id=1,
        descriptor=descriptor,
        config_sha256=config_sha256,
        document_type="rulebook",
        version_label=None,
        edition=None,
    )
    assert coverage["current_document_count"] == 1

    writer_thread[0].join(timeout=10)
    assert writer_committed.is_set()

    monkeypatch.setattr(service, "_candidate_rows", original_candidate_rows)
    coverage_after, _, _, _ = service._snapshot_state(
        board_game_id=1,
        descriptor=descriptor,
        config_sha256=config_sha256,
        document_type="rulebook",
        version_label=None,
        edition=None,
    )
    assert coverage_after["current_document_count"] == 2
    assert "atomic-race-doc" in coverage_after["missing_document_ids"]
