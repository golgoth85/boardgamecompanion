from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

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
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode()
        objects.append(page)
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


def test_pdf_ingest_preserves_page_identity_text_and_document_provenance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    pdf = _pdf_with_pages("Setup: draw five cards.", "Turn: play one card.")

    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, pdf)

        response = client.post(f"/api/documents/{document['id']}/ingest")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["created"] is True
        ingest = payload["ingest"]
        assert ingest["status"] == "succeeded"
        assert ingest["parser"]["name"] == "pypdf"
        assert ingest["page_count"] == 2
        assert ingest["text_page_count"] == 2
        assert ingest["error_page_count"] == 0

        pages = client.get(f"/api/documents/{document['id']}/pages").json()
        assert pages["count"] == 2
        assert [page["page_number"] for page in pages["items"]] == [1, 2]
        assert "text" not in pages["items"][0]
        assert "text" not in pages["items"][1]
        assert pages["items"][0]["id"] != pages["items"][1]["id"]
        assert pages["items"][0]["extraction_status"] == "text"

        status = client.get(f"/api/documents/{document['id']}/ingest").json()
        assert status["document"]["language"] == "it"
        assert status["document"]["document_type"] == "rulebook"
        assert status["document"]["version_label"] == "v2"
        assert status["document"]["edition"] == "Retail IT"
        assert status["document"]["source"]["official"] is True
        assert status["current"]["id"] == ingest["id"]

        page = client.get(f"/api/documents/{document['id']}/pages/1").json()
        assert page["id"] == pages["items"][0]["id"]
        assert "Setup: draw five cards." in page["text"]
        assert page["text_sha256"] == pages["items"][0]["text_sha256"]
        second_page = client.get(
            f"/api/documents/{document['id']}/pages/2"
        ).json()
        assert "Turn: play one card." in second_page["text"]


def test_pdf_ingest_is_idempotent_and_force_reparse_keeps_page_identity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    pdf = _pdf_with_pages("First page.")

    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, pdf)

        first = client.post(f"/api/documents/{document['id']}/ingest").json()
        page_before = client.get(f"/api/documents/{document['id']}/pages/1").json()

        second = client.post(f"/api/documents/{document['id']}/ingest").json()
        assert second["created"] is False
        assert second["ingest"]["id"] == first["ingest"]["id"]

        forced = client.post(
            f"/api/documents/{document['id']}/ingest?force=true"
        ).json()
        assert forced["created"] is True
        assert forced["ingest"]["id"] != first["ingest"]["id"]
        page_after = client.get(f"/api/documents/{document['id']}/pages/1").json()
        assert page_after["id"] == page_before["id"]
        assert page_after["parse_run_id"] == forced["ingest"]["id"]


def test_pdf_ingest_records_empty_pages_without_inventing_ocr_text(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    pdf = _pdf_with_pages("")

    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, pdf)
        response = client.post(f"/api/documents/{document['id']}/ingest")
        assert response.status_code == 200
        ingest = response.json()["ingest"]
        assert ingest["page_count"] == 1
        assert ingest["text_page_count"] == 0
        assert ingest["empty_page_count"] == 1

        page = client.get(f"/api/documents/{document['id']}/pages/1").json()
        assert page["text"] == ""
        assert page["extraction_status"] == "empty"


def test_pdf_ingest_rejects_tampered_archive_and_keeps_no_pages(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _configure(monkeypatch, tmp_path)
    pdf = _pdf_with_pages("Trusted text.")

    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, pdf)
        stored = next((tmp_path / "manuals" / "900001").glob("*.pdf"))
        stored.write_bytes(_pdf_with_pages("Tampered text."))

        response = client.post(f"/api/documents/{document['id']}/ingest")
        assert response.status_code == 409
        pages = client.get(f"/api/documents/{document['id']}/pages").json()
        assert pages["count"] == 0
        status = client.get(f"/api/documents/{document['id']}/ingest").json()
        assert status["latest_run"]["status"] == "failed"
        assert status["latest_run"]["error"]["code"] == "integrity_mismatch"


def test_pdf_ingest_unknown_document_and_missing_page(monkeypatch, tmp_path: Path) -> None:
    _configure(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/documents/missing/ingest").status_code == 404
        assert client.get("/api/documents/missing/pages").status_code == 404


def test_failed_force_reparse_keeps_previous_successful_pages(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from boardgamecompanion.pdf_ingest import PdfIngestParseError, PdfIngestService

    _configure(monkeypatch, tmp_path)
    pdf = _pdf_with_pages("Stable page.")

    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, pdf)
        first = client.post(f"/api/documents/{document['id']}/ingest")
        assert first.status_code == 200
        page_before = client.get(f"/api/documents/{document['id']}/pages/1").json()

        def fail_parser(self, snapshot):
            raise PdfIngestParseError("forced_failure: simulated parser failure")

        monkeypatch.setattr(PdfIngestService, "_run_parser", fail_parser)
        failed = client.post(
            f"/api/documents/{document['id']}/ingest?force=true"
        )
        assert failed.status_code == 422

        page_after = client.get(f"/api/documents/{document['id']}/pages/1").json()
        assert page_after["id"] == page_before["id"]
        assert page_after["text"] == page_before["text"]

        status = client.get(f"/api/documents/{document['id']}/ingest").json()
        assert status["current"]["id"] == first.json()["ingest"]["id"]
        assert status["latest_run"]["status"] == "failed"
        assert status["latest_run"]["error"]["code"] == "forced_failure"


def test_parser_start_failure_is_not_reported_as_document_integrity_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import boardgamecompanion.pdf_ingest as pdf_ingest_module

    _configure(monkeypatch, tmp_path)
    pdf = _pdf_with_pages("Parser startup test.")

    def fail_start(*args, **kwargs):
        raise OSError("simulated process start failure")

    monkeypatch.setattr(pdf_ingest_module.subprocess, "run", fail_start)

    with TestClient(app) as client:
        _import_game(client)
        document = _upload(client, pdf)

        response = client.post(f"/api/documents/{document['id']}/ingest")
        assert response.status_code == 422
        assert "parser_start_failed" in response.json()["detail"]

        status = client.get(f"/api/documents/{document['id']}/ingest").json()
        assert status["latest_run"]["status"] == "failed"
        assert status["latest_run"]["error"]["code"] == "parser_start_failed"
