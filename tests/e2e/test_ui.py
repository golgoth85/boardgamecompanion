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
from urllib.parse import parse_qs, urlsplit
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

SAMPLE = Path(__file__).parents[1] / "fixtures" / "bgg_collection_sample.csv"


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        launch_kwargs = {}
        candidates = [
            os.environ.get("BGC_CHROMIUM_EXECUTABLE"),
            os.environ.get("CHROMIUM_EXECUTABLE"),
            "/root/bin/chromium",
            "/mnt/user/appdata/claude-code-home/bin/chromium",
        ]
        def usable_browser_executable(candidate: str | None) -> bool:
            if not candidate:
                return False
            try:
                return Path(candidate).is_file() and os.access(candidate, os.X_OK)
            except OSError:
                return False

        executable = next(
            (
                candidate
                for candidate in candidates
                if usable_browser_executable(candidate)
            ),
            None,
        )
        if executable:
            launch_kwargs["executable_path"] = executable
        browser = p.chromium.launch(**launch_kwargs)
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
    import_button = page.get_by_role("button", name="Importa BGG CSV")
    if not import_button.is_visible():
        page.get_by_role("button", name="Apri navigazione").click()
    import_button.click()
    page.locator("#csvFile").set_input_files(str(path))
    page.get_by_role("button", name="Importa", exact=True).click()
    expect(page.locator("#importResult")).to_contain_text("Import completato.")
    expect(page.locator("#importResult")).to_contain_text("2 righe")
    page.get_by_role("button", name="Chiudi").click()
    expect(page.locator("#importDialog")).not_to_be_visible()


def open_barcode_scanner(page) -> None:
    scanner_button = page.get_by_role("button", name="Importa barcode")
    if not scanner_button.is_visible():
        page.get_by_role("button", name="Apri navigazione").click()
    scanner_button.click()


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


def test_app_bootstrap_diagnostics(browser, live_server):
    context, page = new_page(browser)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        response = page.goto(live_server)
        assert response is not None and response.ok
        static_response = page.request.get(f"{live_server}/static/app.js")
        assert static_response.ok
        page.wait_for_timeout(500)
        assert errors == []
        assert page.evaluate("typeof googleRulebookSearchUrl") == "function"
        expect(page.get_by_role("button", name="Importa BGG CSV")).to_be_visible()
    finally:
        context.close()


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



def test_catalog_card_list_switch_persists_and_mobile_stays_bounded(browser, live_server):
    context, page = new_page(browser)
    try:
        import_csv(page, live_server)
        expect(page.locator(".catalog-results-cards")).to_be_visible()
        expect(page.locator(".game-card")).to_have_count(2)

        page.get_by_role("button", name="☷ Lista").click()
        expect(page.locator(".catalog-results-list")).to_be_visible()
        expect(page.locator(".catalog-list-row")).to_have_count(2)
        expect(page.locator("#listViewButton")).to_have_attribute("aria-pressed", "true")

        page.reload()
        expect(page.locator(".catalog-results-list")).to_be_visible()
        expect(page.locator("#listViewButton")).to_have_attribute("aria-pressed", "true")
    finally:
        context.close()

    mobile_context, mobile_page = new_page(browser, mobile=True)
    try:
        import_csv(mobile_page, live_server)
        mobile_page.get_by_role("button", name="☷ Lista").click()
        expect(mobile_page.locator(".catalog-results-list")).to_be_visible()
        assert mobile_page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        )
        mobile_page.get_by_role("button", name="▦ Card").click()
        expect(mobile_page.locator(".catalog-results-cards")).to_be_visible()
        assert mobile_page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        )
    finally:
        mobile_context.close()


def test_advanced_catalog_search_filters_by_play_context(browser, live_server):
    context, page = new_page(browser)
    try:
        import_csv(page, live_server)
        details = page.locator("#advancedSearch")
        expect(details).not_to_have_attribute("open", "")
        details.locator("summary").click()

        page.locator("#idealPlayers").fill("2")
        page.locator("#idealPlayers").blur()
        page.locator("#playerAge").fill("12")
        page.locator("#playerAge").blur()
        page.locator("#weightFilter").select_option("light")
        page.locator("#maxMinutes").fill("60")
        page.locator("#maxMinutes").blur()
        page.locator("#minRating").fill("7")
        page.locator("#minRating").blur()

        expect(page.locator(".game-card")).to_have_count(1)
        expect(page.locator(".card-title")).to_have_text("Synthetic Beta Expansion")
        expect(page.get_by_text("Partite", exact=True)).to_have_count(0)

        page.get_by_role("button", name="Azzera filtri avanzati").click()
        expect(page.locator(".game-card")).to_have_count(2)
    finally:
        context.close()


def test_catalog_collapses_inferred_expansions_under_base_game(browser, live_server):
    context, page = new_page(browser)
    base_game = {
        "bgg_id": 100,
        "title": "Root",
        "original_title": "Root",
        "year_published": 2018,
        "item_type": "standalone",
        "players": {"min": 2, "max": 4},
        "play_time": {"playing": 90, "min": 60, "max": 90},
        "bgg": {
            "average": 8.1,
            "average_weight": 3.8,
            "recommended_age": "10",
        },
        "collection": {"own": True, "num_plays": 12},
        "bgg_metadata": {"cover_url": None},
    }
    expansion = {
        "bgg_id": 101,
        "title": "Root: The Riverfolk Expansion",
        "original_title": "Root: The Riverfolk Expansion",
        "year_published": 2018,
        "item_type": "expansion",
        "players": {"min": 1, "max": 6},
        "play_time": {"playing": 90, "min": 60, "max": 90},
        "bgg": {
            "average": 8.4,
            "average_weight": 3.7,
            "recommended_age": "10",
        },
        "collection": {"own": True, "num_plays": 3},
        "bgg_metadata": {"cover_url": None},
    }

    def games_route(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "items": [base_game, expansion],
                    "total": 2,
                    "limit": 250,
                    "offset": 0,
                    "sort": "title",
                }
            ),
        )

    try:
        page.route(re.compile(r".*/api/games\?.*"), games_route)
        page.route(
            "**/api/catalog/stats",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"total": 2, "standalone": 1, "expansions": 1, "owned": 2}
                ),
            ),
        )
        page.goto(live_server)

        expect(page.locator(".game-card")).to_have_count(1)
        badge = page.locator(".expansion-count-badge")
        expect(badge).to_have_count(1)
        expect(badge).to_contain_text("1")
        expect(page.locator(".expansion-mini-card")).to_be_hidden()

        badge.click()
        expect(page.locator(".expansion-mini-card")).to_be_visible()
        expect(page.locator(".expansion-mini-card")).to_contain_text(
            "Root: The Riverfolk Expansion"
        )

        page.locator("#collapseExpansions").uncheck()
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

        expect(page.locator(".game-card")).to_have_count(30)
        expect(page.locator("#pagination")).to_be_hidden()
    finally:
        context.close()


def test_mobile_layout_has_no_horizontal_overflow(browser, live_server):
    context, page = new_page(browser, mobile=True)
    try:
        import_csv(page, live_server)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        expect(page.get_by_role("button", name="Apri navigazione")).to_be_visible()
        expect(page.locator(".game-card")).to_have_count(2)

        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        expect(page.locator(".detail-main h1")).to_have_text("Synthetic Alpha")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

        page.get_by_role("button", name="Apri navigazione").click()
        expect(page.get_by_role("button", name="Importa BGG CSV")).to_be_visible()
        page.get_by_role("button", name="Importa BGG CSV").click()
        expect(page.locator("#importDialog")).to_be_visible()
        box = page.locator("#importDialog").bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= 391
        page.get_by_role("button", name="Chiudi").click()
    finally:
        context.close()


def test_sidebar_separates_daily_and_admin_navigation(browser, live_server):
    context, page = new_page(browser)
    try:
        page.goto(live_server)
        sidebar = page.locator("#appSidebar")
        expect(sidebar).to_be_visible()
        expect(sidebar.get_by_text("Ludoteca", exact=True)).to_be_visible()
        expect(sidebar.get_by_text("Collezione", exact=True)).to_be_visible()
        expect(sidebar.get_by_text("Amministrazione", exact=True)).to_be_visible()
        expect(sidebar.get_by_role("link", name="Catalogo")).to_have_attribute(
            "aria-current", "page"
        )
        expect(sidebar.get_by_role("link", name="Fonti da verificare")).to_be_visible()
        expect(sidebar.get_by_role("link", name="Aggiornamenti regolamenti")).to_be_visible()
        expect(sidebar.get_by_role("link", name="Ricerca regolamenti")).to_be_visible()
        expect(sidebar.get_by_role("button", name="Provider e AI")).to_be_visible()
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


def test_settings_save_bgg_and_rag_without_revealing_secrets(browser, live_server):
    context, page = new_page(browser)
    try:
        page.goto(live_server)
        page.get_by_role("button", name="Provider e AI").click()
        expect(page.locator("#settingsDialog")).to_be_visible()
        expect(page.locator("#settingsDialogTitle")).to_have_text("Provider e AI")

        page.locator("#bggApplicationToken").fill("browser-secret-bgg-token")
        page.locator("#ragEmbeddingOrder").fill("lmstudio,ollama")
        page.locator("#ragGenerationOrder").fill("lmstudio,gemini")
        page.locator("#lmstudioSettings summary").click()
        page.locator("#geminiSettings summary").click()
        page.locator("#lmstudioUrl").fill("http://lmstudio.test:1234")
        page.locator("#lmstudioEmbeddingModel").fill("embed-test")
        page.locator("#lmstudioGenerationModel").fill("qwen3-14b")
        page.locator("#lmstudioApiKey").fill("browser-secret-lmstudio-key")
        page.locator("#geminiApiKey").fill("browser-secret-gemini-key")
        page.get_by_role("button", name="Salva", exact=True).click()

        expect(page.locator("#settingsResult")).to_contain_text("Impostazioni salvate")
        bgg_response = page.request.get(f"{live_server}/api/settings/bgg")
        assert bgg_response.ok
        bgg_body = bgg_response.json()
        assert bgg_body["configured"] is True
        assert bgg_body["application_token_source"] == "stored"
        assert "browser-secret-bgg-token" not in bgg_response.text()

        rag_response = page.request.get(f"{live_server}/api/settings/rag")
        assert rag_response.ok
        rag_body = rag_response.json()
        assert rag_body["embedding_provider_order"] == ["lmstudio", "ollama"]
        assert rag_body["generation_provider_order"] == ["lmstudio", "gemini"]
        assert rag_body["effective_embedding_provider"] == "lmstudio"
        assert rag_body["effective_generation_provider"] == "lmstudio"
        assert rag_body["automatic_fallback"] is False
        assert rag_body["providers"]["lmstudio"]["api_key_configured"] is True
        assert rag_body["providers"]["gemini"]["api_key_configured"] is True
        assert "browser-secret-lmstudio-key" not in rag_response.text()
        assert "browser-secret-gemini-key" not in rag_response.text()

        page.get_by_role("button", name="Chiudi impostazioni").click()
        page.get_by_role("button", name="Provider e AI").click()
        page.locator("#lmstudioSettings summary").click()
        page.locator("#geminiSettings summary").click()

        expect(page.locator("#bggApplicationToken")).to_have_value("")
        expect(page.locator("#bggTokenHint")).to_contain_text("Token BGG configurato")
        expect(page.locator("#clearTokenRow")).to_be_visible()
        expect(page.locator("#lmstudioApiKey")).to_have_value("")
        expect(page.locator("#lmstudioApiKeyHint")).to_contain_text("API key configurata")
        expect(page.locator("#clearLmstudioApiKeyRow")).to_be_visible()
        expect(page.locator("#geminiApiKey")).to_have_value("")
        expect(page.locator("#geminiApiKeyHint")).to_contain_text("API key configurata")
        expect(page.locator("#clearGeminiApiKeyRow")).to_be_visible()
    finally:
        context.close()


def test_mobile_settings_and_drawer_accessibility(browser, live_server):
    context, page = new_page(browser, mobile=True)
    try:
        page.goto(live_server)
        menu = page.get_by_role("button", name="Apri navigazione")
        expect(menu).to_have_attribute("aria-expanded", "false")

        menu.click()
        expect(page.locator("#sidebarToggle")).to_have_attribute(
            "aria-expanded", "true"
        )
        expect(page.get_by_role("button", name="Provider e AI")).to_be_visible()
        page.get_by_role("button", name="Provider e AI").click()

        expect(page.locator("#settingsDialog")).to_be_visible()
        expect(page.locator("#appSidebar")).not_to_be_in_viewport()
        expect(page.locator("#bggSettings")).to_have_attribute("open", "")
        expect(page.locator("#ollamaSettings")).not_to_have_attribute("open", "")
        expect(page.locator("#lmstudioSettings")).not_to_have_attribute("open", "")
        expect(page.locator("#geminiSettings")).not_to_have_attribute("open", "")
        box = page.locator("#settingsDialog").bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= 391
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

        page.get_by_role("button", name="Chiudi impostazioni").click()
        menu = page.get_by_role("button", name="Apri navigazione")
        menu.click()
        expect(page.locator("#sidebarToggle")).to_have_attribute("aria-label", "Chiudi navigazione")
        page.keyboard.press("Escape")
        expect(page.get_by_role("button", name="Apri navigazione")).to_have_attribute(
            "aria-expanded", "false"
        )
        expect(page.locator("#appSidebar")).not_to_be_in_viewport()
    finally:
        context.close()


def test_mobile_admin_surfaces_do_not_overflow(browser, live_server):
    context, page = new_page(browser, mobile=True)
    try:
        for path, heading in (
            ("/reviews", "Fonti da verificare"),
            ("/discovery", "Ricerca regolamenti"),
            ("/updates", "Aggiornamenti regolamenti"),
        ):
            page.goto(f"{live_server}{path}")
            expect(page.get_by_role("heading", name=heading)).to_be_visible()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth + 1"
            )
    finally:
        context.close()


def test_game_detail_is_game_centric_and_rules_are_secondary(browser, live_server):
    context, page = new_page(browser)
    try:
        import_csv(page, live_server)
        page.get_by_role("link", name="Apri Synthetic Alpha").click()

        expect(page.locator(".game-summary-rail")).to_be_visible()
        expect(page.get_by_text("Giocatori", exact=True)).to_be_visible()
        expect(page.get_by_text("Età consigliata", exact=True)).to_be_visible()
        expect(page.get_by_text("10+", exact=True)).to_be_visible()

        description = page.get_by_role("heading", name="Descrizione")
        rules = page.get_by_role("heading", name="Regole")
        expect(description).to_be_visible()
        expect(rules).to_be_visible()
        description_box = description.bounding_box()
        rules_box = rules.bounding_box()
        assert description_box is not None and rules_box is not None
        assert description_box["y"] < rules_box["y"]

        expect(page.get_by_role("button", name="+ Aggiungi copia").first).to_be_visible()
        expect(page.get_by_text("1 copia registrata", exact=True)).to_be_visible()

        expect(page.get_by_role("heading", name="Fai una domanda sul regolamento")).to_be_visible()
        expect(page.locator("#ragQuestion")).to_be_visible()

        technical = page.locator(".technical-game-details")
        expect(technical).not_to_have_attribute("open", "")

        expect(page.locator("#gameDiscoveryStatus")).not_to_be_visible()
        expect(page.get_by_role("button", name="Cerca automaticamente")).to_be_visible()
        expect(page.get_by_role("button", name="Carica PDF")).to_be_visible()
    finally:
        context.close()


def test_physical_copy_detail_and_edit_flow(browser, live_server):
    context, page = new_page(browser)
    try:
        import_csv(page, live_server)
        page.get_by_role("link", name="Apri Synthetic Alpha").click()

        expect(page.get_by_text("1 copia registrata", exact=True)).to_be_visible()
        expect(page.locator(".physical-copy-card")).not_to_be_visible()
        page.locator(".copy-details-disclosure summary").click()
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

        open_barcode_scanner(page)
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

        open_barcode_scanner(page)
        page.locator("#scannerBarcode").fill("222-222-222")
        page.get_by_role("button", name="Cerca", exact=True).click()

        expect(page.locator("#scannerResult")).to_contain_text("Barcode non associato")
        page.locator("#scannerGameSearch").fill("Beta")
        page.locator("#scannerSearchGames").click()
        expect(page.locator(".scanner-game-choice")).to_have_count(1)
        expect(page.locator(".scanner-game-choice")).to_contain_text("Synthetic Beta Expansion")
        page.locator(".scanner-game-choice").click()

        expect(page.locator("#scannerResult")).to_contain_text("Barcode importato")
        expect(page.locator("#scannerResult")).to_contain_text("Synthetic Beta Expansion")
        expect(page.get_by_role("button", name="Scansiona prossimo")).to_be_visible()
        page.get_by_role("button", name="Scansiona prossimo").click()
        expect(page.locator("#scannerBarcode")).to_have_value("")

        response = page.request.get(f"{live_server}/api/games/900002/copies")
        assert response.ok
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["barcode"] == "222-222-222"
        assert items[0]["barcode_normalized"] == "222222222"
    finally:
        context.close()


def test_mobile_sidebar_and_scanner_dialog_do_not_overflow(browser, live_server):
    context, page = new_page(browser, mobile=True)
    try:
        page.goto(live_server)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        expect(page.get_by_role("button", name="Apri navigazione")).to_be_visible()
        expect(page.get_by_role("button", name="Importa barcode")).not_to_be_visible()

        page.get_by_role("button", name="Apri navigazione").click()
        expect(page.get_by_role("button", name="Importa barcode")).to_be_visible()
        page.wait_for_function(
            "document.querySelector('#appSidebar').getBoundingClientRect().x >= 0"
        )
        sidebar_box = page.locator("#appSidebar").bounding_box()
        assert sidebar_box is not None
        assert sidebar_box["x"] >= 0
        assert sidebar_box["x"] + sidebar_box["width"] <= 390

        open_barcode_scanner(page)
        expect(page.locator("#scannerDialog")).to_be_visible()
        expect(page.locator("#appSidebar")).not_to_be_in_viewport()
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

        expect(page.get_by_text("Regolamento non presente", exact=True)).to_be_visible()
        expect(page.locator(".game-document-card")).to_have_count(0)

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
        page.get_by_role("link", name="Fonti da verificare").click()
        expect(page).to_have_url(f"{live_server}/reviews")
        expect(page.get_by_role("heading", name="Fonti da verificare")).to_be_visible()
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
        expect(page.locator(".review-counter")).to_have_text("101 da verificare")
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
            page.get_by_role("heading", name="Aggiornamenti regolamenti")
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
        open_barcode_scanner(page)

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
        open_barcode_scanner(page)
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
        open_barcode_scanner(page)
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
        open_barcode_scanner(page)
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


def _rag_document_response() -> dict:
    return {
        "bgg_id": 900001,
        "count": 1,
        "items": [
            {
                "id": "doc-rag",
                "document_type": "rulebook",
                "language": "it",
                "title": "Regolamento RAG",
                "version_label": "v2",
                "edition": "Retail IT",
                "original_filename": "rules.pdf",
                "size_bytes": 12345,
                "source": {
                    "kind": "official_publisher",
                    "provider": "publisher-test",
                    "url": "https://publisher.example/rules.pdf",
                    "official": True,
                },
            }
        ],
    }


def _rag_answer_response() -> dict:
    return {
        "status": "answer",
        "reason": None,
        "game": {"id": 1, "bgg_id": 900001, "title": "Synthetic Alpha"},
        "query": "Come si prepara?",
        "answer": "Si usano cinque carte. [1]",
        "claims": [
            {
                "text": 'Si usano cinque carte <img src=x onerror="window.__bgc_rag_xss=1">.',
                "citations": [1],
                "supports": [
                    {
                        "citation": 1,
                        "evidence_id": "E1",
                        "quote": "Setup uses five cards.",
                    }
                ],
            }
        ],
        "citations": [
            {
                "index": 1,
                "document": {
                    "id": "doc-rag",
                    "document_type": "rulebook",
                    "language": "it",
                    "version_label": "v2",
                    "edition": "Retail IT",
                    "published_at": "2026-01-01",
                    "official": True,
                    "source_kind": "official_publisher",
                    "source_provider": "publisher-test",
                    "source_url": "https://publisher.example/rules.pdf",
                },
                "page": {
                    "id": "page-2",
                    "number": 2,
                    "text_sha256": "c" * 64,
                },
                "evidence": [
                    {
                        "evidence_id": "E1",
                        "chunk_id": "chunk-1",
                        "chunk_index": 0,
                        "score": 0.94,
                    }
                ],
            }
        ],
        "retrieval": {
            "provider": "fake-embed",
            "model": "embed-v1",
            "model_digest": "e" * 64,
            "coverage": {
                "current_document_count": 1,
                "embedded_document_count": 1,
                "missing_document_ids": [],
            },
            "selected_tier": {
                "rank": 0,
                "name": "official-requested-language",
            },
            "retrieved_evidence_count": 1,
            "generation_evidence_count": 1,
        },
        "conflicts": {
            "has_conflict": True,
            "selected_cohort": {
                "version_label": "v2",
                "edition": "Retail IT",
            },
            "excluded_cohorts": [
                {
                    "version_label": "v1",
                    "edition": "Retail IT",
                    "candidate_count": 2,
                }
            ],
        },
        "generation": {
            "provider": "ollama",
            "model": "rules-test:latest",
            "model_digest": "f" * 64,
        },
    }


def test_rag_query_ui_renders_grounded_citations_and_conflicts(browser, live_server):
    context, page = new_page(browser)
    answer_requests = []

    def answer_route(route):
        answer_requests.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_rag_answer_response()),
        )
    try:
        import_csv(page, live_server)
        page.route(
            "**/api/games/900001/documents",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(_rag_document_response()),
            ),
        )
        page.route(
            "**/api/documents/doc-rag/embeddings",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "document_id": "doc-rag",
                        "current": {"id": "embedding-run"},
                        "latest_run": {"id": "embedding-run"},
                    }
                ),
            ),
        )
        page.route("**/api/games/900001/answer", answer_route)

        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        expect(page.get_by_role("heading", name="Fai una domanda sul regolamento")).to_be_visible()
        expect(page.locator("#ragIndexStatus")).to_contain_text("1/1 documenti indicizzati")

        page.locator("#ragQuestion").fill("Come si prepara?")
        page.locator("#ragAsk").click()
        expect(page.locator(".rag-answer")).to_be_visible()
        expect(page.locator(".rag-claim")).to_contain_text("<img src=x")
        assert page.locator(".rag-claim img").count() == 0
        assert page.evaluate("window.__bgc_rag_xss") is None
        expect(page.locator(".rag-conflict")).to_contain_text("Conflitto di versione")
        expect(page.locator(".rag-conflict")).to_contain_text("Versione v1")
        expect(page.locator(".rag-citation-card")).to_contain_text("Pagina 2")
        expect(page.locator(".rag-citation-card")).to_contain_text("Versione v2")
        expect(page.locator(".rag-citation-card")).to_contain_text("Retail IT")
        expect(page.locator(".rag-citation-card")).to_contain_text("Ufficiale")

        pdf_href = page.locator(".rag-citation-card a").get_attribute("href")
        assert pdf_href == "/api/documents/doc-rag/file#page=2"
        assert answer_requests == [
            {
                "query": "Come si prepara?",
                "language": "it",
                "document_type": None,
                "version_label": None,
                "edition": None,
            }
        ]

        page.locator(".rag-citation-ref").click()
        expect(page.locator(".rag-citation-card")).to_have_class(
            re.compile(r".*rag-highlight.*")
        )
        page.locator(".rag-document-jump").click()
        expect(page.locator(".game-document-card")).to_have_class(
            re.compile(r".*rag-highlight.*")
        )
    finally:
        context.close()


def test_rag_not_found_can_prepare_full_document_index(browser, live_server):
    context, page = new_page(browser)
    build_calls = []

    def embeddings_route(route):
        if route.request.method == "GET":
            route.fulfill(
                status=409,
                content_type="application/json",
                body=json.dumps({"detail": "Document has no current P7B chunk index"}),
            )
            return
        build_calls.append("embeddings")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "created": True,
                    "embedding_index": {"id": "embedding-run", "chunk_count": 3},
                }
            ),
        )

    def ingest_route(route):
        build_calls.append("ingest")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"created": True, "ingest": {"id": "parse-run"}}),
        )
    def chunks_route(route):
        build_calls.append("chunks")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"created": True, "index": {"id": "chunk-run"}}),
        )

    not_found = {
        "status": "not_found",
        "reason": "index_incomplete",
        "game": {"id": 1, "bgg_id": 900001, "title": "Synthetic Alpha"},
        "query": "Quando finisce il turno?",
        "answer": None,
        "claims": [],
        "citations": [],
        "retrieval": {
            "provider": "fake",
            "model": "embed",
            "model_digest": "e" * 64,
            "coverage": {
                "current_document_count": 1,
                "embedded_document_count": 0,
                "missing_document_ids": ["doc-rag"],
            },
            "selected_tier": None,
        },
        "conflicts": {
            "has_conflict": False,
            "selected_cohort": None,
            "excluded_cohorts": [],
        },
        "generation": None,
    }
    try:
        import_csv(page, live_server)
        page.route(
            "**/api/games/900001/documents",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(_rag_document_response()),
            ),
        )
        page.route("**/api/documents/doc-rag/embeddings", embeddings_route)
        page.route("**/api/documents/doc-rag/embeddings/build", embeddings_route)
        page.route("**/api/documents/doc-rag/ingest", ingest_route)
        page.route("**/api/documents/doc-rag/chunks/build", chunks_route)
        page.route(
            "**/api/games/900001/answer",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(not_found),
            ),
        )

        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        expect(page.locator("#ragIndexStatus")).to_contain_text("Indice incompleto")

        page.locator("#ragQuestion").fill("Quando finisce il turno?")
        page.locator("#ragAsk").click()
        expect(page.locator(".rag-state-not-found")).to_contain_text(
            "Nessuna risposta affidabile"
        )
        expect(page.locator(".rag-state-not-found")).to_contain_text(
            "indice dei documenti non è completo"
        )
        page.locator(".rag-state-not-found .rag-prepare-index").click()
        expect(page.locator("#ragIndexStatus")).to_contain_text("Indice pronto")
        assert build_calls == ["ingest", "chunks", "embeddings"]
    finally:
        context.close()


def test_mobile_rag_query_panel_has_no_horizontal_overflow(browser, live_server):
    context, page = new_page(browser, mobile=True)
    try:
        import_csv(page, live_server)
        page.get_by_role("link", name="Apri Synthetic Alpha").click()

        expect(page.get_by_role("heading", name="Fai una domanda sul regolamento")).to_be_visible()
        expect(page.locator("#ragIndexStatus")).to_contain_text(
            "Nessun documento archiviato"
        )
        box = page.locator("#ragPanel").bounding_box()
        assert box is not None
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= 391
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        )
    finally:
        context.close()



@pytest.mark.parametrize(
    ("title", "expected_phrase"),
    [
        ('Game" site:example.invalid "manual', "Game site:example.invalid manual"),
        ('Game\\" site:example.invalid "manual', "Game site:example.invalid manual"),
        ('“Game” site:example.invalid „manual‟', "Game site:example.invalid manual"),
        ('My <img src=x onerror="alert(1)">', "My <img src=x onerror= alert(1) >"),
        ("L'isola del tesoro", "L'isola del tesoro"),
        ("天空の城ラピュタ – Café 🔥", "天空の城ラピュタ – Café 🔥"),
        ("Cafe\u0301 et l'Île", "Café et l'Île"),
        ("Alpha\u0001\tBeta\u2028Gamma\\", "Alpha Beta Gamma"),
    ],
)
def test_google_rulebook_query_treats_title_as_literal_phrase(
    browser, live_server, title, expected_phrase
):
    context, page = new_page(browser)
    try:
        page.goto(live_server)
        # Exercise the shipped JavaScript, not a second implementation in Python.
        href = page.evaluate("(value) => googleRulebookSearchUrl(value)", title)
        parsed = urlsplit(href)
        assert (parsed.scheme, parsed.netloc, parsed.path) == (
            "https", "www.google.com", "/search"
        )
        query = parse_qs(parsed.query)["q"][0]
        assert query == f'"{expected_phrase}" regolamento italiano pdf'
        assert query.count('"') == 2
    finally:
        context.close()


def test_google_rulebook_query_control_only_title_uses_safe_fallback(
    browser, live_server
):
    context, page = new_page(browser)
    try:
        page.goto(live_server)
        href = page.evaluate(
            "(value) => googleRulebookSearchUrl(value)", '\u0001"\\\u2028'
        )
        assert parse_qs(urlsplit(href).query)["q"] == ["regolamento italiano pdf"]
    finally:
        context.close()


def test_google_rulebook_query_injection_from_imported_csv(browser, live_server, tmp_path):
    malicious_title = 'Game" site:example.invalid "manual'
    with SAMPLE.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames
        rows = list(reader)
    rows[0]["objectname"] = malicious_title
    rows[0]["originalname"] = malicious_title
    fixture = tmp_path / "untrusted_title.csv"
    with fixture.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    context, page = new_page(browser)
    google_requests = []
    context.on(
        "request",
        lambda request: google_requests.append(request.url)
        if request.url.startswith("https://www.google.com/")
        else None,
    )
    try:
        import_csv(page, live_server, fixture)
        page.goto(f"{live_server}/games/900001")
        expect(page.locator(".detail-main h1")).to_have_text(malicious_title)
        expect(page.get_by_role("link", name="Cerca PDF su Google")).to_have_count(0)
        expect(page.get_by_role("button", name="Cerca automaticamente")).to_be_visible()
        href = page.evaluate("(value) => googleRulebookSearchUrl(value)", malicious_title)
        query = parse_qs(urlsplit(href).query)["q"][0]
        assert query == '"Game site:example.invalid manual" regolamento italiano pdf'
        assert google_requests == []
        expect(page.get_by_role("button", name="Carica PDF")).to_be_visible()
    finally:
        context.close()


def test_rulebook_search_uses_known_sources_then_google_only_after_clean_miss(
    browser, live_server
):
    context, page = new_page(browser)
    state = {
        "candidates_found": 0,
        "provider_failures": 0,
        "last_finished_at": None,
    }
    discovery_requests = []
    google_requests = []
    context.on(
        "request",
        lambda request: google_requests.append(request.url)
        if request.url.startswith("https://www.google.com/")
        else None,
    )

    def discovery_status(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(state),
        )

    def discovery_run(route):
        discovery_requests.append(route.request.method)
        state["last_finished_at"] = "2026-10-02T08:00:00+00:00"
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                **state,
                "review_items": [],
            }),
        )

    try:
        import_csv(page, live_server)
        page.route(
            re.compile(r".*/api/games/900001/rulebook-discovery$"),
            discovery_status,
        )
        page.route(
            re.compile(r".*/api/games/900001/rulebook-discovery/run$"),
            discovery_run,
        )
        page.get_by_role("link", name="Apri Synthetic Alpha").click()

        panel = page.locator(".rules-simple")
        action = panel.get_by_role("button", name="Cerca automaticamente")
        expect(action).to_be_visible()
        expect(panel.get_by_role("link", name="Cerca PDF su Google")).to_have_count(0)

        action.click()
        expect(page.locator("#toast")).to_contain_text(
            "Nessuna fonte nota trovata. Premi di nuovo"
        )
        action = panel.get_by_role("button", name="Cerca PDF su Google")
        expect(action).to_be_visible()
        assert discovery_requests == ["POST"]
        assert google_requests == []

        # The second-click Google state is derived from persisted discovery state,
        # not a transient browser flag.
        page.reload()
        panel = page.locator(".rules-simple")
        action = panel.get_by_role("button", name="Cerca PDF su Google")
        expect(action).to_be_visible()
        assert google_requests == []

        page.evaluate(
            """() => {
              window.open = (url, target, features) => {
                window.__bgcGoogleFallback = {url, target, features};
                return null;
              };
            }"""
        )
        action.click()
        opened = page.evaluate("window.__bgcGoogleFallback")
        assert opened["target"] == "_blank"
        assert "noopener" in opened["features"]
        assert "noreferrer" in opened["features"]
        parsed = urlsplit(opened["url"])
        assert (parsed.scheme, parsed.netloc, parsed.path) == (
            "https", "www.google.com", "/search"
        )
        assert parse_qs(parsed.query)["q"] == [
            '"Synthetic Alpha" regolamento italiano pdf'
        ]
        assert discovery_requests == ["POST"]
        assert google_requests == []
    finally:
        context.close()


def test_rulebook_search_allows_google_after_completed_miss_with_provider_failure(
    browser, live_server
):
    context, page = new_page(browser)
    state = {
        "candidates_found": 0,
        "provider_failures": 0,
        "last_finished_at": None,
    }
    requests = []

    def discovery_status(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(state),
        )

    def discovery_run(route):
        requests.append(route.request.method)
        state.update({
            "candidates_found": 0,
            "provider_failures": 1,
            "last_finished_at": "2026-10-02T08:00:00+00:00",
        })
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({**state, "review_items": []}),
        )

    try:
        import_csv(page, live_server)
        page.route(
            re.compile(r".*/api/games/900001/rulebook-discovery$"),
            discovery_status,
        )
        page.route(
            re.compile(r".*/api/games/900001/rulebook-discovery/run$"),
            discovery_run,
        )
        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        button = page.get_by_role("button", name="Cerca automaticamente")
        expect(button).to_be_visible()
        button.click()
        expect(page.locator("#toast")).to_contain_text(
            "alcune fonti note non hanno risposto"
        )
        expect(page.get_by_role("button", name="Cerca PDF su Google")).to_be_visible()
        assert requests == ["POST"]
    finally:
        context.close()


def test_rulebook_search_candidates_keep_single_known_source_action(
    browser, live_server
):
    context, page = new_page(browser)
    state = {
        "candidates_found": 0,
        "provider_failures": 0,
        "last_finished_at": None,
    }
    requests = []

    def discovery_status(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(state),
        )

    def discovery_run(route):
        requests.append(route.request.method)
        state.update({
            "candidates_found": 2,
            "provider_failures": 0,
            "last_finished_at": "2026-10-02T08:00:00+00:00",
        })
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                **state,
                "review_items": [
                    {"status": "approved"},
                    {"status": "pending"},
                ],
            }),
        )

    try:
        import_csv(page, live_server)
        page.route(
            re.compile(r".*/api/games/900001/rulebook-discovery$"),
            discovery_status,
        )
        page.route(
            re.compile(r".*/api/games/900001/rulebook-discovery/run$"),
            discovery_run,
        )
        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        page.get_by_role("button", name="Cerca automaticamente").click()
        expect(page.locator("#toast")).to_contain_text(
            "Trovate 2 fonti: 1 approvate, 1 da verificare"
        )
        expect(
            page.get_by_role("button", name="Aggiorna ricerca automatica")
        ).to_be_visible()
        expect(page.get_by_role("button", name="Cerca PDF su Google")).to_have_count(0)
        expect(page.locator(".game-document-card")).to_have_count(0)
        assert requests == ["POST"]
    finally:
        context.close()


def test_rulebook_search_panel_is_readable_on_mobile(browser, live_server):
    context, page = new_page(browser, mobile=True)
    try:
        import_csv(page, live_server)
        page.get_by_role("link", name="Apri Synthetic Alpha").click()
        button = page.get_by_role("button", name="Cerca automaticamente")
        expect(button).to_be_visible()
        button.click(trial=True)
        rect = button.bounding_box()
        assert rect is not None
        assert rect["width"] >= 44 and rect["height"] >= 24
        assert rect["x"] >= 0 and rect["x"] + rect["width"] <= 391
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    finally:
        context.close()

