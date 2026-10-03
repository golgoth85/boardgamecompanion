from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from boardgamecompanion.database import Database


class IndexStageService(Protocol):
    def __call__(self, document_id: str) -> dict[str, Any]: ...


class DocumentIndexingError(RuntimeError):
    pass


class DocumentIndexingBusy(DocumentIndexingError):
    pass


def enqueue_document_index(
    connection: sqlite3.Connection,
    document_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    current = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    result = connection.execute(
        """INSERT INTO document_index_jobs
           (document_id,status,stage,next_attempt_at,created_at,updated_at)
           VALUES (?,'pending','queued',?,?,?)
           ON CONFLICT(document_id) DO NOTHING""",
        (document_id, current, current, current),
    )
    return result.rowcount == 1


def requeue_document_indexes_for_provider_change(
    database: Database,
    *,
    exclude_document_id: str,
) -> int:
    now = datetime.now(UTC).isoformat()
    with database.transaction(immediate=True) as connection:
        result = connection.execute(
            """UPDATE document_index_jobs
               SET status='pending',stage='queued',next_attempt_at=?,
                   consecutive_failures=0,last_error_code=NULL,last_error_message=NULL,
                   lease_owner=NULL,lease_until=NULL,updated_at=?
               WHERE document_id<>?""",
            (now, now, exclude_document_id),
        )
    return int(result.rowcount)


class DocumentIndexingService:
    def __init__(
        self,
        database: Database,
        *,
        ingest: IndexStageService,
        chunks: IndexStageService,
        embeddings: IndexStageService,
        retry_base_seconds: int = 15 * 60,
        retry_max_seconds: int = 24 * 60 * 60,
        lease_seconds: int = 30 * 60,
    ) -> None:
        self.database = database
        self.ingest = ingest
        self.chunks = chunks
        self.embeddings = embeddings
        self.retry_base_seconds = int(retry_base_seconds)
        self.retry_max_seconds = int(retry_max_seconds)
        self.lease_seconds = int(lease_seconds)

    def synchronize_documents(self) -> int:
        now = datetime.now(UTC)
        with self.database.transaction(immediate=True) as connection:
            documents = connection.execute(
                """SELECT d.id FROM game_documents d LEFT JOIN document_index_jobs j
                   ON j.document_id=d.id WHERE j.document_id IS NULL"""
            ).fetchall()
            for row in documents:
                enqueue_document_index(connection, row["id"], now=now)
        return len(documents)

    def _claim(self, document_id: str, *, force: bool) -> tuple[str, int, datetime]:
        now = datetime.now(UTC)
        owner = str(uuid4())
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM document_index_jobs WHERE document_id=?", (document_id,)).fetchone()
            if row is None:
                document = connection.execute("SELECT id FROM game_documents WHERE id=?", (document_id,)).fetchone()
                if document is None:
                    raise DocumentIndexingError(f"Document {document_id} not found")
                enqueue_document_index(connection, document_id, now=now)
                row = connection.execute("SELECT * FROM document_index_jobs WHERE document_id=?", (document_id,)).fetchone()
            assert row is not None
            if row["lease_until"] and row["lease_until"] > now.isoformat():
                raise DocumentIndexingBusy(f"Document {document_id} is already being indexed")
            if not force and (row["status"] == "succeeded" or (row["next_attempt_at"] and row["next_attempt_at"] > now.isoformat())):
                raise DocumentIndexingBusy(f"Document {document_id} is not due")
            generation = int(row["lease_generation"]) + 1
            connection.execute(
                """UPDATE document_index_jobs SET status='running',stage='ingest',attempt_count=attempt_count+1,
                   last_started_at=?,lease_owner=?,lease_until=?,lease_generation=?,updated_at=? WHERE document_id=?""",
                (now.isoformat(), owner, (now + timedelta(seconds=self.lease_seconds)).isoformat(), generation, now.isoformat(), document_id),
            )
        return owner, generation, now

    def run(self, document_id: str, *, force: bool = True) -> dict[str, Any]:
        owner, generation, started = self._claim(document_id, force=force)
        stage = "ingest"
        try:
            ingest = self.ingest(document_id)
            stage = "chunks"
            self._set_stage(document_id, owner, generation, stage)
            chunks = self.chunks(document_id)
            stage = "embeddings"
            self._set_stage(document_id, owner, generation, stage)
            embeddings = self.embeddings(document_id)
        except Exception as exc:
            finished = datetime.now(UTC)
            with self.database.transaction(immediate=True) as connection:
                row = connection.execute("SELECT consecutive_failures FROM document_index_jobs WHERE document_id=?", (document_id,)).fetchone()
                failures = int(row["consecutive_failures"]) + 1 if row else 1
                delay = min(self.retry_base_seconds * (2 ** (failures - 1)), self.retry_max_seconds)
                connection.execute(
                    """UPDATE document_index_jobs SET status='failed',stage=?,next_attempt_at=?,
                       consecutive_failures=?,last_finished_at=?,last_error_code=?,last_error_message=?,
                       lease_owner=NULL,lease_until=NULL,updated_at=?
                       WHERE document_id=? AND lease_owner=? AND lease_generation=?""",
                    (stage, (finished + timedelta(seconds=delay)).isoformat(), failures, finished.isoformat(),
                     exc.__class__.__name__, str(exc)[:2000], finished.isoformat(), document_id, owner, generation),
                )
                connection.execute(
                    """INSERT INTO document_index_runs
                       (id,document_id,lease_generation,started_at,finished_at,outcome,final_stage,error_code,error_message)
                       VALUES (?,?,?,?,?,'failed',?,?,?)""",
                    (str(uuid4()), document_id, generation, started.isoformat(), finished.isoformat(), stage,
                     exc.__class__.__name__, str(exc)[:2000]),
                )
            raise
        finished = datetime.now(UTC)
        with self.database.transaction(immediate=True) as connection:
            changed = connection.execute(
                """UPDATE document_index_jobs SET status='succeeded',stage='complete',next_attempt_at=NULL,
                   consecutive_failures=0,last_finished_at=?,last_error_code=NULL,last_error_message=NULL,
                   lease_owner=NULL,lease_until=NULL,updated_at=?
                   WHERE document_id=? AND lease_owner=? AND lease_generation=?""",
                (finished.isoformat(), finished.isoformat(), document_id, owner, generation),
            )
            if changed.rowcount != 1:
                raise DocumentIndexingBusy("Document indexing lease changed before completion")
            connection.execute(
                """INSERT INTO document_index_runs
                   (id,document_id,lease_generation,started_at,finished_at,outcome,final_stage)
                   VALUES (?,?,?,?,?,'succeeded','complete')""",
                (str(uuid4()), document_id, generation, started.isoformat(), finished.isoformat()),
            )
        return {"document_id": document_id, "status": "succeeded", "stage": "complete",
                "ingest": ingest, "chunks": chunks, "embeddings": embeddings}

    def _set_stage(self, document_id: str, owner: str, generation: int, stage: str) -> None:
        with self.database.transaction(immediate=True) as connection:
            changed = connection.execute(
                """UPDATE document_index_jobs SET stage=?,updated_at=?
                   WHERE document_id=? AND lease_owner=? AND lease_generation=?""",
                (stage, datetime.now(UTC).isoformat(), document_id, owner, generation),
            )
            if changed.rowcount != 1:
                raise DocumentIndexingBusy("Document indexing lease changed")

    def run_due(self, *, limit: int = 2) -> dict[str, Any]:
        self.synchronize_documents()
        current = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT document_id FROM document_index_jobs
                   WHERE (
                       (status IN ('pending','failed') AND next_attempt_at<=?)
                       OR (status='running' AND lease_until<=?)
                   )
                   AND (lease_until IS NULL OR lease_until<=?) ORDER BY next_attempt_at LIMIT ?""",
                (current, current, current, max(1, min(int(limit), 20))),
            ).fetchall()
        items: list[dict[str, Any]] = []
        failures = 0
        for row in rows:
            try:
                items.append(self.run(row["document_id"], force=False))
            except DocumentIndexingBusy:
                continue
            except Exception:
                failures += 1
        return {"attempted": len(items) + failures, "succeeded": len(items), "failed": failures, "items": items}

    def status(self, *, document_id: str | None = None, limit: int = 250) -> dict[str, Any]:
        where = "WHERE j.document_id=?" if document_id else ""
        params: tuple[Any, ...] = (document_id,) if document_id else ()
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""SELECT j.*,d.board_game_id,g.bgg_id,g.title AS game_title FROM document_index_jobs j
                    JOIN game_documents d ON d.id=j.document_id JOIN board_games g ON g.id=d.board_game_id
                    {where} ORDER BY j.updated_at DESC LIMIT ?""", (*params, max(1, min(int(limit), 500)))
            ).fetchall()
        return {"count": len(rows), "items": [dict(row) for row in rows]}
