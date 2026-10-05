from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from boardgamecompanion.database import Database
from boardgamecompanion.document_indexing import DocumentIndexingService, enqueue_document_index
from boardgamecompanion.embedding_retrieval import EmbeddingProviderError
from boardgamecompanion.main import (
    build_document_embeddings_with_failover,
    run_document_auto_index,
)


def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    now = datetime.now(UTC).isoformat()
    with db.transaction() as connection:
        connection.execute(
            """INSERT INTO board_games
               (bgg_id,title,source_metadata_json,created_at,updated_at)
               VALUES (1,'Indexed Game','{}',?,?)""", (now, now)
        )
        game_id = connection.execute("SELECT id FROM board_games WHERE bgg_id=1").fetchone()["id"]
        connection.execute(
            """INSERT INTO game_documents
               (id,board_game_id,document_type,language,title,original_filename,storage_path,sha256,
                size_bytes,mime_type,source_kind,is_official,provenance_json,created_at,updated_at)
               VALUES ('doc-1',?,'rulebook','it','Regolamento','rules.pdf','1/rules.pdf',?,10,
                       'application/pdf','rulebook_fetch',1,'{}',?,?)""",
            (game_id, hashlib.sha256(b"pdf").hexdigest(), now, now),
        )
    return db


class Stage:
    def __init__(self, name: str, calls: list[str], fail: bool = False):
        self.name = name
        self.calls = calls
        self.fail = fail

    def __call__(self, document_id: str):
        self.calls.append(self.name)
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        return {"document_id": document_id, "stage": self.name}


def test_auto_index_runs_ingest_chunks_embeddings_and_is_idempotent(tmp_path: Path) -> None:
    db = database(tmp_path)
    calls: list[str] = []
    service = DocumentIndexingService(
        db,
        ingest=Stage("ingest", calls),
        chunks=Stage("chunks", calls),
        embeddings=Stage("embeddings", calls),
    )
    assert service.synchronize_documents() == 1
    assert service.synchronize_documents() == 0

    result = service.run("doc-1")
    restarted = DocumentIndexingService(
        db,
        ingest=Stage("ingest", calls),
        chunks=Stage("chunks", calls),
        embeddings=Stage("embeddings", calls),
    )

    assert calls == ["ingest", "chunks", "embeddings"]
    assert result["status"] == "succeeded"
    assert restarted.status(document_id="doc-1")["items"][0]["stage"] == "complete"
    assert restarted.run_due()["attempted"] == 0


def test_auto_index_failure_is_persisted_and_retried_from_idempotent_services(tmp_path: Path) -> None:
    db = database(tmp_path)
    calls: list[str] = []
    service = DocumentIndexingService(
        db,
        ingest=Stage("ingest", calls),
        chunks=Stage("chunks", calls, fail=True),
        embeddings=Stage("embeddings", calls),
        retry_base_seconds=60,
        retry_max_seconds=60,
    )
    service.synchronize_documents()
    with pytest.raises(RuntimeError, match="chunks failed"):
        service.run("doc-1")
    state = service.status(document_id="doc-1")["items"][0]
    assert state["status"] == "failed" and state["stage"] == "chunks"
    assert state["next_attempt_at"] is not None


def test_enqueue_is_transactional_and_duplicate_safe(tmp_path: Path) -> None:
    db = database(tmp_path)
    with db.transaction(immediate=True) as connection:
        assert enqueue_document_index(connection, "doc-1") is True
        assert enqueue_document_index(connection, "doc-1") is False
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) AS count FROM document_index_jobs").fetchone()["count"] == 1


def test_expired_running_job_is_reclaimed_after_restart(tmp_path: Path) -> None:
    db = database(tmp_path)
    calls: list[str] = []
    first = DocumentIndexingService(
        db,
        ingest=Stage("ingest", calls),
        chunks=Stage("chunks", calls),
        embeddings=Stage("embeddings", calls),
    )
    first.synchronize_documents()
    with db.transaction(immediate=True) as connection:
        connection.execute(
            """UPDATE document_index_jobs SET status='running',stage='chunks',
               lease_owner='dead-worker',lease_until='2000-01-01T00:00:00+00:00'"""
        )
    restarted = DocumentIndexingService(
        db,
        ingest=Stage("ingest", calls),
        chunks=Stage("chunks", calls),
        embeddings=Stage("embeddings", calls),
    )
    result = restarted.run_due()
    assert result["succeeded"] == 1
    assert calls == ["ingest", "chunks", "embeddings"]


def test_auto_index_maps_embedding_provider_failure_to_503(monkeypatch) -> None:
    class FailingIndexService:
        def run(self, document_id: str, *, force: bool = True):
            raise EmbeddingProviderError(
                "Gemini embedding request failed with HTTP 429 after retries"
            )

    monkeypatch.setattr(
        "boardgamecompanion.main.get_document_indexing_service",
        lambda: FailingIndexService(),
    )

    with pytest.raises(HTTPException) as captured:
        run_document_auto_index("doc-1")

    assert captured.value.status_code == 503
    assert captured.value.detail == (
        "Gemini embedding request failed with HTTP 429 after retries"
    )


def test_embedding_failover_promotes_qwen_after_gemini_failure(monkeypatch) -> None:
    class FakeDatabase:
        def initialize(self) -> None:
            pass

    class FakeService:
        def __init__(self, provider: str):
            self.provider = provider

        def build(self, document_id: str, *, force: bool = False):
            if self.provider == "gemini":
                raise EmbeddingProviderError(
                    "Gemini embedding request failed with HTTP 429 after retries"
                )
            return {
                "created": True,
                "embedding_index": {
                    "document_id": document_id,
                    "provider": "ollama",
                    "model": "qwen3-embedding:0.6b",
                    "chunk_count": 42,
                },
            }

    database = FakeDatabase()
    rag = SimpleNamespace(
        embedding_provider_order=("gemini", "ollama"),
        ollama_embedding_model="qwen3-embedding:0.6b",
    )
    activated: list[str] = []

    monkeypatch.setattr(
        "boardgamecompanion.main.get_database",
        lambda: database,
    )
    monkeypatch.setattr(
        "boardgamecompanion.main.resolve_rag_settings",
        lambda _database: rag,
    )
    monkeypatch.setattr(
        "boardgamecompanion.main._embedding_retrieval_service_for",
        lambda _database, _rag, selected: FakeService(selected),
    )
    monkeypatch.setattr(
        "boardgamecompanion.main.activate_embedding_provider",
        lambda _database, provider: activated.append(provider),
    )
    monkeypatch.setattr(
        "boardgamecompanion.main.requeue_document_indexes_for_provider_change",
        lambda _database, *, exclude_document_id: 3,
    )

    result = build_document_embeddings_with_failover("doc-1")

    assert result["active_provider"] == "ollama"
    assert result["provider_message"].startswith("Gemini failed")
    assert result["provider_message"].endswith("Qwen OK")
    assert result["requeued_documents"] == 3
    assert activated == ["ollama"]
    # activate_embedding_provider itself preserves the remaining configured providers.


def test_embedding_failover_reports_both_provider_failures(monkeypatch) -> None:
    class FakeDatabase:
        def initialize(self) -> None:
            pass

    class FailingService:
        def __init__(self, provider: str):
            self.provider = provider

        def build(self, document_id: str, *, force: bool = False):
            if self.provider == "gemini":
                raise EmbeddingProviderError(
                    "Gemini embedding request failed with HTTP 429 after retries"
                )
            raise EmbeddingProviderError("Ollama model qwen3-embedding:0.6b is unavailable")

    database = FakeDatabase()
    rag = SimpleNamespace(
        embedding_provider_order=("gemini", "ollama"),
        ollama_embedding_model="qwen3-embedding:0.6b",
    )

    monkeypatch.setattr(
        "boardgamecompanion.main.get_database",
        lambda: database,
    )
    monkeypatch.setattr(
        "boardgamecompanion.main.resolve_rag_settings",
        lambda _database: rag,
    )
    monkeypatch.setattr(
        "boardgamecompanion.main._embedding_retrieval_service_for",
        lambda _database, _rag, selected: FailingService(selected),
    )

    with pytest.raises(EmbeddingProviderError) as captured:
        build_document_embeddings_with_failover("doc-1")

    message = str(captured.value)
    assert "Gemini failed" in message
    assert "Qwen failed" in message
    assert "HTTP 429" in message
    assert "qwen3-embedding:0.6b" in message
