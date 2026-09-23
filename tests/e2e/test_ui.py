from __future__ import annotations

import csv
import os
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
