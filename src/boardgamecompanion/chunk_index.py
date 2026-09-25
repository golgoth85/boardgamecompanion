from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from boardgamecompanion.database import Database
from boardgamecompanion.documents import DocumentError, DocumentStore

CHUNKER_NAME = "page-char-window"
CHUNKER_VERSION = "1"
MAX_PROVENANCE_BYTES = 128 * 1024
MAX_CONFIG_BYTES = 16 * 1024


class ChunkIndexError(RuntimeError):
    pass


class ChunkIndexDocumentNotFound(ChunkIndexError):
    pass


class ChunkIndexSourceNotReady(ChunkIndexError):
    pass


class ChunkIndexConflict(ChunkIndexError):
    pass


class ChunkIndexCorruptSource(ChunkIndexError):
    pass


@dataclass(frozen=True)
class ChunkSpan:
    index: int
    start_char: int
    end_char: int
    text: str


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
    max_bytes: int,
    strict: bool = False,
) -> dict[str, Any]:
    if not raw:
        return {}
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > max_bytes:
        if strict:
            raise ChunkIndexCorruptSource("Persisted JSON exceeds the safety limit")
        return {"corrupt": True}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        if strict:
            raise ChunkIndexCorruptSource("Persisted JSON is invalid") from exc
        return {"corrupt": True}
    if not isinstance(value, dict):
        if strict:
            raise ChunkIndexCorruptSource("Persisted JSON is not an object")
        return {"corrupt": True}
    return value


def _config_json(
    *,
    max_chars: int,
    overlap_chars: int,
    min_break_chars: int,
) -> str:
    raw = _canonical_json(
        {
            "max_chars": max_chars,
            "min_break_chars": min_break_chars,
            "overlap_chars": overlap_chars,
        }
    )
    if len(raw.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ChunkIndexError("Chunker configuration is unexpectedly large")
    return raw


def split_page_text(
    text: str,
    *,
    max_chars: int,
    overlap_chars: int,
    min_break_chars: int,
) -> list[ChunkSpan]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if min_break_chars <= 0 or min_break_chars > max_chars:
        raise ValueError("min_break_chars must be between 1 and max_chars")
    if overlap_chars < 0 or overlap_chars >= min_break_chars:
        raise ValueError("overlap_chars must be smaller than min_break_chars")
    if not text or not text.strip():
        return []

    spans: list[ChunkSpan] = []
    start = 0
    length = len(text)

    while start < length:
        hard_end = min(length, start + max_chars)
        end = hard_end

        if hard_end < length:
            floor = min(hard_end, start + min_break_chars)
            boundary: int | None = None
            for separator, include in (
                ("\n\n", 2),
                ("\n", 1),
                (". ", 1),
                ("? ", 1),
                ("! ", 1),
                ("; ", 1),
                (": ", 1),
                (" ", 0),
            ):
                position = text.rfind(separator, floor, hard_end)
                if position >= floor:
                    boundary = position + include
                    break
            if boundary is not None and boundary > start:
                end = boundary

        if end <= start:
            end = hard_end
        chunk_text = text[start:end]
        if chunk_text.strip():
            spans.append(
                ChunkSpan(
                    index=len(spans),
                    start_char=start,
                    end_char=end,
                    text=chunk_text,
                )
            )

        if end >= length:
            break
        next_start = max(start + 1, end - overlap_chars)
        if next_start <= start:
            next_start = end
        start = next_start

    return spans


def _validate_pages(
    pages: list[dict[str, Any]],
    parse_run: dict[str, Any],
) -> None:
    expected_text = int(parse_run["text_page_count"])
    expected_empty = int(parse_run["empty_page_count"])
    expected_error = int(parse_run["error_page_count"])
    expected_chars = int(parse_run["total_text_chars"])

    text_count = 0
    empty_count = 0
    error_count = 0
    total_chars = 0

    for expected_index, page in enumerate(pages):
        text = page["text"]
        if not isinstance(text, str):
            raise ChunkIndexCorruptSource("Persisted page text is invalid")
        if page["page_index"] != expected_index:
            raise ChunkIndexCorruptSource("Persisted page indexes are not contiguous")
        if page["page_number"] != expected_index + 1:
            raise ChunkIndexCorruptSource("Persisted page numbers are not contiguous")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if page["text_sha256"] != digest:
            raise ChunkIndexCorruptSource("Persisted page text digest is invalid")
        if int(page["char_count"]) != len(text):
            raise ChunkIndexCorruptSource("Persisted page character count is invalid")

        status = page["extraction_status"]
        if status == "text":
            if not text.strip():
                raise ChunkIndexCorruptSource("Text page has no extractable text")
            text_count += 1
        elif status == "empty":
            if text:
                raise ChunkIndexCorruptSource("Empty page unexpectedly contains text")
            empty_count += 1
        elif status == "error":
            if text:
                raise ChunkIndexCorruptSource("Error page unexpectedly contains text")
            error_count += 1
        else:
            raise ChunkIndexCorruptSource("Persisted page status is invalid")
        total_chars += len(text)

    if (
        text_count != expected_text
        or empty_count != expected_empty
        or error_count != expected_error
        or total_chars != expected_chars
    ):
        raise ChunkIndexCorruptSource("Persisted page totals do not match parse run")


def _page_set_digest(pages: list[dict[str, Any]]) -> str:
    return _sha256_json(
        [
            {
                "id": page["id"],
                "page_number": page["page_number"],
                "text_sha256": page["text_sha256"],
                "extraction_status": page["extraction_status"],
            }
            for page in pages
        ]
    )


def _document_metadata(
    document: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "board_game_id": document["board_game_id"],
        "document_id": document["id"],
        "document_sha256": document["sha256"],
        "document_type": document["document_type"],
        "language": document["language"],
        "version_label": document["version_label"],
        "edition": document["edition"],
        "source_kind": document["source_kind"],
        "source_provider": document["source_provider"],
        "source_url": document["source_url"],
        "is_official": bool(document["is_official"]),
        "provenance": provenance,
    }


def _row_to_run(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "board_game_id": row["board_game_id"],
        "parse_run_id": row["parse_run_id"],
        "document_sha256": row["document_sha256"],
        "document_metadata_sha256": row["document_metadata_sha256"],
        "source_pages_sha256": row["source_pages_sha256"],
        "chunker": {
            "name": row["chunker_name"],
            "version": row["chunker_version"],
            "config": _safe_json_object(
                row["chunker_config_json"],
                max_bytes=MAX_CONFIG_BYTES,
            ),
        },
        "page_count": row["page_count"],
        "indexed_page_count": row["indexed_page_count"],
        "chunk_count": row["chunk_count"],
        "total_chunk_chars": row["total_chunk_chars"],
        "created_at": row["created_at"],
    }


def _row_to_chunk(
    row: sqlite3.Row,
    *,
    include_text: bool,
) -> dict[str, Any]:
    provenance = _safe_json_object(
        row["document_provenance_json"],
        max_bytes=MAX_PROVENANCE_BYTES,
        strict=True,
    )
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
        raise ChunkIndexCorruptSource("Chunk document metadata digest is invalid")
    if row["document_sha256"] != row["run_document_sha256"]:
        raise ChunkIndexCorruptSource("Chunk document hash disagrees with chunk run")
    if row["document_metadata_sha256"] != row["run_metadata_sha256"]:
        raise ChunkIndexCorruptSource("Chunk metadata hash disagrees with chunk run")
    if (
        row["chunker_name"] != row["run_chunker_name"]
        or row["chunker_version"] != row["run_chunker_version"]
        or row["chunker_config_json"] != row["run_chunker_config_json"]
    ):
        raise ChunkIndexCorruptSource("Chunker provenance disagrees with chunk run")

    text = row["text"]
    if not isinstance(text, str):
        raise ChunkIndexCorruptSource("Chunk text is invalid")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != row["text_sha256"]:
        raise ChunkIndexCorruptSource("Chunk text digest is invalid")
    if int(row["char_count"]) != len(text):
        raise ChunkIndexCorruptSource("Chunk character count is invalid")

    page_text = row["current_page_text"]
    if not isinstance(page_text, str):
        raise ChunkIndexCorruptSource("Chunk page is missing or invalid")
    if (
        row["current_page_document_id"] != row["document_id"]
        or row["current_page_parse_run_id"] != row["parse_run_id"]
        or row["current_page_number"] != row["page_number"]
        or row["current_page_text_sha256"] != row["page_text_sha256"]
    ):
        raise ChunkIndexCorruptSource("Chunk page provenance is invalid")
    if (
        hashlib.sha256(page_text.encode("utf-8")).hexdigest()
        != row["page_text_sha256"]
    ):
        raise ChunkIndexCorruptSource("Chunk page text digest is invalid")
    start_char = int(row["start_char"])
    end_char = int(row["end_char"])
    if end_char > len(page_text) or page_text[start_char:end_char] != text:
        raise ChunkIndexCorruptSource(
            "Chunk text does not match its declared page span"
        )

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
        "chunker_config": _safe_json_object(
            row["chunker_config_json"],
            max_bytes=MAX_CONFIG_BYTES,
            strict=True,
        ),
    }
    if _sha256_json(identity) != row["chunk_key"]:
        raise ChunkIndexCorruptSource("Chunk deterministic identity is invalid")

    payload: dict[str, Any] = {
        "id": row["id"],
        "chunk_key": row["chunk_key"],
        "chunk_run_id": row["chunk_run_id"],
        "game": {
            "id": row["board_game_id"],
            "bgg_id": row["bgg_id"],
            "title": row["game_title"],
        },
        "document": {
            "id": row["document_id"],
            "sha256": row["document_sha256"],
            "metadata_sha256": row["document_metadata_sha256"],
            "document_type": row["document_type"],
            "language": row["language"],
            "version_label": row["version_label"],
            "edition": row["edition"],
            "source": {
                "kind": row["source_kind"],
                "provider": row["source_provider"],
                "url": row["source_url"],
                "official": bool(row["is_official"]),
            },
            "provenance": provenance,
        },
        "page": {
            "id": row["page_id"],
            "number": row["page_number"],
            "text_sha256": row["page_text_sha256"],
            "parse_run_id": row["parse_run_id"],
        },
        "chunk": {
            "index": row["chunk_index"],
            "start_char": row["start_char"],
            "end_char": row["end_char"],
            "char_count": row["char_count"],
            "text_sha256": row["text_sha256"],
        },
        "chunker": {
            "name": row["chunker_name"],
            "version": row["chunker_version"],
            "config": _safe_json_object(
                row["chunker_config_json"],
                max_bytes=MAX_CONFIG_BYTES,
            ),
        },
        "created_at": row["created_at"],
    }
    if include_text:
        payload["text"] = row["text"]
    return payload


class ChunkIndexService:
    def __init__(
        self,
        database: Database,
        manuals_dir: Path,
        *,
        max_chars: int,
        overlap_chars: int,
        min_break_chars: int,
    ) -> None:
        if min_break_chars <= 0 or min_break_chars > max_chars:
            raise ValueError("Invalid chunk minimum boundary size")
        if overlap_chars < 0 or overlap_chars >= min_break_chars:
            raise ValueError("Invalid chunk overlap")
        self.database = database
        self.manuals_dir = Path(manuals_dir)
        self.max_chars = int(max_chars)
        self.overlap_chars = int(overlap_chars)
        self.min_break_chars = int(min_break_chars)
        self.config_json = _config_json(
            max_chars=self.max_chars,
            overlap_chars=self.overlap_chars,
            min_break_chars=self.min_break_chars,
        )

    @staticmethod
    def _chunk_select(where: str) -> str:
        return f"""
            SELECT
                c.*,
                g.bgg_id,
                g.title AS game_title,
                r.document_sha256 AS run_document_sha256,
                r.document_metadata_sha256 AS run_metadata_sha256,
                r.chunker_name AS run_chunker_name,
                r.chunker_version AS run_chunker_version,
                r.chunker_config_json AS run_chunker_config_json,
                p.document_id AS current_page_document_id,
                p.parse_run_id AS current_page_parse_run_id,
                p.page_number AS current_page_number,
                p.text AS current_page_text,
                p.text_sha256 AS current_page_text_sha256
            FROM document_chunks c
            JOIN board_games g ON g.id = c.board_game_id
            JOIN document_chunk_runs r ON r.id = c.chunk_run_id
            LEFT JOIN document_pages p ON p.id = c.page_id
            WHERE {where}
        """

    def _document_exists(self, document_id: str) -> dict[str, Any]:
        document = DocumentStore(self.database, self.manuals_dir).get(document_id)
        if document is None:
            raise ChunkIndexDocumentNotFound(f"Document {document_id} not found")
        return document

    def _verify_archive(
        self,
        document_id: str,
        *,
        expected_sha256: str | None = None,
        expected_size_bytes: int | None = None,
    ) -> None:
        snapshot: Path | None = None
        try:
            snapshot = DocumentStore(
                self.database,
                self.manuals_dir,
            ).create_verified_snapshot(
                document_id,
                expected_sha256=expected_sha256,
                expected_size_bytes=expected_size_bytes,
                prefix=".p7b-verify-",
            )
        except DocumentError as exc:
            raise ChunkIndexSourceNotReady(
                "Archived PDF no longer matches document provenance"
            ) from exc
        finally:
            if snapshot is not None:
                snapshot.unlink(missing_ok=True)

    def _load_source(self, document_id: str) -> dict[str, Any]:
        document_summary = self._document_exists(document_id)
        self._verify_archive(
            document_id,
            expected_sha256=str(document_summary["sha256"]),
            expected_size_bytes=int(document_summary["size_bytes"]),
        )
        with self.database.connect() as connection:
            document_row = connection.execute(
                """
                SELECT d.*, g.bgg_id, g.title AS game_title
                FROM game_documents d
                JOIN board_games g ON g.id = d.board_game_id
                WHERE d.id = ?
                """,
                (document_id,),
            ).fetchone()
            if document_row is None:
                raise ChunkIndexDocumentNotFound(
                    f"Document {document_id} not found"
                )

            parse_row = connection.execute(
                """
                SELECT r.*
                FROM document_parse_runs r
                WHERE r.document_id = ?
                  AND r.status = 'succeeded'
                  AND (
                    r.page_count = 0
                    OR (
                        SELECT COUNT(*)
                        FROM document_pages p
                        WHERE p.document_id = r.document_id
                          AND p.parse_run_id = r.id
                    ) = r.page_count
                  )
                ORDER BY r.finished_at DESC, r.id DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
            if parse_row is None:
                raise ChunkIndexSourceNotReady(
                    "Document has no current successful page ingest"
                )

            page_rows = connection.execute(
                """
                SELECT *
                FROM document_pages
                WHERE document_id = ? AND parse_run_id = ?
                ORDER BY page_number
                """,
                (document_id, parse_row["id"]),
            ).fetchall()

        document = dict(document_row)
        parse_run = dict(parse_row)
        pages = [dict(row) for row in page_rows]
        if len(pages) != int(parse_run["page_count"]):
            raise ChunkIndexSourceNotReady(
                "Document page ingest is incomplete"
            )
        _validate_pages(pages, parse_run)
        provenance = _safe_json_object(
            document.get("provenance_json"),
            max_bytes=MAX_PROVENANCE_BYTES,
            strict=True,
        )
        metadata = _document_metadata(document, provenance)
        return {
            "document": document,
            "parse_run": parse_run,
            "pages": pages,
            "provenance": provenance,
            "metadata_sha256": _sha256_json(metadata),
            "source_pages_sha256": _page_set_digest(pages),
        }

    def _current_run_in_connection(
        self,
        connection: sqlite3.Connection,
        *,
        document_id: str,
        parse_run_id: str,
        document_sha256: str,
        metadata_sha256: str,
        source_pages_sha256: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT *
            FROM document_chunk_runs
            WHERE document_id = ?
              AND parse_run_id = ?
              AND document_sha256 = ?
              AND document_metadata_sha256 = ?
              AND source_pages_sha256 = ?
              AND chunker_name = ?
              AND chunker_version = ?
              AND chunker_config_json = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (
                document_id,
                parse_run_id,
                document_sha256,
                metadata_sha256,
                source_pages_sha256,
                CHUNKER_NAME,
                CHUNKER_VERSION,
                self.config_json,
            ),
        ).fetchone()
        if row is None:
            return None
        count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM document_chunks
            WHERE chunk_run_id = ?
            """,
            (row["id"],),
        ).fetchone()["count"]
        if int(count) != int(row["chunk_count"]):
            return None
        return _row_to_run(row)

    def _current_run(
        self,
        *,
        document_id: str,
        parse_run_id: str,
        document_sha256: str,
        metadata_sha256: str,
        source_pages_sha256: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return self._current_run_in_connection(
                connection,
                document_id=document_id,
                parse_run_id=parse_run_id,
                document_sha256=document_sha256,
                metadata_sha256=metadata_sha256,
                source_pages_sha256=source_pages_sha256,
            )

    def _chunk_source(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        document = source["document"]
        provenance = source["provenance"]
        chunks: list[dict[str, Any]] = []

        for page in source["pages"]:
            if page["extraction_status"] != "text" or not page["text"].strip():
                continue
            spans = split_page_text(
                page["text"],
                max_chars=self.max_chars,
                overlap_chars=self.overlap_chars,
                min_break_chars=self.min_break_chars,
            )
            for span in spans:
                text_sha256 = hashlib.sha256(
                    span.text.encode("utf-8")
                ).hexdigest()
                identity = {
                    "document_id": document["id"],
                    "document_sha256": document["sha256"],
                    "page_id": page["id"],
                    "page_number": page["page_number"],
                    "page_text_sha256": page["text_sha256"],
                    "chunk_index": span.index,
                    "start_char": span.start_char,
                    "end_char": span.end_char,
                    "text_sha256": text_sha256,
                    "chunker_name": CHUNKER_NAME,
                    "chunker_version": CHUNKER_VERSION,
                    "chunker_config": json.loads(self.config_json),
                }
                chunk_key = _sha256_json(identity)
                chunks.append(
                    {
                        "id": str(
                            uuid5(
                                NAMESPACE_URL,
                                f"boardgamecompanion:chunk:{chunk_key}",
                            )
                        ),
                        "chunk_key": chunk_key,
                        "page_id": page["id"],
                        "page_number": page["page_number"],
                        "page_text_sha256": page["text_sha256"],
                        "chunk_index": span.index,
                        "start_char": span.start_char,
                        "end_char": span.end_char,
                        "text": span.text,
                        "text_sha256": text_sha256,
                        "char_count": len(span.text),
                        "document_provenance_json": _canonical_json(provenance),
                    }
                )
        return chunks

    def _validate_source_unchanged(
        self,
        connection: sqlite3.Connection,
        source: dict[str, Any],
    ) -> None:
        document = source["document"]
        current_row = connection.execute(
            """
            SELECT *
            FROM game_documents
            WHERE id = ?
            """,
            (document["id"],),
        ).fetchone()
        if current_row is None:
            raise ChunkIndexConflict("Document disappeared during chunking")

        current_document = dict(current_row)
        current_provenance = _safe_json_object(
            current_document.get("provenance_json"),
            max_bytes=MAX_PROVENANCE_BYTES,
            strict=True,
        )
        current_metadata_sha256 = _sha256_json(
            _document_metadata(current_document, current_provenance)
        )
        if current_metadata_sha256 != source["metadata_sha256"]:
            raise ChunkIndexConflict(
                "Document provenance changed during chunking"
            )

        parse_row = connection.execute(
            """
            SELECT *
            FROM document_parse_runs
            WHERE id = ? AND document_id = ?
            """,
            (source["parse_run"]["id"], document["id"]),
        ).fetchone()
        if (
            parse_row is None
            or parse_row["status"] != "succeeded"
            or parse_row["document_sha256"] != document["sha256"]
        ):
            raise ChunkIndexConflict(
                "Document parse provenance changed during chunking"
            )

        page_rows = connection.execute(
            """
            SELECT *
            FROM document_pages
            WHERE document_id = ? AND parse_run_id = ?
            ORDER BY page_number
            """,
            (document["id"], source["parse_run"]["id"]),
        ).fetchall()
        current_pages = [dict(row) for row in page_rows]
        if len(current_pages) != int(parse_row["page_count"]):
            raise ChunkIndexConflict(
                "Document pages changed during chunking"
            )
        _validate_pages(current_pages, dict(parse_row))
        if _page_set_digest(current_pages) != source["source_pages_sha256"]:
            raise ChunkIndexConflict(
                "Document pages changed during chunking"
            )

    def build(
        self,
        document_id: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        source = self._load_source(document_id)
        document = source["document"]
        parse_run = source["parse_run"]

        if not force:
            current = self._current_run(
                document_id=document_id,
                parse_run_id=parse_run["id"],
                document_sha256=document["sha256"],
                metadata_sha256=source["metadata_sha256"],
                source_pages_sha256=source["source_pages_sha256"],
            )
            if current is not None:
                return {"created": False, "index": current}

        chunks = self._chunk_source(source)
        indexed_page_count = len({chunk["page_id"] for chunk in chunks})
        total_chunk_chars = sum(chunk["char_count"] for chunk in chunks)
        run_id = str(uuid4())
        created_at = _now()

        with self.database.transaction(immediate=True) as connection:
            self._validate_source_unchanged(connection, source)
            if not force:
                current = self._current_run_in_connection(
                    connection,
                    document_id=document_id,
                    parse_run_id=parse_run["id"],
                    document_sha256=document["sha256"],
                    metadata_sha256=source["metadata_sha256"],
                    source_pages_sha256=source["source_pages_sha256"],
                )
                if current is not None:
                    return {"created": False, "index": current}

            connection.execute(
                """
                INSERT INTO document_chunk_runs (
                    id, document_id, board_game_id, parse_run_id,
                    document_sha256, document_metadata_sha256,
                    source_pages_sha256, chunker_name, chunker_version,
                    chunker_config_json, page_count, indexed_page_count,
                    chunk_count, total_chunk_chars, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    document["id"],
                    document["board_game_id"],
                    parse_run["id"],
                    document["sha256"],
                    source["metadata_sha256"],
                    source["source_pages_sha256"],
                    CHUNKER_NAME,
                    CHUNKER_VERSION,
                    self.config_json,
                    int(parse_run["page_count"]),
                    indexed_page_count,
                    len(chunks),
                    total_chunk_chars,
                    created_at,
                ),
            )
            connection.execute(
                "DELETE FROM document_chunks WHERE document_id = ?",
                (document_id,),
            )

            for chunk in chunks:
                connection.execute(
                    """
                    INSERT INTO document_chunks (
                        id, chunk_key, chunk_run_id,
                        board_game_id, document_id, document_sha256,
                        document_metadata_sha256, parse_run_id,
                        page_id, page_number, page_text_sha256,
                        chunk_index, start_char, end_char,
                        text, text_sha256, char_count,
                        language, document_type, version_label, edition,
                        source_kind, source_provider, source_url, is_official,
                        document_provenance_json,
                        chunker_name, chunker_version, chunker_config_json,
                        created_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        chunk["id"],
                        chunk["chunk_key"],
                        run_id,
                        document["board_game_id"],
                        document["id"],
                        document["sha256"],
                        source["metadata_sha256"],
                        parse_run["id"],
                        chunk["page_id"],
                        chunk["page_number"],
                        chunk["page_text_sha256"],
                        chunk["chunk_index"],
                        chunk["start_char"],
                        chunk["end_char"],
                        chunk["text"],
                        chunk["text_sha256"],
                        chunk["char_count"],
                        document["language"],
                        document["document_type"],
                        document["version_label"],
                        document["edition"],
                        document["source_kind"],
                        document["source_provider"],
                        document["source_url"],
                        1 if document["is_official"] else 0,
                        chunk["document_provenance_json"],
                        CHUNKER_NAME,
                        CHUNKER_VERSION,
                        self.config_json,
                        created_at,
                    ),
                )

            run_row = connection.execute(
                "SELECT * FROM document_chunk_runs WHERE id = ?",
                (run_id,),
            ).fetchone()

        assert run_row is not None
        return {"created": True, "index": _row_to_run(run_row)}

    def status(self, document_id: str) -> dict[str, Any]:
        document = self._document_exists(document_id)
        with self.database.connect() as connection:
            latest = connection.execute(
                """
                SELECT *
                FROM document_chunk_runs
                WHERE document_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()

        try:
            source = self._load_source(document_id)
        except ChunkIndexSourceNotReady:
            return {
                "document": document,
                "source_ready": False,
                "current": None,
                "latest_run": _row_to_run(latest),
            }

        current = self._current_run(
            document_id=document_id,
            parse_run_id=source["parse_run"]["id"],
            document_sha256=source["document"]["sha256"],
            metadata_sha256=source["metadata_sha256"],
            source_pages_sha256=source["source_pages_sha256"],
        )
        return {
            "document": document,
            "source_ready": True,
            "source_parse_run_id": source["parse_run"]["id"],
            "source_pages_sha256": source["source_pages_sha256"],
            "current": current,
            "latest_run": _row_to_run(latest),
        }

    def list_chunks(
        self,
        document_id: str,
        *,
        page_number: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        document = self._document_exists(document_id)
        self._verify_archive(
            document_id,
            expected_sha256=str(document["sha256"]),
            expected_size_bytes=int(document["size_bytes"]),
        )
        params: list[Any] = [document_id]
        where = "c.document_id = ?"
        if page_number is not None:
            where += " AND c.page_number = ?"
            params.append(page_number)

        with self.database.connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) AS count FROM document_chunks c WHERE {where}",
                params,
            ).fetchone()["count"]
            rows = connection.execute(
                self._chunk_select(where)
                + """
                ORDER BY c.page_number, c.chunk_index
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return {
            "document": document,
            "count": total,
            "limit": limit,
            "offset": offset,
            "items": [
                _row_to_chunk(row, include_text=False)
                for row in rows
            ],
        }

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                self._chunk_select("c.id = ?"),
                (chunk_id,),
            ).fetchone()
        if row is None:
            return None
        self._verify_archive(
            str(row["document_id"]),
            expected_sha256=str(row["document_sha256"]),
        )
        return _row_to_chunk(row, include_text=True)
