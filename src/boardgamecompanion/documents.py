from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from boardgamecompanion.database import Database


DOCUMENT_TYPES = {
    "rulebook",
    "reference",
    "faq",
    "errata",
    "scenario_book",
    "campaign_book",
    "player_aid",
    "other",
}


class DocumentError(ValueError):
    pass


class DocumentNotFound(DocumentError):
    pass


class DocumentTooLarge(DocumentError):
    pass


class InvalidPdf(DocumentError):
    pass


class BoardGameDocumentNotFound(DocumentError):
    pass


def normalize_language(value: str | None) -> str:
    text = (value or "und").strip().lower().replace("_", "-")
    if not text:
        return "und"
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", text):
        raise DocumentError("Invalid document language tag")
    return text


def normalize_document_type(value: str | None) -> str:
    text = (value or "rulebook").strip().lower()
    if text not in DOCUMENT_TYPES:
        raise DocumentError(
            f"Unsupported document type: {text or '(empty)'}"
        )
    return text


def _clean_text(value: Any, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if max_length is not None and len(text) > max_length:
        raise DocumentError(f"Text value exceeds {max_length} characters")
    return text


def _row_to_document(row: sqlite3.Row) -> dict[str, Any]:
    try:
        provenance = json.loads(row["provenance_json"] or "{}")
    except (TypeError, ValueError):
        provenance = {}
    return {
        "id": row["id"],
        "bgg_id": row["bgg_id"],
        "game_title": row["game_title"],
        "document_type": row["document_type"],
        "language": row["language"],
        "title": row["title"],
        "original_filename": row["original_filename"],
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
        "mime_type": row["mime_type"],
        "source": {
            "kind": row["source_kind"],
            "provider": row["source_provider"],
            "url": row["source_url"],
            "official": bool(row["is_official"]),
        },
        "version_label": row["version_label"],
        "edition": row["edition"],
        "published_at": row["published_at"],
        "provenance": provenance,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "download_url": f"/api/documents/{row['id']}/file",
    }


class DocumentStore:
    def __init__(self, database: Database, manuals_dir: Path):
        self.database = database
        self.manuals_dir = Path(manuals_dir)

    @staticmethod
    def _select_sql(where: str) -> str:
        return f"""
            SELECT d.*, g.bgg_id, g.title AS game_title
            FROM game_documents d
            JOIN board_games g ON g.id = d.board_game_id
            WHERE {where}
        """

    def list_for_game(self, bgg_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                self._select_sql("g.bgg_id = ?") + """
                ORDER BY
                    d.is_official DESC,
                    CASE d.language WHEN 'it' THEN 0 WHEN 'en' THEN 1 ELSE 2 END,
                    d.document_type,
                    d.title COLLATE NOCASE,
                    d.created_at
                """,
                (bgg_id,),
            ).fetchall()
        return [_row_to_document(row) for row in rows]

    def get(self, document_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                self._select_sql("d.id = ?"),
                (document_id,),
            ).fetchone()
        return _row_to_document(row) if row else None

    def resolve_path(self, document_id: str) -> Path:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT storage_path FROM game_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            raise DocumentNotFound(f"Document {document_id} not found")

        relative = Path(row["storage_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise DocumentError("Invalid stored document path")

        root = self.manuals_dir.resolve()
        path = (root / relative).resolve()
        if root not in path.parents:
            raise DocumentError("Document path escapes manuals directory")
        if not path.is_file():
            raise DocumentNotFound(f"Document file {document_id} is missing")
        return path

    def import_pdf(
        self,
        *,
        bgg_id: int,
        original_filename: str,
        stream: BinaryIO,
        document_type: str = "rulebook",
        language: str = "und",
        title: str | None = None,
        version_label: str | None = None,
        edition: str | None = None,
        published_at: str | None = None,
        source_url: str | None = None,
        is_official: bool = False,
        max_bytes: int,
    ) -> tuple[dict[str, Any], bool]:
        doc_type = normalize_document_type(document_type)
        lang = normalize_language(language)
        clean_filename = Path(original_filename or "document.pdf").name
        if not clean_filename.lower().endswith(".pdf"):
            raise InvalidPdf("Only PDF documents are supported")

        document_id = str(uuid4())
        game_dir = self.manuals_dir / str(int(bgg_id))
        game_dir.mkdir(parents=True, exist_ok=True)
        temp_path = game_dir / f".{document_id}.part"
        final_path = game_dir / f"{document_id}.pdf"

        digest = hashlib.sha256()
        size = 0
        first_bytes = b""
        try:
            with temp_path.open("wb") as destination:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    if not isinstance(chunk, (bytes, bytearray)):
                        raise InvalidPdf("Uploaded document is not binary")
                    if len(first_bytes) < 8:
                        first_bytes += bytes(chunk[: 8 - len(first_bytes)])
                    size += len(chunk)
                    if size > max_bytes:
                        raise DocumentTooLarge(
                            f"PDF exceeds the {max_bytes} byte upload limit"
                        )
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())

            if not first_bytes.startswith(b"%PDF-"):
                raise InvalidPdf("Uploaded file is not a PDF")
            if size <= 5:
                raise InvalidPdf("Uploaded PDF is empty")

            sha256 = digest.hexdigest()
            now = datetime.now(UTC).isoformat()

            with self.database.connect() as connection:
                game = connection.execute(
                    "SELECT id, title FROM board_games WHERE bgg_id = ?",
                    (bgg_id,),
                ).fetchone()
                if game is None:
                    raise BoardGameDocumentNotFound(
                        f"Board game BGG #{bgg_id} not found"
                    )

                duplicate = connection.execute(
                    self._select_sql("d.board_game_id = ? AND d.sha256 = ?"),
                    (game["id"], sha256),
                ).fetchone()
                if duplicate is not None:
                    return _row_to_document(duplicate), False

            os.replace(temp_path, final_path)
            relative_path = final_path.relative_to(self.manuals_dir).as_posix()
            doc_title = (
                _clean_text(title, max_length=500)
                or Path(clean_filename).stem
                or f"Document {bgg_id}"
            )
            provenance = {
                "ingest": "manual_upload",
                "original_filename": clean_filename,
                "source_url": _clean_text(source_url, max_length=2000),
                "official_asserted_by_user": bool(is_official),
            }

            try:
                with self.database.transaction() as connection:
                    game = connection.execute(
                        "SELECT id FROM board_games WHERE bgg_id = ?",
                        (bgg_id,),
                    ).fetchone()
                    if game is None:
                        raise BoardGameDocumentNotFound(
                            f"Board game BGG #{bgg_id} not found"
                        )
                    connection.execute(
                        """
                        INSERT INTO game_documents (
                            id, board_game_id, document_type, language, title,
                            original_filename, storage_path, sha256, size_bytes,
                            mime_type, source_kind, source_provider, source_url,
                            is_official, version_label, edition, published_at,
                            provenance_json, created_at, updated_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, 'application/pdf',
                            'manual_upload', 'user', ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            document_id,
                            game["id"],
                            doc_type,
                            lang,
                            doc_title,
                            clean_filename,
                            relative_path,
                            sha256,
                            size,
                            _clean_text(source_url, max_length=2000),
                            1 if is_official else 0,
                            _clean_text(version_label, max_length=500),
                            _clean_text(edition, max_length=500),
                            _clean_text(published_at, max_length=64),
                            json.dumps(
                                provenance,
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                            now,
                            now,
                        ),
                    )
            except sqlite3.IntegrityError:
                final_path.unlink(missing_ok=True)
                with self.database.connect() as connection:
                    duplicate = connection.execute(
                        self._select_sql("d.board_game_id = ? AND d.sha256 = ?"),
                        (game["id"], sha256),
                    ).fetchone()
                if duplicate is not None:
                    return _row_to_document(duplicate), False
                raise
            except Exception:
                final_path.unlink(missing_ok=True)
                raise

            created = self.get(document_id)
            assert created is not None
            return created, True
        finally:
            temp_path.unlink(missing_ok=True)
