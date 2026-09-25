from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, Iterator
from uuid import NAMESPACE_URL, uuid4, uuid5

from boardgamecompanion.database import Database
from boardgamecompanion.documents import DocumentError, DocumentStore

PARSER_NAME = "pypdf"
MAX_DIAGNOSTICS_BYTES = 128 * 1024
MAX_PAGE_DIAGNOSTICS_BYTES = 16 * 1024


class PdfIngestError(RuntimeError):
    pass


class PdfIngestDocumentNotFound(PdfIngestError):
    pass


class PdfIngestIntegrityError(PdfIngestError):
    pass


class PdfIngestParseError(PdfIngestError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_json_object(raw: str | None, *, max_bytes: int) -> dict[str, Any]:
    if not raw:
        return {}
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > max_bytes:
        return {"corrupt": True}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, RecursionError, UnicodeError):
        return {"corrupt": True}
    if not isinstance(value, dict):
        return {"corrupt": True}
    return value


def _json_object(value: dict[str, Any], *, max_bytes: int) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(raw.encode("utf-8")) > max_bytes:
        raise PdfIngestParseError("Parser diagnostics exceed the persistence limit")
    return raw


def _row_to_run(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "document_sha256": row["document_sha256"],
        "parser": {
            "name": row["parser_name"],
            "version": row["parser_version"],
        },
        "status": row["status"],
        "page_count": row["page_count"],
        "text_page_count": row["text_page_count"],
        "empty_page_count": row["empty_page_count"],
        "error_page_count": row["error_page_count"],
        "total_text_chars": row["total_text_chars"],
        "warning_count": row["warning_count"],
        "diagnostics": _safe_json_object(
            row["diagnostics_json"],
            max_bytes=MAX_DIAGNOSTICS_BYTES,
        ),
        "error": (
            {
                "code": row["error_code"],
                "message": row["error_message"],
            }
            if row["status"] == "failed"
            else None
        ),
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def _row_to_page(
    row: sqlite3.Row,
    *,
    include_text: bool = True,
) -> dict[str, Any]:
    page = {
        "id": row["id"],
        "document_id": row["document_id"],
        "parse_run_id": row["parse_run_id"],
        "page_index": row["page_index"],
        "page_number": row["page_number"],
        "text_sha256": row["text_sha256"],
        "char_count": row["char_count"],
        "extraction_status": row["extraction_status"],
        "diagnostics": _safe_json_object(
            row["diagnostics_json"],
            max_bytes=MAX_PAGE_DIAGNOSTICS_BYTES,
        ),
        "created_at": row["created_at"],
    }
    if include_text:
        page["text"] = row["text"]
    return page


class PdfIngestService:
    def __init__(
        self,
        database: Database,
        manuals_dir: Path,
        *,
        timeout_seconds: float,
        max_pages: int,
        max_chars_per_page: int,
        max_total_chars: int,
        memory_mb: int,
    ) -> None:
        self.database = database
        self.manuals_dir = Path(manuals_dir)
        self.timeout_seconds = float(timeout_seconds)
        self.max_pages = int(max_pages)
        self.max_chars_per_page = int(max_chars_per_page)
        self.max_total_chars = int(max_total_chars)
        self.memory_mb = int(memory_mb)

    @property
    def parser_version(self) -> str:
        return package_version("pypdf")

    def _document(self, document_id: str) -> dict[str, Any]:
        document = DocumentStore(self.database, self.manuals_dir).get(document_id)
        if document is None:
            raise PdfIngestDocumentNotFound(f"Document {document_id} not found")
        return document

    @contextmanager
    def _verified_snapshot(
        self,
        *,
        document_id: str,
        expected_sha256: str,
        expected_size: int,
    ) -> Iterator[Path]:
        store = DocumentStore(self.database, self.manuals_dir)
        snapshot_path: Path | None = None
        try:
            snapshot_path = store.create_verified_snapshot(
                document_id,
                expected_sha256=expected_sha256,
                expected_size_bytes=expected_size,
                prefix=".p7a-",
            )
            yield snapshot_path
        except DocumentError as exc:
            raise PdfIngestIntegrityError(str(exc)) from exc
        finally:
            if snapshot_path is not None:
                snapshot_path.unlink(missing_ok=True)

    def _current_success_in_connection(
        self,
        connection: sqlite3.Connection,
        *,
        document_id: str,
        document_sha256: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT r.*
            FROM document_parse_runs r
            WHERE r.document_id = ?
              AND r.document_sha256 = ?
              AND r.parser_name = ?
              AND r.parser_version = ?
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
            (
                document_id,
                document_sha256,
                PARSER_NAME,
                self.parser_version,
            ),
        ).fetchone()
        return _row_to_run(row)

    def _current_success(
        self,
        *,
        document_id: str,
        document_sha256: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return self._current_success_in_connection(
                connection,
                document_id=document_id,
                document_sha256=document_sha256,
            )

    def _record_failure(
        self,
        *,
        document_id: str,
        document_sha256: str,
        started_at: str,
        code: str,
        message: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = str(uuid4())
        finished_at = _now()
        diagnostics_json = _json_object(
            diagnostics or {},
            max_bytes=MAX_DIAGNOSTICS_BYTES,
        )
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO document_parse_runs (
                    id, document_id, document_sha256,
                    parser_name, parser_version, status,
                    page_count, text_page_count, empty_page_count,
                    error_page_count, total_text_chars, warning_count,
                    diagnostics_json, error_code, error_message,
                    started_at, finished_at
                ) VALUES (
                    ?, ?, ?, ?, ?, 'failed',
                    NULL, NULL, NULL, NULL, NULL, 0,
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    run_id,
                    document_id,
                    document_sha256,
                    PARSER_NAME,
                    self.parser_version,
                    diagnostics_json,
                    code[:128],
                    message[:2000],
                    started_at,
                    finished_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM document_parse_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        assert row is not None
        return _row_to_run(row) or {}

    def _run_parser(self, snapshot: Path) -> dict[str, Any]:
        cpu_seconds = max(1, math.ceil(self.timeout_seconds))
        command = [
            sys.executable,
            "-m",
            "boardgamecompanion.pdf_worker",
            str(snapshot),
            "--max-pages",
            str(self.max_pages),
            "--max-chars-per-page",
            str(self.max_chars_per_page),
            "--max-total-chars",
            str(self.max_total_chars),
            "--memory-mb",
            str(self.memory_mb),
            "--cpu-seconds",
            str(cpu_seconds),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfIngestParseError("parse_timeout: PDF parser timed out") from exc
        except OSError as exc:
            raise PdfIngestParseError(
                "parser_start_failed: PDF parser process could not be started"
            ) from exc

        stdout = completed.stdout or ""
        if len(stdout.encode("utf-8")) > self.max_total_chars * 4 + 1024 * 1024:
            raise PdfIngestParseError(
                "parser_output_limit: PDF parser output exceeded the safety limit"
            )
        try:
            payload = json.loads(stdout)
        except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
            stderr = (completed.stderr or "")[:1000]
            raise PdfIngestParseError(
                "invalid_parser_output: "
                f"{stderr or 'PDF parser returned invalid output'}"
            ) from exc
        if not isinstance(payload, dict):
            raise PdfIngestParseError(
                "invalid_parser_output: PDF parser returned an invalid payload"
            )
        if not payload.get("ok"):
            code = str(payload.get("error_code") or "parse_failed")
            message = str(payload.get("error_message") or "PDF parsing failed")
            raise PdfIngestParseError(f"{code}: {message}")
        return payload

    def _validate_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if payload.get("parser_name") != PARSER_NAME:
            raise PdfIngestParseError("parser_identity: unexpected parser identity")
        if payload.get("parser_version") != self.parser_version:
            raise PdfIngestParseError(
                "parser_version: parser version changed during ingestion"
            )

        pages = payload.get("pages")
        if not isinstance(pages, list):
            raise PdfIngestParseError("parser_pages: parser pages payload is invalid")
        if len(pages) != payload.get("page_count"):
            raise PdfIngestParseError("parser_pages: parser page count is inconsistent")
        if len(pages) > self.max_pages:
            raise PdfIngestParseError("page_limit: parser page count exceeds limit")

        total_chars = 0
        normalized: list[dict[str, Any]] = []
        for expected_index, item in enumerate(pages):
            if not isinstance(item, dict):
                raise PdfIngestParseError("parser_page: page payload is invalid")
            text = item.get("text")
            if not isinstance(text, str):
                raise PdfIngestParseError("parser_page: page text is invalid")
            if item.get("page_index") != expected_index:
                raise PdfIngestParseError(
                    "parser_page: page indexes are not contiguous"
                )
            if item.get("page_number") != expected_index + 1:
                raise PdfIngestParseError(
                    "parser_page: page number is inconsistent"
                )
            if len(text) > self.max_chars_per_page:
                raise PdfIngestParseError(
                    "page_text_limit: parser page text exceeds configured limit"
                )
            total_chars += len(text)
            if total_chars > self.max_total_chars:
                raise PdfIngestParseError(
                    "document_text_limit: parser document text exceeds configured limit"
                )
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if item.get("text_sha256") != digest:
                raise PdfIngestParseError(
                    "parser_digest: parser page text digest is inconsistent"
                )
            status = item.get("extraction_status")
            if status not in {"text", "empty", "error"}:
                raise PdfIngestParseError(
                    "parser_status: page extraction status is invalid"
                )
            diagnostics = item.get("diagnostics")
            if not isinstance(diagnostics, dict):
                diagnostics = {}
            normalized.append(
                {
                    "page_index": expected_index,
                    "page_number": expected_index + 1,
                    "text": text,
                    "text_sha256": digest,
                    "char_count": len(text),
                    "extraction_status": status,
                    "diagnostics_json": _json_object(
                        diagnostics,
                        max_bytes=MAX_PAGE_DIAGNOSTICS_BYTES,
                    ),
                }
            )

        if total_chars != payload.get("total_text_chars"):
            raise PdfIngestParseError(
                "parser_totals: total character count is inconsistent"
            )
        counts = {
            "text": sum(p["extraction_status"] == "text" for p in normalized),
            "empty": sum(p["extraction_status"] == "empty" for p in normalized),
            "error": sum(p["extraction_status"] == "error" for p in normalized),
        }
        if counts["text"] != payload.get("text_page_count"):
            raise PdfIngestParseError("parser_totals: text-page count is inconsistent")
        if counts["empty"] != payload.get("empty_page_count"):
            raise PdfIngestParseError("parser_totals: empty-page count is inconsistent")
        if counts["error"] != payload.get("error_page_count"):
            raise PdfIngestParseError("parser_totals: error-page count is inconsistent")
        return normalized

    def ingest(self, document_id: str, *, force: bool = False) -> dict[str, Any]:
        document = self._document(document_id)
        document_sha256 = str(document["sha256"])
        document_size = int(document["size_bytes"])
        started_at = _now()

        def verify_archive(prefix: str) -> None:
            try:
                with self._verified_snapshot(
                    document_id=document_id,
                    expected_sha256=document_sha256,
                    expected_size=document_size,
                ):
                    pass
            except PdfIngestIntegrityError:
                raise

        if not force:
            try:
                verify_archive(".p7a-current-")
            except PdfIngestIntegrityError as exc:
                self._record_failure(
                    document_id=document_id,
                    document_sha256=document_sha256,
                    started_at=started_at,
                    code="integrity_mismatch",
                    message=str(exc),
                )
                raise
            current = self._current_success(
                document_id=document_id,
                document_sha256=document_sha256,
            )
            if current is not None:
                return {"created": False, "ingest": current}

        try:
            with self._verified_snapshot(
                document_id=document_id,
                expected_sha256=document_sha256,
                expected_size=document_size,
            ) as snapshot:
                payload = self._run_parser(snapshot)
            pages = self._validate_payload(payload)
        except PdfIngestIntegrityError as exc:
            self._record_failure(
                document_id=document_id,
                document_sha256=document_sha256,
                started_at=started_at,
                code="integrity_mismatch",
                message=str(exc),
            )
            raise
        except PdfIngestParseError as exc:
            message = str(exc)
            code = message.split(":", 1)[0] if ":" in message else "parse_failed"
            self._record_failure(
                document_id=document_id,
                document_sha256=document_sha256,
                started_at=started_at,
                code=code,
                message=message,
            )
            raise

        run_id = str(uuid4())
        diagnostics = payload.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}

        created = False
        result_run: dict[str, Any] | None = None
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT sha256, size_bytes FROM game_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if row is None:
                raise PdfIngestDocumentNotFound(
                    f"Document {document_id} disappeared during ingestion"
                )
            if (
                row["sha256"] != document_sha256
                or int(row["size_bytes"]) != document_size
            ):
                raise PdfIngestIntegrityError(
                    "Document provenance changed during ingestion"
                )

            commit_snapshot: Path | None = None
            try:
                commit_snapshot = DocumentStore(
                    self.database,
                    self.manuals_dir,
                ).create_verified_snapshot(
                    document_id,
                    expected_sha256=document_sha256,
                    expected_size_bytes=document_size,
                    prefix=".p7a-commit-",
                )
            except DocumentError as exc:
                raise PdfIngestIntegrityError(str(exc)) from exc
            finally:
                if commit_snapshot is not None:
                    commit_snapshot.unlink(missing_ok=True)

            if not force:
                current = self._current_success_in_connection(
                    connection,
                    document_id=document_id,
                    document_sha256=document_sha256,
                )
                if current is not None:
                    result_run = current

            if result_run is None:
                finished_at = _now()
                connection.execute(
                    """
                    INSERT INTO document_parse_runs (
                        id, document_id, document_sha256,
                        parser_name, parser_version, status,
                        page_count, text_page_count, empty_page_count,
                        error_page_count, total_text_chars, warning_count,
                        diagnostics_json, error_code, error_message,
                        started_at, finished_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, 'succeeded',
                        ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?
                    )
                    """,
                    (
                        run_id,
                        document_id,
                        document_sha256,
                        PARSER_NAME,
                        self.parser_version,
                        int(payload["page_count"]),
                        int(payload["text_page_count"]),
                        int(payload["empty_page_count"]),
                        int(payload["error_page_count"]),
                        int(payload["total_text_chars"]),
                        int(payload["warning_count"]),
                        _json_object(
                            diagnostics,
                            max_bytes=MAX_DIAGNOSTICS_BYTES,
                        ),
                        started_at,
                        finished_at,
                    ),
                )
                connection.execute(
                    "DELETE FROM document_pages WHERE document_id = ?",
                    (document_id,),
                )
                for page in pages:
                    page_id = str(
                        uuid5(
                            NAMESPACE_URL,
                            (
                                "boardgamecompanion:"
                                f"{document_id}:page:{page['page_number']}"
                            ),
                        )
                    )
                    connection.execute(
                        """
                        INSERT INTO document_pages (
                            id, document_id, parse_run_id,
                            page_index, page_number, text, text_sha256,
                            char_count, extraction_status, diagnostics_json,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            page_id,
                            document_id,
                            run_id,
                            page["page_index"],
                            page["page_number"],
                            page["text"],
                            page["text_sha256"],
                            page["char_count"],
                            page["extraction_status"],
                            page["diagnostics_json"],
                            finished_at,
                        ),
                    )
                run_row = connection.execute(
                    "SELECT * FROM document_parse_runs WHERE id = ?",
                    (run_id,),
                ).fetchone()
                assert run_row is not None
                result_run = _row_to_run(run_row)
                created = True

        assert result_run is not None

        # The filesystem is outside SQLite's transaction. Re-verify after the
        # DB commit so a replacement in the pre-commit verification window is
        # detected before the ingest request can succeed. On mismatch, remove
        # all page material for the document; FK cascades invalidate P7B/P7C.
        try:
            verify_archive(".p7a-postcommit-")
        except PdfIngestIntegrityError as exc:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    "DELETE FROM document_pages WHERE document_id = ?",
                    (document_id,),
                )
            self._record_failure(
                document_id=document_id,
                document_sha256=document_sha256,
                started_at=started_at,
                code="integrity_mismatch",
                message=str(exc),
            )
            raise

        return {"created": created, "ingest": result_run}

    def status(self, document_id: str) -> dict[str, Any]:
        document = self._document(document_id)
        with self.database.connect() as connection:
            latest = connection.execute(
                """
                SELECT *
                FROM document_parse_runs
                WHERE document_id = ?
                ORDER BY finished_at DESC, id DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
            current = connection.execute(
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
        return {
            "document": document,
            "current": _row_to_run(current),
            "latest_run": _row_to_run(latest),
        }

    def list_pages(
        self,
        document_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        document = self._document(document_id)
        with self.database.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) AS count FROM document_pages WHERE document_id = ?",
                (document_id,),
            ).fetchone()["count"]
            rows = connection.execute(
                """
                SELECT *
                FROM document_pages
                WHERE document_id = ?
                ORDER BY page_number
                LIMIT ? OFFSET ?
                """,
                (document_id, limit, offset),
            ).fetchall()
        return {
            "document": document,
            "count": total,
            "limit": limit,
            "offset": offset,
            "items": [_row_to_page(row, include_text=False) for row in rows],
        }

    def get_page(self, document_id: str, page_number: int) -> dict[str, Any] | None:
        self._document(document_id)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM document_pages
                WHERE document_id = ? AND page_number = ?
                """,
                (document_id, page_number),
            ).fetchone()
        return _row_to_page(row) if row else None
