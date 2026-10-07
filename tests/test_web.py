from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.main import app
from boardgamecompanion.settings import settings


def _configure(tmp_path: Path) -> None:
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"


def test_web_home_is_served(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "BoardGameCompanion" in response.text
    assert "Scansiona barcode" in response.text
    assert 'id="settingsDialogTitle">Impostazioni<' in response.text
    assert "Priorità provider" in response.text
    assert 'id="bggApplicationToken"' in response.text
    assert 'id="youtubeApiKey"' in response.text
    assert 'data-settings-tab="crowdfunding"' in response.text
    assert 'id="apifyToken"' in response.text
    assert 'id="verifyApifyToken"' in response.text
    assert "Floppy" not in response.text
    assert 'src="/static/zxing-browser-0.2.1.min.js"' in response.text
    assert 'src="/static/app.js"' in response.text


def test_web_game_route_is_spa_entrypoint(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/games/900001")

    assert response.status_code == 200
    assert "Importa CSV BGG" in response.text


def test_web_reviews_route_is_spa_entrypoint(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/reviews")

    assert response.status_code == 200
    assert "Fonti da verificare" in response.text


def test_web_updates_route_is_spa_entrypoint(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/updates")

    assert response.status_code == 200
    assert "Aggiornamenti" in response.text


def test_web_discovery_route_is_spa_entrypoint(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/discovery")

    assert response.status_code == 200
    assert "Ricerca regolamenti" in response.text


def test_web_crowdfunding_route_is_spa_entrypoint(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/crowdfunding")

    assert response.status_code == 200
    assert "Crowdfunding" in response.text


def test_web_suggestions_route_is_spa_entrypoint(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/suggestions")

    assert response.status_code == 200
    assert "Suggerimenti" in response.text


def test_static_assets_are_served(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        css = client.get("/static/app.css")
        extra_css = client.get("/static/game-centric.css")
        js = client.get("/static/app.js")
        zxing = client.get("/static/zxing-browser-0.2.1.min.js")

    assert css.status_code == 200
    assert "--accent:" in css.text
    assert extra_css.status_code == 200
    assert ".assistant-dialog" in extra_css.text
    assert ".tutorial-video-grid" in extra_css.text
    assert js.status_code == 200
    assert "renderCatalog" in js.text
    assert "renderReviews" in js.text
    assert "renderUpdates" in js.text
    assert "renderDiscovery" in js.text
    assert "renderCrowdfunding" in js.text
    assert "renderSuggestions" in js.text
    assert "/api/catalog/suggestions" in js.text
    assert 'id="lmstudioWolEnabled"' in client.get("/").text
    assert 'openSettingsDialog("crowdfunding")' in js.text
    assert "Configura Apify" in js.text
    assert "tutorialDiscoveryAction" in js.text
    assert "tutorialVideoCard" in js.text
    assert "tutorial-video-frame" in js.text
    assert zxing.status_code == 200
    assert "ZXingBrowser" in zxing.text
