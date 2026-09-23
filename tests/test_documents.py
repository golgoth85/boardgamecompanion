from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.main import app
from boardgamecompanion.settings import settings

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


def configure_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "config_dir", tmp_path / "config")
    monkeypatch.setattr(settings, "import_dir", tmp_path / "import")
    monkeypatch.setattr(settings, "manuals_dir", tmp_path / "manuals")
    monkeypatch.setattr(settings, "max_document_bytes", 1024 * 1024)


def import_fixture(client: TestClient) -> None:
    with FIXTURE.open("rb") as handle:
        response = client.post(
            "/api/imports/bgg-csv",
            files={"file": ("collection.csv", handle, "text/csv")},
        )
    assert response.status_code == 200


def test_pdf_upload_is_persisted_with_provenance_and_downloadable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure_paths(monkeypatch, tmp_path)

    with TestClient(app) as client:
        import_fixture(client)

        response = client.post(
            "/api/games/900001/documents",
            data={
                "document_type": "rulebook",
                "language": "it",
                "title": "Regolamento italiano",
                "version_label": "v2",
                "edition": "Retail IT",
                "published_at": "2026-01-02",
                "source_url": "https://publisher.example/rules.pdf",
                "is_official": "true",
            },
            files={
                "file": (
                    "../../Regolamento Ufficiale.pdf",
                    PDF_BYTES,
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["created"] is True
        document = payload["document"]
        assert document["bgg_id"] == 900001
        assert document["document_type"] == "rulebook"
        assert document["language"] == "it"
        assert document["title"] == "Regolamento italiano"
        assert document["original_filename"] == "Regolamento Ufficiale.pdf"
        assert document["size_bytes"] == len(PDF_BYTES)
        assert document["source"] == {
            "kind": "manual_upload",
            "provider": "user",
            "url": "https://publisher.example/rules.pdf",
            "official": True,
        }
        assert document["version_label"] == "v2"
        assert document["edition"] == "Retail IT"
        assert document["published_at"] == "2026-01-02"
        assert document["provenance"]["ingest"] == "manual_upload"
        assert document["provenance"]["official_asserted_by_user"] is True

        listed = client.get("/api/games/900001/documents")
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
        assert listed.json()["items"][0]["id"] == document["id"]

        downloaded = client.get(document["download_url"])
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith("application/pdf")
        assert downloaded.content == PDF_BYTES

        stored_files = list((tmp_path / "manuals" / "900001").glob("*.pdf"))
        assert len(stored_files) == 1
        assert stored_files[0].name == f"{document['id']}.pdf"
        assert not (tmp_path / "Regolamento Ufficiale.pdf").exists()


def test_duplicate_pdf_is_idempotent_per_game(monkeypatch, tmp_path: Path) -> None:
    configure_paths(monkeypatch, tmp_path)

    with TestClient(app) as client:
        import_fixture(client)

        first = client.post(
            "/api/games/900001/documents",
            data={"language": "en", "document_type": "rulebook"},
            files={"file": ("rules-a.pdf", PDF_BYTES, "application/pdf")},
        )
        second = client.post(
            "/api/games/900001/documents",
            data={"language": "it", "document_type": "faq"},
            files={"file": ("rules-b.pdf", PDF_BYTES, "application/pdf")},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["created"] is True
        assert second.json()["created"] is False
        assert second.json()["document"]["id"] == first.json()["document"]["id"]

        listed = client.get("/api/games/900001/documents").json()
        assert listed["count"] == 1
        assert len(list((tmp_path / "manuals" / "900001").glob("*.pdf"))) == 1


def test_document_upload_rejects_invalid_pdf_size_and_unknown_game(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configure_paths(monkeypatch, tmp_path)

    with TestClient(app) as client:
        import_fixture(client)

        wrong_extension = client.post(
            "/api/games/900001/documents",
            files={"file": ("rules.txt", PDF_BYTES, "text/plain")},
        )
        assert wrong_extension.status_code == 400

        wrong_signature = client.post(
            "/api/games/900001/documents",
            files={"file": ("rules.pdf", b"not a pdf", "application/pdf")},
        )
        assert wrong_signature.status_code == 400

        monkeypatch.setattr(settings, "max_document_bytes", 16)
        too_large = client.post(
            "/api/games/900001/documents",
            files={"file": ("large.pdf", PDF_BYTES, "application/pdf")},
        )
        assert too_large.status_code == 413

        monkeypatch.setattr(settings, "max_document_bytes", 1024 * 1024)
        missing_game = client.post(
            "/api/games/999999/documents",
            files={"file": ("rules.pdf", PDF_BYTES, "application/pdf")},
        )
        assert missing_game.status_code == 404

    leftovers = list((tmp_path / "manuals").rglob("*.part"))
    assert leftovers == []


def test_document_metadata_validation(monkeypatch, tmp_path: Path) -> None:
    configure_paths(monkeypatch, tmp_path)

    with TestClient(app) as client:
        import_fixture(client)

        bad_type = client.post(
            "/api/games/900001/documents",
            data={"document_type": "executable"},
            files={"file": ("rules.pdf", PDF_BYTES, "application/pdf")},
        )
        assert bad_type.status_code == 400

        bad_language = client.post(
            "/api/games/900001/documents",
            data={"language": "../../it"},
            files={"file": ("rules.pdf", PDF_BYTES, "application/pdf")},
        )
        assert bad_language.status_code == 400
