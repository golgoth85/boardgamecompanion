from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import sys
from array import array
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx

from boardgamecompanion.chunk_index import (
    CHUNKER_NAME,
    CHUNKER_VERSION,
    ChunkIndexCorruptSource,
    ChunkIndexDocumentNotFound,
    ChunkIndexService,
    ChunkIndexSourceNotReady,
)
from boardgamecompanion.database import Database

VECTOR_FORMAT = "f32le"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EmbeddingRetrievalError(RuntimeError):
    pass


class EmbeddingProviderError(EmbeddingRetrievalError):
    pass


class EmbeddingDocumentNotFound(EmbeddingRetrievalError):
    pass


class EmbeddingGameNotFound(EmbeddingRetrievalError):
    pass


class EmbeddingSourceNotReady(EmbeddingRetrievalError):
    pass


class EmbeddingConflict(EmbeddingRetrievalError):
    pass


class EmbeddingCorruptRecord(EmbeddingRetrievalError):
    pass


@dataclass(frozen=True)
class EmbeddingDescriptor:
    provider: str
    model: str
    model_digest: str
    requested_dimensions: int | None
    endpoint: str

    def config(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "model_digest": self.model_digest,
            "requested_dimensions": self.requested_dimensions,
            "endpoint": self.endpoint,
            "truncate": False,
        }


class EmbeddingProvider(Protocol):
    def describe(self) -> EmbeddingDescriptor: ...

    def embed(
        self,
        texts: list[str],
        descriptor: EmbeddingDescriptor,
    ) -> list[list[float]]: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _safe_json_object(
    raw: str | None,
    *,
    max_bytes: int = 64 * 1024,
) -> dict[str, Any]:
    if not raw or not isinstance(raw, str):
        raise EmbeddingCorruptRecord("Persisted JSON is missing")
    if len(raw.encode("utf-8")) > max_bytes:
        raise EmbeddingCorruptRecord("Persisted JSON exceeds the safety limit")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise EmbeddingCorruptRecord("Persisted JSON is invalid") from exc
    if not isinstance(value, dict):
        raise EmbeddingCorruptRecord("Persisted JSON is not an object")
    return value


def _normalize_vector(values: list[float]) -> list[float]:
    if not values:
        raise EmbeddingProviderError("Embedding vector is empty")
    normalized_values: list[float] = []
    total = 0.0
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise EmbeddingProviderError("Embedding vector contains non-numeric data") from exc
        if not math.isfinite(number):
            raise EmbeddingProviderError("Embedding vector contains non-finite data")
        normalized_values.append(number)
        total += number * number
    norm = math.sqrt(total)
    if not math.isfinite(norm) or norm <= 1e-12:
        raise EmbeddingProviderError("Embedding vector has zero norm")
    return [value / norm for value in normalized_values]


def _pack_vector(values: list[float]) -> bytes:
    packed = array("f", values)
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


def _unpack_vector(blob: bytes, dimensions: int) -> array:
    if dimensions <= 0 or len(blob) != dimensions * 4:
        raise EmbeddingCorruptRecord("Embedding vector byte length is invalid")
    values = array("f")
    values.frombytes(blob)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != dimensions:
        raise EmbeddingCorruptRecord("Embedding vector dimension is invalid")
    total = 0.0
    for value in values:
        if not math.isfinite(value):
            raise EmbeddingCorruptRecord("Embedding vector contains non-finite data")
        total += float(value) * float(value)
    norm = math.sqrt(total)
    if not 0.995 <= norm <= 1.005:
        raise EmbeddingCorruptRecord("Embedding vector is not normalized")
    return values


def _dot(left: array, right: array) -> float:
    if len(left) != len(right):
        raise EmbeddingCorruptRecord("Embedding dimensions do not match")
    return sum(float(a) * float(b) for a, b in zip(left, right, strict=True))


def _descriptor_config(descriptor: EmbeddingDescriptor) -> tuple[str, str]:
    if not SHA256_RE.fullmatch(descriptor.model_digest):
        raise EmbeddingProviderError("Embedding model digest is invalid")
    raw = _canonical_json(descriptor.config())
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


class OllamaEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        requested_dimensions: int | None,
        timeout_seconds: float,
        verify_tls: bool,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.requested_dimensions = requested_dimensions
        self.timeout_seconds = float(timeout_seconds)
        self.verify_tls = bool(verify_tls)
        self._client = client
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("Ollama URL must start with http:// or https://")
        if not self.model:
            raise ValueError("Ollama embedding model is required")

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            if self._client is not None:
                response = self._client.request(method, path, **kwargs)
            else:
                with httpx.Client(
                    base_url=self.base_url,
                    timeout=self.timeout_seconds,
                    verify=self.verify_tls,
                ) as client:
                    response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            raise EmbeddingProviderError("Ollama embedding request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise EmbeddingProviderError(
                f"Ollama embedding request failed with HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError("Ollama embedding endpoint is unreachable") from exc

    def describe(self) -> EmbeddingDescriptor:
        response = self._request("GET", "/api/tags")
        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbeddingProviderError("Ollama model list returned invalid JSON") from exc
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise EmbeddingProviderError("Ollama model list is invalid")

        expected_names = {self.model}
        if ":" not in self.model:
            expected_names.add(f"{self.model}:latest")
        match: dict[str, Any] | None = None
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            model = item.get("model")
            if name in expected_names or model in expected_names:
                match = item
                break
        if match is None:
            raise EmbeddingProviderError(
                f"Ollama embedding model {self.model!r} is not installed"
            )

        digest = str(match.get("digest") or "").lower()
        if not SHA256_RE.fullmatch(digest):
            raise EmbeddingProviderError("Ollama model digest is missing or invalid")
        resolved_model = str(match.get("model") or match.get("name") or self.model)
        return EmbeddingDescriptor(
            provider="ollama",
            model=resolved_model,
            model_digest=digest,
            requested_dimensions=self.requested_dimensions,
            endpoint=self.base_url,
        )

    def embed(
        self,
        texts: list[str],
        descriptor: EmbeddingDescriptor,
    ) -> list[list[float]]:
        if not texts:
            return []
        body: dict[str, Any] = {
            "model": descriptor.model,
            "input": texts,
            "truncate": False,
        }
        if descriptor.requested_dimensions is not None:
            body["dimensions"] = descriptor.requested_dimensions
        response = self._request("POST", "/api/embed", json=body)
        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbeddingProviderError("Ollama embedding response is invalid JSON") from exc
        embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise EmbeddingProviderError("Ollama embedding response count is invalid")
        result: list[list[float]] = []
        for vector in embeddings:
            if not isinstance(vector, list):
                raise EmbeddingProviderError("Ollama embedding vector is invalid")
            result.append(_normalize_vector(vector))
        return result


def _input_set_sha256(chunk_run_id: str, chunks: list[dict[str, Any]]) -> str:
    return _sha256_json(
        {
            "chunk_run_id": chunk_run_id,
            "chunks": [
                {
                    "id": item["id"],
                    "chunk_key": item["chunk_key"],
                    "text_sha256": item["chunk"]["text_sha256"],
                }
                for item in chunks
            ],
        }
    )


def _row_to_run(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "board_game_id": row["board_game_id"],
        "chunk_run_id": row["chunk_run_id"],
        "provider": row["provider"],
        "model": row["model"],
        "model_digest": row["model_digest"],
        "embedding_config_sha256": row["embedding_config_sha256"],
        "input_set_sha256": row["input_set_sha256"],
        "dimensions": row["dimensions"],
        "vector_format": row["vector_format"],
        "chunk_count": row["chunk_count"],
        "created_at": row["created_at"],
    }


class EmbeddingRetrievalService:
    def __init__(
        self,
        database: Database,
        chunk_service: ChunkIndexService,
        provider: EmbeddingProvider,
        *,
        batch_size: int,
        max_candidates: int,
    ) -> None:
        self.database = database
        self.chunk_service = chunk_service
        self.provider = provider
        self.batch_size = int(batch_size)
        self.max_candidates = int(max_candidates)
        if self.batch_size <= 0:
            raise ValueError("Embedding batch size must be positive")
        if self.max_candidates <= 0:
            raise ValueError("Retrieval candidate limit must be positive")

    def _source(self, document_id: str) -> dict[str, Any]:
        try:
            status = self.chunk_service.status(document_id)
        except ChunkIndexDocumentNotFound as exc:
            raise EmbeddingDocumentNotFound(str(exc)) from exc
        except ChunkIndexSourceNotReady as exc:
            raise EmbeddingSourceNotReady(str(exc)) from exc
        except ChunkIndexCorruptSource as exc:
            raise EmbeddingCorruptRecord(str(exc)) from exc
        if status["current"] is None:
            raise EmbeddingSourceNotReady(
                "Document has no current P7B chunk index"
            )
        current = status["current"]
        chunk_run_id = str(current["id"])

        with self.database.connect() as connection:
            document = connection.execute(
                """
                SELECT *
                FROM game_documents
                WHERE id = ?
                """,
                (document_id,),
            ).fetchone()
            if document is None:
                raise EmbeddingDocumentNotFound(
                    f"Document {document_id} not found"
                )

        chunks: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self.chunk_service.list_chunks(
                document_id,
                limit=500,
                offset=offset,
            )
            summaries = page["items"]
            if not summaries:
                break
            for summary in summaries:
                try:
                    detail = self.chunk_service.get_chunk(summary["id"])
                except ChunkIndexCorruptSource as exc:
                    raise EmbeddingCorruptRecord(str(exc)) from exc
                if detail is None:
                    raise EmbeddingConflict(
                        "Chunk disappeared while preparing embeddings"
                    )
                if detail["chunk_run_id"] != chunk_run_id:
                    raise EmbeddingConflict(
                        "Chunk index changed while preparing embeddings"
                    )
                chunks.append(detail)
            offset += len(summaries)
            if offset >= int(page["count"]):
                break

        return {
            "document": dict(document),
            "chunk_run": current,
            "chunks": chunks,
            "input_set_sha256": _input_set_sha256(chunk_run_id, chunks),
        }

    def _current_run_in_connection(
        self,
        connection: sqlite3.Connection,
        *,
        document_id: str,
        chunk_run_id: str,
        descriptor: EmbeddingDescriptor,
        config_sha256: str,
        input_set_sha256: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT *
            FROM document_embedding_runs
            WHERE document_id = ?
              AND chunk_run_id = ?
              AND provider = ?
              AND model = ?
              AND model_digest = ?
              AND embedding_config_sha256 = ?
              AND input_set_sha256 = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (
                document_id,
                chunk_run_id,
                descriptor.provider,
                descriptor.model,
                descriptor.model_digest,
                config_sha256,
                input_set_sha256,
            ),
        ).fetchone()
        if row is None:
            return None
        count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM chunk_embeddings
            WHERE embedding_run_id = ?
            """,
            (row["id"],),
        ).fetchone()["count"]
        if int(count) != int(row["chunk_count"]):
            return None
        return _row_to_run(row)

    def _current_run(
        self,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return self._current_run_in_connection(connection, **kwargs)

    def _validate_source_locked(
        self,
        connection: sqlite3.Connection,
        source: dict[str, Any],
    ) -> None:
        chunk_run_id = source["chunk_run"]["id"]
        rows = connection.execute(
            """
            SELECT
                c.id,
                c.chunk_key,
                c.text,
                c.text_sha256,
                c.page_text_sha256,
                c.start_char,
                c.end_char,
                p.text AS page_text,
                p.text_sha256 AS current_page_text_sha256
            FROM document_chunks c
            LEFT JOIN document_pages p ON p.id = c.page_id
            WHERE c.document_id = ? AND c.chunk_run_id = ?
            ORDER BY c.page_number, c.chunk_index, c.id
            """,
            (source["document"]["id"], chunk_run_id),
        ).fetchall()
        if len(rows) != len(source["chunks"]):
            raise EmbeddingConflict("P7B chunk set changed during embedding")

        current_items: list[dict[str, Any]] = []
        source_by_id = {item["id"]: item for item in source["chunks"]}
        for row in rows:
            text = row["text"]
            if not isinstance(text, str):
                raise EmbeddingCorruptRecord("Persisted chunk text is invalid")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest != row["text_sha256"]:
                raise EmbeddingCorruptRecord("Persisted chunk text digest is invalid")
            page_text = row["page_text"]
            if not isinstance(page_text, str):
                raise EmbeddingCorruptRecord("Persisted chunk page is missing")
            if (
                row["current_page_text_sha256"] != row["page_text_sha256"]
                or hashlib.sha256(page_text.encode("utf-8")).hexdigest()
                != row["page_text_sha256"]
            ):
                raise EmbeddingCorruptRecord(
                    "Persisted chunk page digest is invalid"
                )
            start_char = int(row["start_char"])
            end_char = int(row["end_char"])
            if (
                end_char > len(page_text)
                or page_text[start_char:end_char] != text
            ):
                raise EmbeddingCorruptRecord(
                    "Persisted chunk does not match its page span"
                )
            expected = source_by_id.get(row["id"])
            if expected is None:
                raise EmbeddingConflict("P7B chunk identity changed during embedding")
            if (
                row["chunk_key"] != expected["chunk_key"]
                or row["text_sha256"] != expected["chunk"]["text_sha256"]
            ):
                raise EmbeddingConflict("P7B chunk content changed during embedding")
            current_items.append(
                {
                    "id": row["id"],
                    "chunk_key": row["chunk_key"],
                    "chunk": {"text_sha256": row["text_sha256"]},
                }
            )

        current_sha = _input_set_sha256(chunk_run_id, current_items)
        if current_sha != source["input_set_sha256"]:
            raise EmbeddingConflict("P7B chunk set changed during embedding")

    def build(
        self,
        document_id: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        source = self._source(document_id)
        descriptor = self.provider.describe()
        config_json, config_sha256 = _descriptor_config(descriptor)
        chunk_run_id = str(source["chunk_run"]["id"])
        input_set_sha256 = str(source["input_set_sha256"])

        if not force:
            current = self._current_run(
                document_id=document_id,
                chunk_run_id=chunk_run_id,
                descriptor=descriptor,
                config_sha256=config_sha256,
                input_set_sha256=input_set_sha256,
            )
            if current is not None:
                return {"created": False, "embedding_index": current}

        chunks = source["chunks"]
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), self.batch_size):
            batch = chunks[start : start + self.batch_size]
            raw_vectors = self.provider.embed(
                [item["text"] for item in batch],
                descriptor,
            )
            if len(raw_vectors) != len(batch):
                raise EmbeddingProviderError("Embedding provider returned wrong batch size")
            vectors.extend(_normalize_vector(vector) for vector in raw_vectors)

        descriptor_after = self.provider.describe()
        if descriptor_after != descriptor:
            raise EmbeddingConflict(
                "Embedding model changed while document embeddings were generated"
            )

        dimensions: int | None = None
        prepared: list[dict[str, Any]] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if dimensions is None:
                dimensions = len(vector)
            elif len(vector) != dimensions:
                raise EmbeddingProviderError(
                    "Embedding provider returned inconsistent dimensions"
                )
            if (
                descriptor.requested_dimensions is not None
                and len(vector) != descriptor.requested_dimensions
            ):
                raise EmbeddingProviderError(
                    "Embedding provider ignored requested dimensions"
                )
            blob = _pack_vector(vector)
            prepared.append(
                {
                    "chunk": chunk,
                    "blob": blob,
                    "vector_sha256": hashlib.sha256(blob).hexdigest(),
                }
            )

        if not chunks and descriptor.requested_dimensions is not None:
            dimensions = descriptor.requested_dimensions

        run_id = str(uuid4())
        created_at = _now()
        document = source["document"]

        with self.database.transaction(immediate=True) as connection:
            self._validate_source_locked(connection, source)
            if not force:
                current = self._current_run_in_connection(
                    connection,
                    document_id=document_id,
                    chunk_run_id=chunk_run_id,
                    descriptor=descriptor,
                    config_sha256=config_sha256,
                    input_set_sha256=input_set_sha256,
                )
                if current is not None:
                    return {"created": False, "embedding_index": current}

            connection.execute(
                """
                INSERT INTO document_embedding_runs (
                    id, document_id, board_game_id, chunk_run_id,
                    provider, model, model_digest,
                    embedding_config_json, embedding_config_sha256,
                    input_set_sha256, dimensions, vector_format,
                    chunk_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    document_id,
                    document["board_game_id"],
                    chunk_run_id,
                    descriptor.provider,
                    descriptor.model,
                    descriptor.model_digest,
                    config_json,
                    config_sha256,
                    input_set_sha256,
                    dimensions,
                    VECTOR_FORMAT,
                    len(chunks),
                    created_at,
                ),
            )
            connection.execute(
                """
                DELETE FROM chunk_embeddings
                WHERE document_id = ?
                  AND provider = ?
                  AND model = ?
                """,
                (document_id, descriptor.provider, descriptor.model),
            )

            for item in prepared:
                chunk = item["chunk"]
                vector_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        (
                            "boardgamecompanion:embedding:"
                            f"{chunk['id']}:{descriptor.provider}:"
                            f"{descriptor.model}:{descriptor.model_digest}:"
                            f"{config_sha256}"
                        ),
                    )
                )
                connection.execute(
                    """
                    INSERT INTO chunk_embeddings (
                        id, embedding_run_id, chunk_id,
                        board_game_id, document_id, chunk_run_id,
                        provider, model, model_digest,
                        embedding_config_sha256, dimensions,
                        vector_format, vector_blob, vector_sha256,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vector_id,
                        run_id,
                        chunk["id"],
                        document["board_game_id"],
                        document_id,
                        chunk_run_id,
                        descriptor.provider,
                        descriptor.model,
                        descriptor.model_digest,
                        config_sha256,
                        dimensions,
                        VECTOR_FORMAT,
                        item["blob"],
                        item["vector_sha256"],
                        created_at,
                    ),
                )

            run_row = connection.execute(
                "SELECT * FROM document_embedding_runs WHERE id = ?",
                (run_id,),
            ).fetchone()

        assert run_row is not None
        return {"created": True, "embedding_index": _row_to_run(run_row)}

    def status(self, document_id: str) -> dict[str, Any]:
        source = self._source(document_id)
        descriptor = self.provider.describe()
        _, config_sha256 = _descriptor_config(descriptor)
        current = self._current_run(
            document_id=document_id,
            chunk_run_id=source["chunk_run"]["id"],
            descriptor=descriptor,
            config_sha256=config_sha256,
            input_set_sha256=source["input_set_sha256"],
        )
        with self.database.connect() as connection:
            latest = connection.execute(
                """
                SELECT *
                FROM document_embedding_runs
                WHERE document_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        return {
            "document_id": document_id,
            "chunk_run_id": source["chunk_run"]["id"],
            "chunk_count": len(source["chunks"]),
            "provider": descriptor.provider,
            "model": descriptor.model,
            "model_digest": descriptor.model_digest,
            "current": current,
            "latest_run": _row_to_run(latest),
        }

    @staticmethod
    def _tier(row: sqlite3.Row, requested_language: str | None) -> tuple[int, str]:
        language = str(row["language"] or "und").lower()
        official = bool(row["is_official"])
        source_kind = str(row["source_kind"] or "")

        if requested_language:
            requested = requested_language.lower()
            if official and language == requested:
                return 0, "official-requested-language"
            if official and requested != "en" and language == "en":
                return 1, "official-english"
            if official:
                return 2, "official-other-language"
            if source_kind == "manual_upload" and language == requested:
                return 3, "user-supplied-requested-language"
            if source_kind == "manual_upload":
                return 4, "user-supplied"
            if source_kind == "community" and language == requested:
                return 5, "community-requested-language"
            if source_kind == "community" and language == "en":
                return 6, "community-english"
            if source_kind == "community":
                return 7, "community-other-language"
            return 99, "excluded-untrusted"

        if official:
            return 0, "official"
        if source_kind == "manual_upload":
            return 1, "user-supplied"
        if source_kind == "community":
            return 2, "community"
        return 99, "excluded-untrusted"

    def _eligible_document_ids(
        self,
        *,
        board_game_id: int,
        document_type: str | None,
        version_label: str | None,
        edition: str | None,
    ) -> list[str]:
        clauses = [
            "board_game_id = ?",
            "(is_official = 1 OR source_kind IN ('manual_upload', 'community'))",
        ]
        params: list[Any] = [board_game_id]
        if document_type is not None:
            clauses.append("document_type = ?")
            params.append(document_type)
        if version_label is not None:
            clauses.append("version_label = ?")
            params.append(version_label)
        if edition is not None:
            clauses.append("edition = ?")
            params.append(edition)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id
                FROM game_documents
                WHERE {" AND ".join(clauses)}
                ORDER BY id
                """,
                params,
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def _coverage_state(
        self,
        *,
        board_game_id: int,
        descriptor: EmbeddingDescriptor,
        config_sha256: str,
        document_type: str | None,
        version_label: str | None,
        edition: str | None,
    ) -> tuple[dict[str, Any], str]:
        document_ids = self._eligible_document_ids(
            board_game_id=board_game_id,
            document_type=document_type,
            version_label=version_label,
            edition=edition,
        )
        states: list[dict[str, Any]] = []
        ready_document_ids: list[str] = []
        missing_document_ids: list[str] = []

        for document_id in document_ids:
            try:
                source = self._source(document_id)
            except EmbeddingSourceNotReady:
                states.append(
                    {
                        "document_id": document_id,
                        "status": "p7b_not_ready",
                    }
                )
                missing_document_ids.append(document_id)
                continue
            except EmbeddingDocumentNotFound as exc:
                raise EmbeddingConflict(
                    "Eligible document changed while retrieval coverage was read"
                ) from exc

            current = self._current_run(
                document_id=document_id,
                chunk_run_id=str(source["chunk_run"]["id"]),
                descriptor=descriptor,
                config_sha256=config_sha256,
                input_set_sha256=str(source["input_set_sha256"]),
            )
            if current is None:
                states.append(
                    {
                        "document_id": document_id,
                        "status": "p7c_not_ready",
                        "chunk_run_id": source["chunk_run"]["id"],
                        "input_set_sha256": source["input_set_sha256"],
                    }
                )
                missing_document_ids.append(document_id)
                continue

            states.append(
                {
                    "document_id": document_id,
                    "status": "ready",
                    "chunk_run_id": source["chunk_run"]["id"],
                    "input_set_sha256": source["input_set_sha256"],
                    "embedding_run_id": current["id"],
                    "embedding_config_sha256": current[
                        "embedding_config_sha256"
                    ],
                    "model_digest": current["model_digest"],
                }
            )
            ready_document_ids.append(document_id)

        coverage = {
            "current_document_count": len(document_ids),
            "embedded_document_count": len(ready_document_ids),
            "missing_document_ids": sorted(missing_document_ids),
        }
        return coverage, _sha256_json(states)

    @staticmethod
    def _candidate_set_sha256(rows: list[sqlite3.Row]) -> str:
        return _sha256_json(
            [
                {
                    "embedding_id": row["embedding_id"],
                    "embedding_run_id": row["embedding_run_id"],
                    "chunk_id": row["id"],
                    "chunk_key": row["chunk_key"],
                    "chunk_run_id": row["chunk_run_id"],
                    "document_id": row["document_id"],
                    "document_metadata_sha256": row[
                        "document_metadata_sha256"
                    ],
                    "parse_run_id": row["parse_run_id"],
                    "page_id": row["page_id"],
                    "page_number": row["page_number"],
                    "page_text_sha256": row["page_text_sha256"],
                    "text_sha256": row["text_sha256"],
                    "vector_sha256": row["vector_sha256"],
                    "published_at": row["published_at"],
                }
                for row in rows
            ]
        )

    def validate_retrieval_current(
        self,
        retrieval_payload: dict[str, Any],
    ) -> None:
        snapshot = retrieval_payload.get("currentness")
        if not isinstance(snapshot, dict):
            raise EmbeddingConflict("Retrieval currentness token is missing")
        filters = snapshot.get("filters")
        if not isinstance(filters, dict):
            raise EmbeddingConflict("Retrieval currentness filters are invalid")

        descriptor = self.provider.describe()
        _, config_sha256 = _descriptor_config(descriptor)
        if (
            descriptor.provider != snapshot.get("provider")
            or descriptor.model != snapshot.get("model")
            or descriptor.model_digest != snapshot.get("model_digest")
            or config_sha256 != snapshot.get("embedding_config_sha256")
        ):
            raise EmbeddingConflict(
                "Embedding model changed after retrieval evidence was selected"
            )

        try:
            board_game_id = int(snapshot["board_game_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingConflict(
                "Retrieval currentness game identity is invalid"
            ) from exc

        coverage, coverage_sha256 = self._coverage_state(
            board_game_id=board_game_id,
            descriptor=descriptor,
            config_sha256=config_sha256,
            document_type=filters.get("document_type"),
            version_label=filters.get("version_label"),
            edition=filters.get("edition"),
        )
        rows = self._candidate_rows(
            board_game_id=board_game_id,
            descriptor=descriptor,
            config_sha256=config_sha256,
            document_type=filters.get("document_type"),
            version_label=filters.get("version_label"),
            edition=filters.get("edition"),
        )
        candidate_set_sha256 = self._candidate_set_sha256(rows)
        if (
            coverage_sha256 != snapshot.get("coverage_sha256")
            or candidate_set_sha256 != snapshot.get("candidate_set_sha256")
            or coverage != retrieval_payload.get("coverage")
        ):
            raise EmbeddingConflict(
                "Retrieval evidence changed after it was selected"
            )

    def _candidate_rows(
        self,
        *,
        board_game_id: int,
        descriptor: EmbeddingDescriptor,
        config_sha256: str,
        document_type: str | None,
        version_label: str | None,
        edition: str | None,
    ) -> list[sqlite3.Row]:
        clauses = [
            "c.board_game_id = ?",
            "c.chunker_name = ?",
            "c.chunker_version = ?",
            "c.chunker_config_json = ?",
            "e.provider = ?",
            "e.model = ?",
            "e.model_digest = ?",
            "e.embedding_config_sha256 = ?",
        ]
        params: list[Any] = [
            board_game_id,
            CHUNKER_NAME,
            CHUNKER_VERSION,
            self.chunk_service.config_json,
            descriptor.provider,
            descriptor.model,
            descriptor.model_digest,
            config_sha256,
        ]
        if document_type is not None:
            clauses.append("c.document_type = ?")
            params.append(document_type)
        if version_label is not None:
            clauses.append("c.version_label = ?")
            params.append(version_label)
        if edition is not None:
            clauses.append("c.edition = ?")
            params.append(edition)

        where = " AND ".join(clauses)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    e.id AS embedding_id,
                    e.embedding_run_id,
                    e.dimensions,
                    e.vector_blob,
                    e.vector_sha256,
                    c.*,
                    d.published_at,
                    g.bgg_id,
                    g.title AS game_title,
                    p.document_id AS current_page_document_id,
                    p.parse_run_id AS current_page_parse_run_id,
                    p.page_number AS current_page_number,
                    p.text AS current_page_text,
                    p.text_sha256 AS current_page_text_sha256
                FROM chunk_embeddings e
                JOIN document_chunks c ON c.id = e.chunk_id
                JOIN game_documents d ON d.id = c.document_id
                JOIN board_games g ON g.id = c.board_game_id
                LEFT JOIN document_pages p ON p.id = c.page_id
                WHERE {where}
                ORDER BY c.document_id, c.page_number, c.chunk_index
                LIMIT ?
                """,
                [*params, self.max_candidates + 1],
            ).fetchall()
        if len(rows) > self.max_candidates:
            raise EmbeddingConflict(
                "Retrieval candidate limit exceeded for this game"
            )
        return rows

    @staticmethod
    def _validate_candidate(row: sqlite3.Row) -> None:
        text = row["text"]
        if not isinstance(text, str):
            raise EmbeddingCorruptRecord("Candidate chunk text is invalid")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != row["text_sha256"]:
            raise EmbeddingCorruptRecord("Candidate chunk text digest is invalid")

        page_text = row["current_page_text"]
        if not isinstance(page_text, str):
            raise EmbeddingCorruptRecord("Candidate page is missing or invalid")
        if (
            row["current_page_document_id"] != row["document_id"]
            or row["current_page_parse_run_id"] != row["parse_run_id"]
            or row["current_page_number"] != row["page_number"]
            or row["current_page_text_sha256"] != row["page_text_sha256"]
        ):
            raise EmbeddingCorruptRecord("Candidate page provenance is invalid")
        if (
            hashlib.sha256(page_text.encode("utf-8")).hexdigest()
            != row["page_text_sha256"]
        ):
            raise EmbeddingCorruptRecord("Candidate page text digest is invalid")
        start_char = int(row["start_char"])
        end_char = int(row["end_char"])
        if end_char > len(page_text) or page_text[start_char:end_char] != text:
            raise EmbeddingCorruptRecord(
                "Candidate chunk does not match its declared page span"
            )

        try:
            provenance = json.loads(row["document_provenance_json"])
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise EmbeddingCorruptRecord("Candidate document provenance is invalid") from exc
        if not isinstance(provenance, dict):
            raise EmbeddingCorruptRecord("Candidate document provenance is invalid")

        metadata = {
            "board_game_id": row["board_game_id"],
            "document_id": row["document_id"],
            "document_sha256": row["document_sha256"],
            "document_type": row["document_type"],
            "language": row["language"],
            "version_label": row["version_label"],
            "edition": row["edition"],
            "source_kind": row["source_kind"],
            "source_provider": row["source_provider"],
            "source_url": row["source_url"],
            "is_official": bool(row["is_official"]),
            "provenance": provenance,
        }
        if _sha256_json(metadata) != row["document_metadata_sha256"]:
            raise EmbeddingCorruptRecord("Candidate document metadata digest is invalid")

        chunker_config = _safe_json_object(row["chunker_config_json"])
        identity = {
            "document_id": row["document_id"],
            "document_sha256": row["document_sha256"],
            "page_id": row["page_id"],
            "page_number": row["page_number"],
            "page_text_sha256": row["page_text_sha256"],
            "chunk_index": row["chunk_index"],
            "start_char": row["start_char"],
            "end_char": row["end_char"],
            "text_sha256": row["text_sha256"],
            "chunker_name": row["chunker_name"],
            "chunker_version": row["chunker_version"],
            "chunker_config": chunker_config,
        }
        expected_key = _sha256_json(identity)
        if expected_key != row["chunk_key"]:
            raise EmbeddingCorruptRecord("Candidate chunk identity is invalid")
        expected_id = str(
            uuid5(
                NAMESPACE_URL,
                f"boardgamecompanion:chunk:{expected_key}",
            )
        )
        if expected_id != row["id"]:
            raise EmbeddingCorruptRecord("Candidate chunk identifier is invalid")

        blob = row["vector_blob"]
        if not isinstance(blob, bytes):
            raise EmbeddingCorruptRecord("Embedding vector blob is invalid")
        if hashlib.sha256(blob).hexdigest() != row["vector_sha256"]:
            raise EmbeddingCorruptRecord("Embedding vector digest is invalid")

    def retrieve(
        self,
        *,
        bgg_id: int,
        query: str,
        requested_language: str | None,
        document_type: str | None,
        version_label: str | None,
        edition: str | None,
        top_k: int,
        min_score: float,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            game = connection.execute(
                "SELECT id, bgg_id, title FROM board_games WHERE bgg_id = ?",
                (bgg_id,),
            ).fetchone()
        if game is None:
            raise EmbeddingGameNotFound(f"Board game {bgg_id} not found")

        descriptor = self.provider.describe()
        _, config_sha256 = _descriptor_config(descriptor)
        coverage, coverage_sha256 = self._coverage_state(
            board_game_id=game["id"],
            descriptor=descriptor,
            config_sha256=config_sha256,
            document_type=document_type,
            version_label=version_label,
            edition=edition,
        )
        rows = self._candidate_rows(
            board_game_id=game["id"],
            descriptor=descriptor,
            config_sha256=config_sha256,
            document_type=document_type,
            version_label=version_label,
            edition=edition,
        )
        candidate_set_sha256 = self._candidate_set_sha256(rows)
        currentness = {
            "board_game_id": game["id"],
            "provider": descriptor.provider,
            "model": descriptor.model,
            "model_digest": descriptor.model_digest,
            "embedding_config_sha256": config_sha256,
            "filters": {
                "document_type": document_type,
                "version_label": version_label,
                "edition": edition,
            },
            "coverage_sha256": coverage_sha256,
            "candidate_set_sha256": candidate_set_sha256,
        }

        if not rows:
            return {
                "game": dict(game),
                "query": query,
                "provider": descriptor.provider,
                "model": descriptor.model,
                "model_digest": descriptor.model_digest,
                "coverage": coverage,
                "currentness": currentness,
                "policy": {
                    "selected_tier": None,
                    "selected_cohort": None,
                    "excluded_conflicting_cohorts": [],
                },
                "results": [],
            }

        query_vectors = self.provider.embed([query], descriptor)
        if len(query_vectors) != 1:
            raise EmbeddingProviderError("Embedding provider returned wrong query count")
        query_vector_values = _normalize_vector(query_vectors[0])
        query_vector = array("f", query_vector_values)
        descriptor_after = self.provider.describe()
        if descriptor_after != descriptor:
            raise EmbeddingConflict(
                "Embedding model changed while query embedding was generated"
            )

        coverage_after, coverage_sha256_after = self._coverage_state(
            board_game_id=game["id"],
            descriptor=descriptor,
            config_sha256=config_sha256,
            document_type=document_type,
            version_label=version_label,
            edition=edition,
        )
        rows_after = self._candidate_rows(
            board_game_id=game["id"],
            descriptor=descriptor,
            config_sha256=config_sha256,
            document_type=document_type,
            version_label=version_label,
            edition=edition,
        )
        candidate_set_sha256_after = self._candidate_set_sha256(rows_after)
        if (
            coverage_sha256_after != coverage_sha256
            or candidate_set_sha256_after != candidate_set_sha256
        ):
            raise EmbeddingConflict(
                "Retrieval source changed while query embedding was generated"
            )
        coverage = coverage_after
        rows = rows_after

        scored: list[dict[str, Any]] = []
        for row in rows:
            self._validate_candidate(row)
            dimensions = int(row["dimensions"])
            if dimensions != len(query_vector):
                raise EmbeddingConflict(
                    "Stored embedding dimensions do not match query embedding"
                )
            vector = _unpack_vector(row["vector_blob"], dimensions)
            score = _dot(vector, query_vector)
            if score < min_score:
                continue
            tier, tier_name = self._tier(row, requested_language)
            if tier >= 99:
                continue
            scored.append(
                {
                    "row": row,
                    "score": score,
                    "tier": tier,
                    "tier_name": tier_name,
                }
            )

        if not scored:
            return {
                "game": dict(game),
                "query": query,
                "provider": descriptor.provider,
                "model": descriptor.model,
                "model_digest": descriptor.model_digest,
                "coverage": coverage,
                "currentness": currentness,
                "policy": {
                    "selected_tier": None,
                    "selected_cohort": None,
                    "excluded_conflicting_cohorts": [],
                },
                "results": [],
            }

        best_tier = min(item["tier"] for item in scored)
        tier_items = [item for item in scored if item["tier"] == best_tier]

        cohorts: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
        for item in tier_items:
            row = item["row"]
            key = (row["version_label"], row["edition"])
            cohorts.setdefault(key, []).append(item)

        def cohort_rank(
            entry: tuple[tuple[str | None, str | None], list[dict[str, Any]]]
        ) -> tuple[float, str, str, str]:
            key, items = entry
            best_score = max(float(item["score"]) for item in items)
            published = max(str(item["row"]["published_at"] or "") for item in items)
            return (
                best_score,
                published,
                str(key[0] or ""),
                str(key[1] or ""),
            )

        selected_key, selected_items = max(cohorts.items(), key=cohort_rank)
        excluded = [
            {
                "version_label": key[0],
                "edition": key[1],
                "candidate_count": len(items),
            }
            for key, items in cohorts.items()
            if key != selected_key
        ]

        selected_items.sort(
            key=lambda item: (
                -float(item["score"]),
                int(item["row"]["page_number"]),
                int(item["row"]["chunk_index"]),
                str(item["row"]["id"]),
            )
        )
        results: list[dict[str, Any]] = []
        for item in selected_items[:top_k]:
            row = item["row"]
            results.append(
                {
                    "score": float(item["score"]),
                    "chunk_id": row["id"],
                    "text": row["text"],
                    "game": {
                        "id": row["board_game_id"],
                        "bgg_id": row["bgg_id"],
                        "title": row["game_title"],
                    },
                    "document": {
                        "id": row["document_id"],
                        "document_type": row["document_type"],
                        "language": row["language"],
                        "version_label": row["version_label"],
                        "edition": row["edition"],
                        "published_at": row["published_at"],
                        "source_kind": row["source_kind"],
                        "source_provider": row["source_provider"],
                        "source_url": row["source_url"],
                        "official": bool(row["is_official"]),
                    },
                    "page": {
                        "id": row["page_id"],
                        "number": row["page_number"],
                        "text_sha256": row["page_text_sha256"],
                    },
                    "chunk": {
                        "index": row["chunk_index"],
                        "start_char": row["start_char"],
                        "end_char": row["end_char"],
                        "text_sha256": row["text_sha256"],
                    },
                }
            )

        return {
            "game": dict(game),
            "query": query,
            "provider": descriptor.provider,
            "model": descriptor.model,
            "model_digest": descriptor.model_digest,
            "coverage": coverage,
            "currentness": currentness,
            "policy": {
                "selected_tier": {
                    "rank": best_tier,
                    "name": selected_items[0]["tier_name"],
                },
                "selected_cohort": {
                    "version_label": selected_key[0],
                    "edition": selected_key[1],
                },
                "excluded_conflicting_cohorts": excluded,
            },
            "results": results,
        }
