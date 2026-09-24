from __future__ import annotations

import csv
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

SAMPLE = Path(__file__).parents[1] / "fixtures" / "bgg_collection_sample.csv"


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture()
def live_server(tmp_path: Path):
    config = tmp_path / "config"
    imports = tmp_path / "import"
    manuals = tmp_path / "manuals"
    for path in (config, imports, manuals):
        path.mkdir(parents=True, exist_ok=True)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = os.environ.copy()
    env.update(
        {
            "BGC_CONFIG_DIR": str(config),
            "BGC_IMPORT_DIR": str(imports),
            "BGC_MANUALS_DIR": str(manuals),
        }
    )

    log_path = tmp_path / "uvicorn.log"
    log = log_path.open("w+", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "boardgamecompanion.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                if process.poll() is not None:
                    break
                time.sleep(0.1)
        else:
            log.flush()
            raise RuntimeError(f"server did not become ready:\n{log_path.read_text()}")

        if process.poll() is not None:
            log.flush()
            raise RuntimeError(f"server exited early:\n{log_path.read_text()}")

        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()


def new_page(browser, *, mobile: bool = False):
    viewport = {"width": 390, "height": 844} if mobile else {"width": 1440, "height": 1000}
    context = browser.new_context(viewport=viewport)
    return context, context.new_page()


def import_csv(page, base_url: str, path: Path = SAMPLE) -> None:
    page.goto(base_url)
    page.get_by_role("button", name="Importa BGG CSV").click()
    page.locator("#csvFile").set_input_files(str(path))
    page.get_by_role("button", name="Importa", exact=True).click()
    expect(page.locator("#importResult")).to_contain_text("Import completato.")
    expect(page.locator("#importResult")).to_contain_text("2 righe")
    page.get_by_role("button", name="Chiudi").click()
    expect(page.locator("#importDialog")).not_to_be_visible()


def make_many_games_csv(path: Path, count: int = 30) -> Path:
    with SAMPLE.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        template = next(reader)
        fieldnames = reader.fieldnames

    rows = []
    for index in range(count):
        row = template.copy()
        row["objectname"] = f"Pagination Game {index:02d}"
        row["originalname"] = row["objectname"]
        row["objectid"] = str(910000 + index)
        row["collid"] = str(810000 + index)
        row["yearpublished"] = str(2000 + (index % 25))
        row["average"] = str(5 + index / 20)
        rows.append(row)

    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def make_xss_csv(path: Path) -> Path:
    with SAMPLE.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        row = next(reader)
        fieldnames = reader.fieldnames

    row["objectid"] = "920001"
    row["collid"] = "820001"
    row["objectname"] = '<img src=x onerror="window.__bgc_xss=1">'
    row["originalname"] = row["objectname"]

    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)
    return path


def test_close_x_never_submits_and_dialog_resets(browser, live_server):
    context, page = new_page(browser)
    import_requests: list[str] = []
    page.on(
        "request",
        lambda request: import_requests.append(request.url)
        if "/api/imports/bgg-csv" in request.url
        else None,
    )

    try:
        page.goto(live_server)
        page.get_by_role("button", name="Importa BGG CSV").click()
        page.locator("#csvFile").set_input_files(str(SAMPLE))
        expect(page.locator("#fileName")).to_have_text(SAMPLE.name)

        page.get_by_role("button", name="Chiudi").click()
        expect(page.locator("#importDialog")).not_to_be_visible()
        page.wait_for_timeout(250)
        assert import_requests == []

        page.get_by_role("button", name="Importa BGG CSV").click()
        expect(page.locator("#fileName")).to_have_text("Nessun file selezionato")
        assert page.locator("#csvFile").input_value() == ""

        page.keyboard.press("Escape")
        expect(page.locator("#importDialog")).not_to_be_visible()
        assert import_requests == []

        stats = page.request.get(f"{live_server}/api/catalog/stats").json()
        assert stats["total"] == 0
    finally:
        context.close()


def test_desktop_import_search_filter_navigation_and_repeat_import(browser, live_server):
    context, page = new_page(browser)
    try:
        import_csv(page, live_server)

        expect(page.locator("#statsPanel .stat strong")).to_have_text(["2", "1", "1", "2"])
        expect(page.locator(".game-card")).to_have_count(2)

        page.locator("#searchInput").fill("Beta")
        expect(page.locator(".game-card")).to_have_count(1)
        expect(page.locator(".card-title")).to_have_text("Synthetic Beta Expansion")

        page.locator("#searchInput").fill("")
        expect(page.locator(".game-card")).to_have_count(2)

        page.locator("#typeFilter").select_option("expansion")
        expect(page.locator(".game-card")).to_have_count(1)
        expect(page.locator(".card-title")).to_have_text("Synthetic Beta Expansion")

        page.locator("#typeFilter").select_option("")
        expect(page.locator(".game-card")).to_have_count(2)

        page.locator("#sortFilter").select_option("rating_desc")
        expect(page.locator(".card-title").first).to_have_text("Synthetic Alpha")

        page.get_by_role("link", name="Apri Synthetic Beta Expansion").click()
        expect(page).to_have_url(f"{live_server}/games/900002")
        expect(page.locator(".detail-main h1")).to_have_text("Synthetic Beta Expansion")
        expect(page.get_by_text("Espansione", exact=True)).to_be_visible()

        page.get_by_role("button", name="Importa BGG CSV").click()
        page.locator("#csvFile").set_input_files(str(SAMPLE))
        page.get_by_role("button", name="Importa", exact=True).click()
        expect(page.locator("#importResult")).to_contain_text("0 nuovi")
        expect(page.locator("#importResult")).to_contain_text("2 invariati")
        expect(page.locator(".detail-main h1")).to_have_text("Synthetic Beta Expansion")

        page.get_by_role("button", name="Chiudi").click()
        expect(page.locator("#importDialog")).not_to_be_visible()

        page.get_by_role("link", name="Torna al catalogo").click()
        expect(page).to_have_url(f"{live_server}/")
        expect(page.locator(".game-card")).to_have_count(2)
    finally:
        context.close()


def test_import_error_is_visible_and_recoverable(browser, live_server):
    context, page = new_page(browser)
    try:
        page.goto(live_server)
        page.get_by_role("button", name="Importa BGG CSV").click()
        page.locator("#csvFile").set_input_files(
            {
                "name": "not-a-csv.txt",
                "mimeType": "text/plain",
                "buffer": b"not a csv",
            }
        )
        page.get_by_role("button", name="Importa", exact=True).click()
        expect(page.locator("#importResult")).to_contain_text("Expected a .csv file")

        page.get_by_role("button", name="Chiudi").click()
        expect(page.locator("#importDialog")).not_to_be_visible()

        page.get_by_role("button", name="Importa BGG CSV").click()
        expect(page.locator("#importResult")).to_be_hidden()
        expect(page.locator("#fileName")).to_have_text("Nessun file selezionato")
    finally:
        context.close()


def test_pagination(browser, live_server, tmp_path: Path):
    many = make_many_games_csv(tmp_path / "many.csv")
    context, page = new_page(browser)
    try:
        page.goto(live_server)
        page.get_by_role("button", name="Importa BGG CSV").click()
        page.locator("#csvFile").set_input_files(str(many))
        page.get_by_role("button", name="Importa", exact=True).click()
        expect(page.locator("#importResult")).to_contain_text("30 righe")
        page.get_by_role("button", name="Chiudi").click()

        expect(page.locator(".game-card")).to_have_count(24)
        expect(page.locator("#pagination")).to_contain_text("Pagina 1 di 2")
        page.get_by_role("button", name="Successiva").click()
        expect(page.locator(".game-card")).to_have_count(6)
        expect(page.locator("#pagination")).to_contain_text("Pagina 2 di 2")
        page.get_by_role("button", name="Precedente").click()
        expect(page.locator(".game-card")).to_have_count(24)
    finally:
        context.close()


def test_mobile_layout_has_no_horizontal_overflow(browser, live_server):
    context, page = new_page(browser, mobile=True)
    try:
        import_csv(page, live_server)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        expect(page.get_by_role("button", name="Importa BGG CSV")).to_be_visible()
        expect(page.locator(".game-card")).to_have_count(2)

        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        expect(page.locator(".detail-main h1")).to_have_text("Synthetic Alpha")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

        page.get_by_role("button", name="Importa BGG CSV").click()
        expect(page.locator("#importDialog")).to_be_visible()
        box = page.locator("#importDialog").bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= 391
        page.get_by_role("button", name="Chiudi").click()
    finally:
        context.close()


def test_catalog_escapes_untrusted_titles(browser, live_server, tmp_path: Path):
    malicious = make_xss_csv(tmp_path / "xss.csv")
    context, page = new_page(browser)
    try:
        page.goto(live_server)
        page.get_by_role("button", name="Importa BGG CSV").click()
        page.locator("#csvFile").set_input_files(str(malicious))
        page.get_by_role("button", name="Importa", exact=True).click()
        expect(page.locator("#importResult")).to_contain_text("Import completato.")
        page.get_by_role("button", name="Chiudi").click()

        expect(page.locator(".card-title")).to_contain_text("<img src=x")
        assert page.evaluate("window.__bgc_xss") is None
        assert page.locator(".card-title img").count() == 0
    finally:
        context.close()


def test_floppy_panel_reports_unconfigured_without_blocking_catalog(browser, live_server):
    context, page = new_page(browser)
    try:
        page.goto(live_server)
        expect(page.locator("#floppyStatus")).to_have_text("Non configurato")
        expect(page.locator("#floppyBody")).to_contain_text("Apri Impostazioni")
        expect(page.locator("#floppyPreview")).to_be_disabled()
        expect(page.locator("#catalogGrid")).to_be_visible()
    finally:
        context.close()


def test_floppy_settings_are_saved_from_ui_without_revealing_token(browser, live_server):
    context, page = new_page(browser)
    try:
        page.route(
            "**/api/integrations/floppy/status",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"configured":false,"reachable":false,"authenticated":false,"boardgame_api":false,"schema":{"available":false,"media_write":false,"collection_write":false,"write_contract_ready":false}}',
            ),
        )

        page.goto(live_server)
        page.get_by_role("button", name="Impostazioni").click()
        expect(page.locator("#settingsDialog")).to_be_visible()

        page.locator("#floppyUrl").fill("http://floppy:8000")
        page.locator("#floppyApiKey").fill("browser-secret-token")
        page.locator("#floppyTimeout").fill("11")
        page.locator("#floppyVerifyTls").uncheck()
        page.get_by_role("button", name="Salva", exact=True).click()

        expect(page.locator("#settingsResult")).to_contain_text("Impostazioni salvate")
        response = page.request.get(f"{live_server}/api/settings/floppy")
        assert response.ok
        body = response.json()
        assert body["url"] == "http://floppy:8000"
        assert body["api_key_configured"] is True
        assert body["timeout_seconds"] == 11
        assert body["verify_tls"] is False
        assert "browser-secret-token" not in response.text()

        page.get_by_role("button", name="Chiudi impostazioni").click()
        page.get_by_role("button", name="Impostazioni").click()

        expect(page.locator("#floppyApiKey")).to_have_value("")
        expect(page.locator("#floppyTokenHint")).to_contain_text("Token configurato")
        expect(page.locator("#clearTokenRow")).to_be_visible()
    finally:
        context.close()


def test_floppy_sync_requires_preview_confirmation_and_refreshes(browser, live_server):
    context, page = new_page(browser)
    sync_requests = []
    preview_calls = {"count": 0}

    def status_route(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=(
                '{"configured":true,"reachable":true,"authenticated":true,'
                '"boardgame_api":true,"info":{"version":"26.9"},'
                '"schema":{"available":true,"media_write":true,'
                '"collection_write":true,"write_contract_ready":true}}'
            ),
        )

    def preview_route(route):
        preview_calls["count"] += 1
        if preview_calls["count"] == 1:
            body = {
                "local_owned": 2,
                "remote_boardgames": 1,
                "remote_collection_entries": 1,
                "matched": 1,
                "matched_by_saved_link": 0,
                "matched_by_bgg_id": 1,
                "matched_by_title_year": 0,
                "already_owned": 1,
                "needs_collection": 0,
                "needs_media": 1,
                "missing_in_floppy": 1,
                "ambiguous": 0,
                "actionable": 1,
                "already_owned_items": [],
                "needs_collection_items": [],
                "needs_media_items": [
                    {
                        "bgg_id": 900002,
                        "title": "Synthetic Beta Expansion",
                        "year_published": 2021,
                        "item_type": "expansion",
                    }
                ],
                "missing": [],
                "ambiguous_items": [],
                "plan_hash": "a" * 64,
                "mode": "dry_run",
                "apply_supported": True,
            }
        else:
            body = {
                "local_owned": 2,
                "remote_boardgames": 2,
                "remote_collection_entries": 2,
                "matched": 2,
                "matched_by_saved_link": 1,
                "matched_by_bgg_id": 1,
                "matched_by_title_year": 0,
                "already_owned": 2,
                "needs_collection": 0,
                "needs_media": 0,
                "missing_in_floppy": 0,
                "ambiguous": 0,
                "actionable": 0,
                "already_owned_items": [],
                "needs_collection_items": [],
                "needs_media_items": [],
                "missing": [],
                "ambiguous_items": [],
                "plan_hash": "b" * 64,
                "mode": "dry_run",
                "apply_supported": True,
            }
        route.fulfill(status=200, content_type="application/json", body=__import__("json").dumps(body))

    def sync_route(route):
        request = route.request
        sync_requests.append(request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(
                {
                    "plan_hash": "a" * 64,
                    "attempted": 1,
                    "media_created": 1,
                    "collection_created": 1,
                    "skipped": 0,
                    "failed": 0,
                    "remaining_from_preview": 0,
                    "batch_size": 1,
                    "results": [],
                }
            ),
        )

    try:
        page.route("**/api/integrations/floppy/status", status_route)
        page.route("**/api/integrations/floppy/preview", preview_route)
        page.route("**/api/integrations/floppy/sync", sync_route)
        page.on("dialog", lambda dialog: dialog.accept())

        page.goto(live_server)
        expect(page.locator("#floppyStatus")).to_have_text("Connesso")
        page.get_by_role("button", name="Confronta cataloghi").click()

        expect(page.locator("#floppyPreviewResult")).to_contain_text("Media mancanti")
        expect(page.get_by_role("button", name="Sincronizza 1")).to_be_visible()
        page.get_by_role("button", name="Sincronizza 1").click()

        expect(page.locator("#floppyPreviewResult")).to_contain_text("Ultimo batch")
        expect(page.locator("#floppyPreviewResult")).to_contain_text("Collection allineata")
        assert sync_requests == [{"plan_hash": "a" * 64, "batch_size": 1}]
        assert preview_calls["count"] == 2
    finally:
        context.close()


def test_physical_copy_detail_and_edit_flow(browser, live_server):
    context, page = new_page(browser)
    try:
        import_csv(page, live_server)
        page.get_by_role("link", name="Apri Synthetic Alpha").click()

        expect(page.get_by_text("Copie fisiche", exact=True)).to_be_visible()
        expect(page.locator(".physical-copy-card")).to_have_count(1)
        expect(page.locator(".physical-copy-card")).to_contain_text("1234567890123")
        expect(page.locator(".physical-copy-card")).to_contain_text("Kallax A1")
        expect(page.locator(".physical-copy-card")).to_contain_text("Italian")

        page.get_by_role("button", name="Modifica").click()
        expect(page.locator("#copyDialog")).to_be_visible()
        expect(page.locator("#copyBarcode")).to_have_value("1234567890123")
        expect(page.locator("#copyLocation")).to_have_value("Kallax A1")

        page.locator("#copyBarcode").fill("555-000-111")
        page.locator("#copyLocation").fill("Kallax Z9")
        page.locator("#copyNotes").fill("Copia aggiornata da UI")
        page.get_by_role("button", name="Salva copia").click()

        expect(page.locator("#copyDialog")).not_to_be_visible()
        expect(page.locator(".physical-copy-card")).to_contain_text("555-000-111")
        expect(page.locator(".physical-copy-card")).to_contain_text("Kallax Z9")
        expect(page.locator(".physical-copy-card")).to_contain_text("Copia aggiornata da UI")

        response = page.request.get(f"{live_server}/api/games/900001/copies")
        assert response.ok
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["barcode_normalized"] == "555000111"
        assert items[0]["inventory_location"] == "Kallax Z9"
    finally:
        context.close()


def test_scanner_manual_lookup_finds_existing_copy(browser, live_server):
    context, page = new_page(browser)
    try:
        import_csv(page, live_server)

        page.get_by_role("button", name="Scansiona").click()
        expect(page.locator("#scannerDialog")).to_be_visible()
        page.locator("#scannerBarcode").fill("1234-5678-90123")
        page.get_by_role("button", name="Cerca", exact=True).click()

        expect(page.locator("#scannerResult")).to_contain_text("Copia trovata")
        expect(page.locator("#scannerResult")).to_contain_text("Synthetic Alpha")
        expect(page.locator("#scannerResult")).to_contain_text("1234567890123")
        expect(page.get_by_role("link", name="Apri gioco")).to_be_visible()
    finally:
        context.close()


def test_scanner_assigns_unknown_barcode_to_single_unbarcoded_copy(browser, live_server):
    context, page = new_page(browser)
    try:
        import_csv(page, live_server)

        page.get_by_role("button", name="Scansiona").click()
        page.locator("#scannerBarcode").fill("222-222-222")
        page.get_by_role("button", name="Cerca", exact=True).click()

        expect(page.locator("#scannerResult")).to_contain_text("Barcode non associato")
        page.locator("#scannerGameSearch").fill("Beta")
        page.locator("#scannerSearchGames").click()
        expect(page.locator(".scanner-game-choice")).to_have_count(1)
        expect(page.locator(".scanner-game-choice")).to_contain_text("Synthetic Beta Expansion")
        page.locator(".scanner-game-choice").click()

        expect(page.locator("#scannerResult")).to_contain_text("Copia trovata")
        expect(page.locator("#scannerResult")).to_contain_text("Synthetic Beta Expansion")

        response = page.request.get(f"{live_server}/api/games/900002/copies")
        assert response.ok
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["barcode"] == "222-222-222"
        assert items[0]["barcode_normalized"] == "222222222"
    finally:
        context.close()


def test_mobile_topbar_and_scanner_dialog_do_not_overflow(browser, live_server):
    context, page = new_page(browser, mobile=True)
    try:
        page.goto(live_server)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        expect(page.get_by_role("button", name="Scansiona")).to_be_visible()

        page.get_by_role("button", name="Scansiona").click()
        expect(page.locator("#scannerDialog")).to_be_visible()
        box = page.locator("#scannerDialog").bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= 391
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    finally:
        context.close()



def test_document_upload_list_download_and_dedup(browser, live_server):
    context, page = new_page(browser)
    pdf_bytes = b"%PDF-1.4\nBoardGameCompanion test manual\n%%EOF\n"
    try:
        import_csv(page, live_server)
        page.get_by_role("link", name="Apri Synthetic Alpha").click()

        expect(page.get_by_role("heading", name="Manuali e documenti", exact=True)).to_be_visible()
        expect(page.locator(".game-document-card")).to_have_count(0)
        expect(page.locator(".document-empty")).to_contain_text(
            "Nessun manuale o documento registrato"
        )

        page.locator("#addDocument").click()
        expect(page.locator("#documentDialog")).to_be_visible()
        page.locator("#documentFile").set_input_files(
            {
                "name": "manuale-italiano.pdf",
                "mimeType": "application/pdf",
                "buffer": pdf_bytes,
            }
        )
        expect(page.locator("#documentFileName")).to_have_text("manuale-italiano.pdf")
        page.locator("#documentTitle").fill("Regolamento italiano")
        page.locator("#documentVersion").fill("v1.2")
        page.locator("#documentEdition").fill("Retail IT")
        page.locator("#documentSourceUrl").fill("https://publisher.example/manuale.pdf")
        page.locator("#documentOfficial").check()
        page.locator("#saveDocument").click()

        expect(page.locator("#documentDialog")).not_to_be_visible()
        expect(page.locator(".game-document-card")).to_have_count(1)
        card = page.locator(".game-document-card")
        expect(card).to_contain_text("Regolamento italiano")
        expect(card).to_contain_text("Regolamento")
        expect(card).to_contain_text("IT")
        expect(card).to_contain_text("Ufficiale")
        expect(card).to_contain_text("Versione v1.2")
        expect(card).to_contain_text("Edizione Retail IT")
        expect(card).to_contain_text("manuale-italiano.pdf")
        expect(card).to_contain_text("Upload manuale")
        expect(card).to_contain_text("https://publisher.example/manuale.pdf")

        href = page.locator(".document-download").get_attribute("href")
        assert href is not None
        response = page.request.get(f"{live_server}{href}")
        assert response.ok
        assert response.body() == pdf_bytes

        api_response = page.request.get(f"{live_server}/api/games/900001/documents")
        assert api_response.ok
        assert api_response.json()["count"] == 1

        page.locator("#addDocument").click()
        page.locator("#documentFile").set_input_files(
            {
                "name": "stesso-file-altro-nome.pdf",
                "mimeType": "application/pdf",
                "buffer": pdf_bytes,
            }
        )
        page.locator("#documentTitle").fill("Titolo che non deve duplicare il file")
        page.locator("#saveDocument").click()

        expect(page.locator("#documentDialog")).not_to_be_visible()
        expect(page.locator(".game-document-card")).to_have_count(1)
        expect(page.locator("#toast")).to_contain_text("già presente")
        api_response = page.request.get(f"{live_server}/api/games/900001/documents")
        assert api_response.json()["count"] == 1
    finally:
        context.close()


def test_document_metadata_is_escaped(browser, live_server):
    context, page = new_page(browser)
    pdf_bytes = b"%PDF-1.4\nXSS metadata test\n%%EOF\n"
    malicious = '<img src=x onerror="window.__bgc_doc_xss=1">'
    try:
        import_csv(page, live_server)
        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        page.locator("#addDocument").click()
        page.locator("#documentFile").set_input_files(
            {
                "name": "safe.pdf",
                "mimeType": "application/pdf",
                "buffer": pdf_bytes,
            }
        )
        page.locator("#documentTitle").fill(malicious)
        page.locator("#saveDocument").click()

        expect(page.locator(".game-document-title")).to_contain_text("<img src=x")
        expect(page.locator(".game-document-card")).to_contain_text("Non ufficiale")
        assert page.evaluate("window.__bgc_doc_xss") is None
        assert page.locator(".game-document-title img").count() == 0
    finally:
        context.close()


def test_mobile_document_dialog_and_cards_do_not_overflow(browser, live_server):
    context, page = new_page(browser, mobile=True)
    try:
        import_csv(page, live_server)
        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        page.locator("#addDocument").click()

        expect(page.locator("#documentDialog")).to_be_visible()
        box = page.locator("#documentDialog").bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= 391
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

        page.locator("#cancelDocumentDialog").click()
        expect(page.locator("#documentDialog")).not_to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    finally:
        context.close()


def test_review_queue_ui_allows_explicit_approval(browser, live_server):
    context, page = new_page(browser)
    state = {"status": "pending", "decision_source": None}
    decisions = []

    def item():
        return {
            "id": "review-1",
            "bgg_id": 900001,
            "game_title": "Synthetic Alpha",
            "candidate_key": "a" * 64,
            "candidate": {
                "provider": "community-example",
                "source_kind": "community",
                "url": "https://community.example/rules.pdf",
                "language": "it",
                "document_type": "rulebook",
                "official": False,
                "confidence": 70,
            },
            "policy_action": "review",
            "policy_reasons": [
                "review:unofficial-source",
                "review:confidence:70",
                "bgg_id:exact",
                "language:it",
            ],
            "status": state["status"],
            "decision_source": state["decision_source"],
            "decision_note": None,
            "created_at": "2026-09-23T18:00:00+00:00",
            "updated_at": "2026-09-23T18:00:00+00:00",
            "decided_at": None,
        }

    def pending_route(route):
        items = [item()] if state["status"] == "pending" else []
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(
                {
                    "total": len(items),
                    "limit": 50,
                    "offset": 0,
                    "items": items,
                    "corrupt_count": 0,
                    "corrupt_items": [],
                }
            ),
        )

    def decided_route(route):
        items = [item()] if state["status"] != "pending" else []
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(
                {
                    "total": len(items),
                    "limit": 50,
                    "offset": 0,
                    "items": items,
                    "corrupt_count": 0,
                    "corrupt_items": [],
                }
            ),
        )

    def decision_route(route):
        decisions.append(route.request.post_data_json)
        state["status"] = "approved"
        state["decision_source"] = "user"
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(item()),
        )

    try:
        page.route(
            re.compile(r".*/api/rulebook-reviews\?status=pending&limit=50&offset=0$"),
            pending_route,
        )
        page.route(
            re.compile(r".*/api/rulebook-reviews\?status=decided&limit=50&offset=0$"),
            decided_route,
        )
        page.route("**/api/rulebook-reviews/review-1/decision", decision_route)

        page.goto(live_server)
        page.get_by_role("link", name="Revisioni").click()
        expect(page).to_have_url(f"{live_server}/reviews")
        expect(page.get_by_role("heading", name="Coda di revisione")).to_be_visible()
        expect(page.locator(".review-card")).to_have_count(1)
        expect(page.locator(".review-card")).to_contain_text("Synthetic Alpha")
        expect(page.locator(".review-card")).to_contain_text("community")
        expect(page.get_by_role("button", name="Approva")).to_be_visible()

        page.get_by_role("button", name="Approva").click()
        expect(page.locator("#toast")).to_contain_text("Candidato approvato")
        expect(page.locator(".review-status-approved")).to_have_text("Approvato")
        assert decisions == [{"decision": "approved"}]
    finally:
        context.close()


def test_review_queue_ui_paginates_all_pending_items(browser, live_server):
    context, page = new_page(browser)

    def make_item(index):
        return {
            "id": f"review-{index}",
            "bgg_id": 900001,
            "game_title": f"Review Game {index:03d}",
            "candidate_key": f"{index:064x}",
            "candidate": {
                "provider": "community-example",
                "source_kind": "community",
                "url": f"https://community.example/{index}.pdf",
                "language": "it",
                "document_type": "rulebook",
                "official": False,
                "confidence": 70,
            },
            "policy_action": "review",
            "policy_reasons": ["review:unofficial-source"],
            "status": "pending",
            "decision_source": None,
            "decision_note": None,
            "created_at": "2026-09-23T18:00:00+00:00",
            "updated_at": "2026-09-23T18:00:00+00:00",
            "decided_at": None,
        }
    items = [make_item(index) for index in range(101)]

    def pending_route(route):
        match = re.search(r"offset=(\d+)$", route.request.url)
        assert match is not None
        offset = int(match.group(1))
        page_items = items[offset:offset + 50]
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(
                {
                    "total": len(items),
                    "limit": 50,
                    "offset": offset,
                    "items": page_items,
                    "corrupt_count": 0,
                    "corrupt_items": [],
                }
            ),
        )

    def decided_route(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(
                {
                    "total": 0,
                    "limit": 50,
                    "offset": 0,
                    "items": [],
                    "corrupt_count": 0,
                    "corrupt_items": [],
                }
            ),
        )
    try:
        page.route(
            re.compile(
                r".*/api/rulebook-reviews\?status=pending&limit=50&offset=\d+$"
            ),
            pending_route,
        )
        page.route(
            re.compile(r".*/api/rulebook-reviews\?status=decided&limit=50&offset=0$"),
            decided_route,
        )

        page.goto(f"{live_server}/reviews")
        expect(page.locator(".review-counter")).to_have_text("101 pending")
        expect(page.locator(".review-card")).to_have_count(50)
        expect(page.locator(".review-pagination")).to_contain_text("1–50 di 101")

        page.get_by_role("button", name="Successiva").click()
        expect(page.locator(".review-card")).to_have_count(50)
        expect(page.locator(".review-pagination")).to_contain_text("51–100 di 101")

        page.get_by_role("button", name="Successiva").click()
        expect(page.locator(".review-card")).to_have_count(1)
        expect(page.locator(".review-card")).to_contain_text("Review Game 100")
        expect(page.locator(".review-pagination")).to_contain_text("101–101 di 101")
    finally:
        context.close()


def test_review_queue_ui_refreshes_after_conflicting_decision(browser, live_server):
    context, page = new_page(browser)
    state = {"status": "pending", "decision_source": None}

    def item():
        return {
            "id": "review-conflict",
            "bgg_id": 900001,
            "game_title": "Concurrent Game",
            "candidate_key": "b" * 64,
            "candidate": {
                "provider": "community-example",
                "source_kind": "community",
                "url": "https://community.example/conflict.pdf",
                "language": "it",
                "document_type": "rulebook",
                "official": False,
                "confidence": 70,
            },
            "policy_action": "review",
            "policy_reasons": ["review:unofficial-source"],
            "status": state["status"],
            "decision_source": state["decision_source"],
            "decision_note": None,
            "created_at": "2026-09-23T18:00:00+00:00",
            "updated_at": "2026-09-23T18:00:00+00:00",
            "decided_at": None,
        }
    def list_payload(pending):
        items = [item()] if (state["status"] == "pending") is pending else []
        return __import__("json").dumps(
            {
                "total": len(items),
                "limit": 50,
                "offset": 0,
                "items": items,
                "corrupt_count": 0,
                "corrupt_items": [],
            }
        )

    def pending_route(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=list_payload(True),
        )

    def decided_route(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=list_payload(False),
        )

    def conflict_route(route):
        state["status"] = "rejected"
        state["decision_source"] = "user"
        route.fulfill(
            status=409,
            content_type="application/json",
            body='{"detail":"Rulebook review is already rejected"}',
        )
    try:
        page.route(
            re.compile(r".*/api/rulebook-reviews\?status=pending&limit=50&offset=0$"),
            pending_route,
        )
        page.route(
            re.compile(r".*/api/rulebook-reviews\?status=decided&limit=50&offset=0$"),
            decided_route,
        )
        page.route(
            "**/api/rulebook-reviews/review-conflict/decision",
            conflict_route,
        )

        page.goto(f"{live_server}/reviews")
        expect(page.get_by_role("button", name="Approva")).to_be_visible()
        page.get_by_role("button", name="Approva").click()

        expect(page.locator("#toast")).to_contain_text("already rejected")
        expect(page.locator(".review-status-rejected")).to_have_text("Rifiutato")
        expect(page.get_by_role("button", name="Approva")).to_have_count(0)
    finally:
        context.close()


def test_rulebook_updates_ui_schedule_and_run_controls(browser, live_server):
    context, page = new_page(browser)
    state = {
        "id": "target-1",
        "review_item_id": "review-update-1",
        "bgg_id": 900001,
        "game_title": "Synthetic Alpha",
        "provider": "publisher-test",
        "source_kind": "official_publisher",
        "url": "https://publisher.example/rules.pdf",
        "review_status": "approved",
        "enabled": True,
        "interval_seconds": 2592000,
        "next_check_at": "2026-10-23T18:00:00+00:00",
        "last_checked_at": None,
        "last_success_at": None,
        "last_document_id": None,
        "last_sha256": None,
        "consecutive_failures": 0,
        "last_outcome": None,
        "last_failure_code": None,
        "last_failure_message": None,
        "leased": False,
        "lease_until": None,
        "created_at": "2026-09-23T18:00:00+00:00",
        "updated_at": "2026-09-23T18:00:00+00:00",
    }
    patch_requests = []
    run_requests = []

    def list_route(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(
                {
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                    "items": [state.copy()],
                    "worker": {
                        "enabled": True,
                        "poll_seconds": 60,
                        "batch_size": 5,
                    },
                }
            ),
        )

    def patch_route(route):
        payload = route.request.post_data_json
        patch_requests.append(payload)
        if "enabled" in payload:
            state["enabled"] = payload["enabled"]
        if "interval_seconds" in payload:
            state["interval_seconds"] = payload["interval_seconds"]
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(state),
        )

    def run_route(route):
        run_requests.append(True)
        state["last_outcome"] = "created"
        state["last_checked_at"] = "2026-09-23T19:00:00+00:00"
        state["last_success_at"] = state["last_checked_at"]
        state["last_document_id"] = "document-1"
        state["last_sha256"] = "a" * 64
        state["next_check_at"] = "2026-09-30T19:00:00+00:00"
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(
                {
                    "target_id": state["id"],
                    "review_item_id": state["review_item_id"],
                    "run_id": "run-1",
                    "outcome": "created",
                    "document": {"id": "document-1"},
                    "next_check_at": state["next_check_at"],
                }
            ),
        )

    try:
        page.route(
            re.compile(r".*/api/rulebook-updates\?limit=50&offset=0$"),
            list_route,
        )
        page.route(
            "**/api/rulebook-updates/review-update-1/run",
            run_route,
        )
        page.route(
            "**/api/rulebook-updates/review-update-1",
            patch_route,
        )

        page.goto(live_server)
        page.get_by_role("link", name="Aggiornamenti").click()
        expect(page).to_have_url(f"{live_server}/updates")
        expect(
            page.get_by_role("heading", name="Aggiornamenti automatici")
        ).to_be_visible()
        expect(page.locator(".update-card")).to_have_count(1)
        expect(page.locator(".update-card")).to_contain_text("Synthetic Alpha")
        expect(page.locator(".update-worker-state")).to_contain_text(
            "ogni 1 minuto"
        )

        page.locator(".update-interval").select_option("604800")
        expect(page.locator(".update-interval")).to_have_value("604800")
        assert {"interval_seconds": 604800} in patch_requests

        page.get_by_role("button", name="Pausa").click()
        expect(page.get_by_role("button", name="Riprendi")).to_be_visible()
        expect(page.locator(".update-status-paused")).to_have_text("In pausa")
        assert {"enabled": False} in patch_requests

        page.get_by_role("button", name="Controlla ora").click()
        expect(page.locator("#toast")).to_contain_text("Nuova versione archiviata")
        expect(page.locator(".update-card")).to_contain_text("SHA aaaaaaaaaaaa")
        assert len(run_requests) == 1

        page.get_by_role("button", name="Riprendi").click()
        expect(page.get_by_role("button", name="Pausa")).to_be_visible()
        expect(page.locator(".update-status-created")).to_have_text(
            "Nuova versione"
        )
    finally:
        context.close()


def test_mobile_updates_page_has_no_horizontal_overflow(browser, live_server):
    context, page = new_page(browser, mobile=True)

    def list_route(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(
                {
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                    "items": [
                        {
                            "id": "target-mobile",
                            "review_item_id": "review-mobile",
                            "bgg_id": 900001,
                            "game_title": "Synthetic Alpha",
                            "provider": "publisher-test",
                            "source_kind": "official_publisher",
                            "url": "https://publisher.example/very/long/path/rules.pdf",
                            "review_status": "approved",
                            "enabled": True,
                            "interval_seconds": 2592000,
                            "next_check_at": "2026-10-23T18:00:00+00:00",
                            "last_checked_at": None,
                            "last_success_at": None,
                            "last_document_id": None,
                            "last_sha256": None,
                            "consecutive_failures": 0,
                            "last_outcome": None,
                            "last_failure_code": None,
                            "last_failure_message": None,
                            "leased": False,
                            "lease_until": None,
                            "created_at": "2026-09-23T18:00:00+00:00",
                            "updated_at": "2026-09-23T18:00:00+00:00",
                        }
                    ],
                    "worker": {
                        "enabled": True,
                        "poll_seconds": 60,
                        "batch_size": 5,
                    },
                }
            ),
        )

    try:
        page.route(
            re.compile(r".*/api/rulebook-updates\?limit=50&offset=0$"),
            list_route,
        )
        page.goto(f"{live_server}/updates")
        expect(page.locator(".update-card")).to_have_count(1)
        expect(page.get_by_role("button", name="Controlla ora")).to_be_visible()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        )
    finally:
        context.close()


def _install_camera_stub(page, *, native_code: str | None = None) -> None:
    page.add_init_script(
        """
        Object.defineProperty(navigator, "mediaDevices", {
          configurable: true,
          value: {
            getUserMedia: async () => {
              window.__bgcCameraRequests = (window.__bgcCameraRequests || 0) + 1;
              return new MediaStream();
            },
          },
        });
        HTMLMediaElement.prototype.play = function () { return Promise.resolve(); };
        try {
          Object.defineProperty(HTMLMediaElement.prototype, "readyState", {
            configurable: true,
            get() { return 4; },
          });
        } catch (_) {}
        """
    )
    if native_code is not None:
        page.add_init_script(
            f"""
            window.BarcodeDetector = class {{
              static async getSupportedFormats() {{
                return ["ean_13", "ean_8", "upc_a", "upc_e"];
              }}
              constructor(options) {{ window.__bgcNativeFormats = options.formats; }}
              async detect() {{ return [{{rawValue: {native_code!r}}}]; }}
            }};
            """
        )


def test_barcode_scanner_starts_camera_and_native_lookup_automatically(browser, live_server):
    context, page = new_page(browser, mobile=True)
    _install_camera_stub(page, native_code="8001234567890")
    try:
        page.goto(live_server)
        page.get_by_role("button", name="Scansiona").click()

        expect(page.locator("#scannerDialog")).to_be_visible()
        expect(page.locator("#scannerResult")).to_contain_text("Barcode non associato")
        expect(page.locator("#scannerBarcode")).to_have_value("8001234567890")
        assert page.evaluate("window.__bgcCameraRequests") == 1
        assert page.evaluate("window.__bgcNativeFormats") == [
            "ean_13",
            "ean_8",
            "upc_a",
            "upc_e",
        ]
        expect(page.locator("#scannerManualFallback")).not_to_have_attribute("open", "")
    finally:
        context.close()


def test_barcode_scanner_uses_zxing_when_native_detector_is_missing(browser, live_server):
    context, page = new_page(browser, mobile=True)
    _install_camera_stub(page)
    page.add_init_script(
        """
        Object.defineProperty(window, "BarcodeDetector", {
          configurable: true,
          value: undefined,
        });
        """
    )
    page.route(
        "**/static/zxing-browser-0.2.1.min.js",
        lambda route: route.fulfill(
            content_type="application/javascript",
            body="""
            window.ZXingBrowser = {
              BarcodeFormat: {EAN_13: 1, EAN_8: 2, UPC_A: 3, UPC_E: 4},
              BrowserMultiFormatReader: class {
                set possibleFormats(value) { window.__bgcZxingFormats = value; }
                async decodeFromConstraints(constraints, video, callback) {
                  window.__bgcZxingConstraints = constraints;
                  video.srcObject = new MediaStream();
                  setTimeout(() => callback({getText: () => "9781234567897"}), 0);
                  return {stop() { window.__bgcZxingStopped = true; }};
                }
              }
            };
            """,
        ),
    )

    try:
        page.goto(live_server)
        page.get_by_role("button", name="Scansiona").click()
        expect(page.locator("#scannerResult")).to_contain_text("Barcode non associato")
        expect(page.locator("#scannerBarcode")).to_have_value("9781234567897")
        assert page.evaluate("window.__bgcZxingFormats") == [1, 2, 3, 4]
        constraints = page.evaluate("window.__bgcZxingConstraints")
        assert constraints["video"]["facingMode"]["ideal"] == "environment"
        assert page.evaluate("window.__bgcZxingStopped") is True
    finally:
        context.close()


def test_manual_barcode_submit_wins_over_late_camera_detection(browser, live_server):
    context, page = new_page(browser, mobile=True)
    _install_camera_stub(page)
    page.add_init_script(
        """
        window.BarcodeDetector = class {
          static async getSupportedFormats() {
            return ["ean_13", "ean_8", "upc_a", "upc_e"];
          }
          async detect() {
            window.__bgcDetectCalls = (window.__bgcDetectCalls || 0) + 1;
            return await new Promise((resolve) => {
              window.__bgcResolveDetection = resolve;
            });
          }
        };
        """
    )
    try:
        page.goto(live_server)
        page.get_by_role("button", name="Scansiona").click()
        page.wait_for_function("window.__bgcResolveDetection !== undefined")

        page.locator("#scannerManualFallback").evaluate("(node) => { node.open = true; }")
        page.locator("#scannerBarcode").fill("1234567890123")
        page.get_by_role("button", name="Cerca").click()
        expect(page.locator("#scannerResult")).to_contain_text("Barcode non associato")
        expect(page.locator("#scannerBarcode")).to_have_value("1234567890123")

        page.evaluate(
            "window.__bgcResolveDetection([{rawValue: '9999999999999'}])"
        )
        page.wait_for_timeout(100)
        expect(page.locator("#scannerBarcode")).to_have_value("1234567890123")
        expect(page.locator("#scannerResult")).to_contain_text("1234567890123")
    finally:
        context.close()


def test_closing_scanner_cancels_pending_camera_start(browser, live_server):
    context, page = new_page(browser, mobile=True)
    page.add_init_script(
        """
        Object.defineProperty(navigator, "mediaDevices", {
          configurable: true,
          value: {
            getUserMedia: () => new Promise((resolve) => {
              window.__bgcResolveCamera = resolve;
            }),
          },
        });
        HTMLMediaElement.prototype.play = function () { return Promise.resolve(); };
        window.BarcodeDetector = class {
          static async getSupportedFormats() {
            return ["ean_13", "ean_8", "upc_a", "upc_e"];
          }
          async detect() { return []; }
        };
        """
    )
    try:
        page.goto(live_server)
        page.get_by_role("button", name="Scansiona").click()
        page.wait_for_function("typeof window.__bgcResolveCamera === 'function'")

        page.get_by_role("button", name="Chiudi scanner").click()
        expect(page.locator("#scannerDialog")).not_to_be_visible()

        page.evaluate(
            "window.__bgcResolveCamera(new MediaStream())"
        )
        page.wait_for_timeout(100)
        assert page.evaluate(
            "document.querySelector('#scannerVideo').srcObject === null"
        )
        expect(page.locator("#scannerDialog")).not_to_be_visible()
    finally:
        context.close()


def test_game_metadata_refresh_renders_cached_floppy_metadata(browser, live_server):
    context, page = new_page(browser)
    state = {"refreshed": False}
    try:
        import_csv(page, live_server)
        base_game = page.request.get(f"{live_server}/api/games/900001").json()
        metadata = {
            "provider": "floppy_bgg",
            "source": "bgg",
            "media_id": "900001",
            "title": "Synthetic Alpha provider",
            "source_url": "https://boardgamegeek.com/boardgame/900001",
            "image_url": "https://cf.geekdo-images.com/alpha.jpg",
            "synopsis": "Fresh provider synopsis.",
            "genres": ["Strategy", "Economic"],
            "score": 8.3,
            "score_count": 5000,
            "year_published": 2024,
            "players": "1-5 players",
            "playtime": "45 min",
            "min_age": "12+",
            "designers": "A. Designer",
            "publishers": "Provider Publisher",
            "payload_sha256": "a" * 64,
            "fetched_at": "2026-09-24T12:00:00+00:00",
            "updated_at": "2026-09-24T12:00:00+00:00",
        }
        def metadata_route(route):
            request = route.request
            if request.method == "POST":
                state["refreshed"] = True
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "bgg_id": 900001,
                            "changed": True,
                            "metadata": metadata,
                        }
                    ),
                )
                return

            body = dict(base_game)
            body["metadata"] = metadata if state["refreshed"] else None
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(body),
            )

        page.route(
            re.compile(r".*/api/games/900001(?:/metadata/refresh)?$"),
            metadata_route,
        )
        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        expect(page.locator(".metadata-heading .section-subtitle")).to_contain_text(
            "Il catalogo resta utilizzabile offline"
        )
        expect(page.locator(".detail-cover-image")).to_have_count(0)

        page.get_by_role("button", name="Aggiorna metadata").click()

        expect(page.locator(".detail-main h1")).to_have_text("Synthetic Alpha")
        expect(page.locator(".metadata-synopsis")).to_have_text(
            "Fresh provider synopsis."
        )
        expect(page.locator(".detail-cover-image")).to_have_attribute(
            "src",
            "https://cf.geekdo-images.com/alpha.jpg",
        )
        expect(page.locator(".metadata-facts")).to_contain_text("Provider Publisher")
        expect(page.locator(".metadata-facts")).to_contain_text("Strategy, Economic")
        assert state["refreshed"] is True
    finally:
        context.close()
