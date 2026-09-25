from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from fastapi.testclient import TestClient

from boardgamecompanion.chunk_index import split_page_text
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


def _upload(client: TestClient, payload: bytes) -> dict:
    response = client.post(
        "/api/games/900001/documents",
        data={
            "document_type": "rulebook",
            "language": "it",
            "title": "Regolamento",
            "version_label": "v2",
            "edition": "Retail IT",
            "source_url": "https://publisher.example/rules.pdf",
            "is_official": "true",
        },
        files={"file": ("rules.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()["document"]


def _long_page(label: str) -> str:
    sentences = [
        f"{label} rule {number}: perform this exact action before the next step."
        for number in range(1, 10)
    ]
    return " ".join(sentences)


def test_split_page_text_is_deterministic_bounded_and_exact() -> None:
    text = (
        "Alpha one. Alpha two. Alpha three. "
        "Beta one. Beta two. Beta three. "
        "Gamma one. Gamma two."
    )
    first = split_page_text(
        text,
        max_chars=45,
        overlap_chars=8,
        min_break_chars=20,
    )
    second = split_page_text(
        text,
        max_chars=45,
        overlap_chars=8,
        min_break_chars=20,
    )

    assert first == second
    assert len(first) >= 2
    for index, span in enumerate(first):
        assert span.index == index
        assert 0 <= span.start_char < span.end_char <= len(text)
        assert len(span.text) <= 45
        assert span.text == text[span.start_char : span.end_char]
    assert first[1].start_char < first[0].end_char


def test_chunk_build_requires_current_p7a_pages(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, _pdf_with_pages("Not parsed yet."))

        response = client.post(f"/api/documents/{document['id']}/chunks/build")
        assert response.status_code == 409
        assert "page ingest" in response.json()["detail"]

        status = client.get(
            f"/api/documents/{document['id']}/chunk-index"
        ).json()
        assert status["source_ready"] is False
        assert status["current"] is None


def test_chunk_build_preserves_page_and_document_provenance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    pdf = _pdf_with_pages(_long_page("Setup"), _long_page("Turn"))

    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, pdf)
        ingest = client.post(f"/api/documents/{document['id']}/ingest")
        assert ingest.status_code == 200

        page_list = client.get(f"/api/documents/{document['id']}/pages").json()
        page_texts = {
            item["page_number"]: client.get(
                f"/api/documents/{document['id']}/pages/{item['page_number']}"
            ).json()["text"]
            for item in page_list["items"]
        }

        built = client.post(f"/api/documents/{document['id']}/chunks/build")
        assert built.status_code == 200, built.text
        result = built.json()
        assert result["created"] is True
        assert result["index"]["page_count"] == 2
        assert result["index"]["indexed_page_count"] == 2
        assert result["index"]["chunk_count"] > 2

        listing = client.get(
            f"/api/documents/{document['id']}/chunks?limit=100"
        ).json()
        assert listing["count"] == result["index"]["chunk_count"]
        assert all("text" not in item for item in listing["items"])

        for summary in listing["items"]:
            detail = client.get(f"/api/chunks/{summary['id']}").json()
            assert detail["id"] == summary["id"]
            assert detail["game"]["bgg_id"] == 900001
            assert detail["document"]["id"] == document["id"]
            assert detail["document"]["sha256"] == document["sha256"]
            assert detail["document"]["language"] == "it"
            assert detail["document"]["document_type"] == "rulebook"
            assert detail["document"]["version_label"] == "v2"
            assert detail["document"]["edition"] == "Retail IT"
            assert detail["document"]["source"]["official"] is True

            page_number = detail["page"]["number"]
            start = detail["chunk"]["start_char"]
            end = detail["chunk"]["end_char"]
            assert detail["text"] == page_texts[page_number][start:end]
            assert detail["chunk"]["char_count"] == len(detail["text"])
            assert detail["chunk"]["text_sha256"] == hashlib.sha256(
                detail["text"].encode("utf-8")
            ).hexdigest()

        first_ids = [item["id"] for item in listing["items"]]
        first_run = result["index"]["id"]

        repeated = client.post(f"/api/documents/{document['id']}/chunks/build").json()
        assert repeated["created"] is False
        assert repeated["index"]["id"] == first_run

        forced = client.post(
            f"/api/documents/{document['id']}/chunks/build?force=true"
        ).json()
        assert forced["created"] is True
        assert forced["index"]["id"] != first_run
        rebuilt = client.get(
            f"/api/documents/{document['id']}/chunks?limit=100"
        ).json()
        assert [item["id"] for item in rebuilt["items"]] == first_ids


def test_p7a_reparse_invalidates_chunks_and_rebuild_keeps_content_identity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    pdf = _pdf_with_pages(_long_page("Round"))

    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, pdf)
        assert client.post(
            f"/api/documents/{document['id']}/ingest"
        ).status_code == 200
        assert client.post(
            f"/api/documents/{document['id']}/chunks/build"
        ).status_code == 200

        before = client.get(
            f"/api/documents/{document['id']}/chunks?limit=100"
        ).json()
        before_ids = [item["id"] for item in before["items"]]
        assert before_ids

        reparsed = client.post(
            f"/api/documents/{document['id']}/ingest?force=true"
        )
        assert reparsed.status_code == 200

        after_reparse = client.get(
            f"/api/documents/{document['id']}/chunks?limit=100"
        ).json()
        assert after_reparse["count"] == 0

        status = client.get(
            f"/api/documents/{document['id']}/chunk-index"
        ).json()
        assert status["source_ready"] is True
        assert status["current"] is None
        assert status["latest_run"] is not None

        rebuilt = client.post(
            f"/api/documents/{document['id']}/chunks/build"
        )
        assert rebuilt.status_code == 200
        after_rebuild = client.get(
            f"/api/documents/{document['id']}/chunks?limit=100"
        ).json()
        assert [item["id"] for item in after_rebuild["items"]] == before_ids


def test_empty_page_builds_valid_zero_chunk_index(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, _pdf_with_pages(""))
        assert client.post(
            f"/api/documents/{document['id']}/ingest"
        ).status_code == 200

        built = client.post(f"/api/documents/{document['id']}/chunks/build")
        assert built.status_code == 200
        payload = built.json()
        assert payload["created"] is True
        assert payload["index"]["page_count"] == 1
        assert payload["index"]["indexed_page_count"] == 0
        assert payload["index"]["chunk_count"] == 0

        repeated = client.post(
            f"/api/documents/{document['id']}/chunks/build"
        ).json()
        assert repeated["created"] is False

        listing = client.get(
            f"/api/documents/{document['id']}/chunks"
        ).json()
        assert listing["count"] == 0


def test_chunk_build_rejects_corrupt_p7a_page_text(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, _pdf_with_pages("Verified page text."))
        assert client.post(
            f"/api/documents/{document['id']}/ingest"
        ).status_code == 200

        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                UPDATE document_pages
                SET text = 'tampered page text'
                WHERE document_id = ?
                """,
                (document["id"],),
            )
            connection.commit()

        response = client.post(f"/api/documents/{document['id']}/chunks/build")
        assert response.status_code == 500
        assert "digest" in response.json()["detail"]


def test_document_provenance_change_invalidates_existing_chunks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, _pdf_with_pages(_long_page("Metadata")))
        assert client.post(
            f"/api/documents/{document['id']}/ingest"
        ).status_code == 200
        assert client.post(
            f"/api/documents/{document['id']}/chunks/build"
        ).status_code == 200
        before = client.get(
            f"/api/documents/{document['id']}/chunks"
        ).json()
        assert before["count"] > 0

        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                UPDATE game_documents
                SET language = 'en', updated_at = 'changed'
                WHERE id = ?
                """,
                (document["id"],),
            )
            connection.commit()

        after = client.get(
            f"/api/documents/{document['id']}/chunks"
        ).json()
        assert after["count"] == 0

        status = client.get(
            f"/api/documents/{document['id']}/chunk-index"
        ).json()
        assert status["source_ready"] is True
        assert status["current"] is None
        assert status["latest_run"] is not None

        rebuilt = client.post(
            f"/api/documents/{document['id']}/chunks/build"
        )
        assert rebuilt.status_code == 200
        detail = client.get(
            f"/api/documents/{document['id']}/chunks?limit=1"
        ).json()["items"][0]
        assert detail["document"]["language"] == "en"


def test_chunk_read_rejects_corrupt_denormalized_provenance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, _pdf_with_pages(_long_page("Integrity")))
        assert client.post(
            f"/api/documents/{document['id']}/ingest"
        ).status_code == 200
        assert client.post(
            f"/api/documents/{document['id']}/chunks/build"
        ).status_code == 200
        chunk_id = client.get(
            f"/api/documents/{document['id']}/chunks?limit=1"
        ).json()["items"][0]["id"]

        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                UPDATE document_chunks
                SET language = 'corrupt'
                WHERE id = ?
                """,
                (chunk_id,),
            )
            connection.commit()

        detail = client.get(f"/api/chunks/{chunk_id}")
        assert detail.status_code == 500
        assert "metadata digest" in detail.json()["detail"]

        listing = client.get(
            f"/api/documents/{document['id']}/chunks"
        )
        assert listing.status_code == 500
        assert "metadata digest" in listing.json()["detail"]


def test_page_mutation_invalidates_existing_chunks(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, _pdf_with_pages(_long_page("PageMutation")))
        assert client.post(
            f"/api/documents/{document['id']}/ingest"
        ).status_code == 200
        assert client.post(
            f"/api/documents/{document['id']}/chunks/build"
        ).status_code == 200
        before = client.get(
            f"/api/documents/{document['id']}/chunks"
        ).json()
        assert before["count"] > 0

        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                UPDATE document_pages
                SET text = text || ' changed',
                    char_count = char_count + 8
                WHERE document_id = ?
                """,
                (document["id"],),
            )
            connection.commit()

        after = client.get(
            f"/api/documents/{document['id']}/chunks"
        ).json()
        assert after["count"] == 0
        status = client.get(
            f"/api/documents/{document['id']}/chunk-index"
        )
        assert status.status_code == 500
        assert "digest" in status.json()["detail"]


def test_non_force_concurrent_builds_are_serialized_and_idempotent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from boardgamecompanion.chunk_index import ChunkIndexService
    from boardgamecompanion.database import Database

    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, _pdf_with_pages(_long_page("Concurrent")))
        assert client.post(
            f"/api/documents/{document['id']}/ingest"
        ).status_code == 200

    database = Database(settings.database_path)
    barrier = threading.Barrier(2)
    original_chunk_source = ChunkIndexService._chunk_source

    def synchronized_chunk_source(self, source):
        chunks = original_chunk_source(self, source)
        barrier.wait(timeout=5)
        return chunks

    monkeypatch.setattr(
        ChunkIndexService,
        "_chunk_source",
        synchronized_chunk_source,
    )

    def build_once():
        service = ChunkIndexService(
            database,
            settings.manuals_dir,
            max_chars=settings.chunk_max_chars,
            overlap_chars=settings.chunk_overlap_chars,
            min_break_chars=settings.chunk_min_break_chars,
        )
        return service.build(document["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result(timeout=10) for future in [
            executor.submit(build_once),
            executor.submit(build_once),
        ]]

    assert sorted(result["created"] for result in results) == [False, True]
    run_ids = {result["index"]["id"] for result in results}
    assert len(run_ids) == 1

    with database.connect() as connection:
        run_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM document_chunk_runs
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()["count"]
        chunk_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM document_chunks
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()["count"]
        expected_chunks = connection.execute(
            """
            SELECT chunk_count
            FROM document_chunk_runs
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()["chunk_count"]

    assert run_count == 1
    assert chunk_count == expected_chunks


def test_build_revalidates_page_bytes_after_source_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from boardgamecompanion.chunk_index import ChunkIndexService

    _configure(monkeypatch, tmp_path)
    original_chunk_source = ChunkIndexService._chunk_source

    def mutate_after_snapshot(self, source):
        chunks = original_chunk_source(self, source)
        document_id = source["document"]["id"]
        with sqlite3.connect(settings.database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                UPDATE document_pages
                SET text = text || ' raced',
                    char_count = char_count + 6
                WHERE document_id = ?
                """,
                (document_id,),
            )
            connection.commit()
        return chunks

    monkeypatch.setattr(
        ChunkIndexService,
        "_chunk_source",
        mutate_after_snapshot,
    )

    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, _pdf_with_pages(_long_page("Race")))
        assert client.post(
            f"/api/documents/{document['id']}/ingest"
        ).status_code == 200

        response = client.post(f"/api/documents/{document['id']}/chunks/build")
        assert response.status_code == 500
        assert "digest" in response.json()["detail"]

        listing = client.get(
            f"/api/documents/{document['id']}/chunks"
        ).json()
        assert listing["count"] == 0

    with sqlite3.connect(settings.database_path) as connection:
        run_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM document_chunk_runs
            WHERE document_id = ?
            """,
            (document["id"],),
        ).fetchone()[0]
    assert run_count == 0


def test_chunk_read_rejects_coherent_text_that_is_not_page_substring(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, _pdf_with_pages(_long_page("Span")))
        assert client.post(f"/api/documents/{document['id']}/ingest").status_code == 200
        assert client.post(f"/api/documents/{document['id']}/chunks/build").status_code == 200

        with sqlite3.connect(settings.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT *
                FROM document_chunks
                WHERE document_id = ?
                ORDER BY page_number, chunk_index
                LIMIT 1
                """,
                (document["id"],),
            ).fetchone()
            assert row is not None
            replacement = "X" * len(row["text"])
            replacement_sha = hashlib.sha256(
                replacement.encode("utf-8")
            ).hexdigest()
            identity = {
                "document_id": row["document_id"],
                "document_sha256": row["document_sha256"],
                "page_id": row["page_id"],
                "page_number": row["page_number"],
                "page_text_sha256": row["page_text_sha256"],
                "chunk_index": row["chunk_index"],
                "start_char": row["start_char"],
                "end_char": row["end_char"],
                "text_sha256": replacement_sha,
                "chunker_name": row["chunker_name"],
                "chunker_version": row["chunker_version"],
                "chunker_config": json.loads(row["chunker_config_json"]),
            }
            chunk_key = hashlib.sha256(
                json.dumps(
                    identity,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            chunk_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"boardgamecompanion:chunk:{chunk_key}",
                )
            )
            connection.execute(
                """
                UPDATE document_chunks
                SET id = ?, chunk_key = ?, text = ?, text_sha256 = ?
                WHERE id = ?
                """,
                (
                    chunk_id,
                    chunk_key,
                    replacement,
                    replacement_sha,
                    row["id"],
                ),
            )
            connection.commit()

        response = client.get(f"/api/chunks/{chunk_id}")
        assert response.status_code == 500
        assert "page span" in response.json()["detail"]
