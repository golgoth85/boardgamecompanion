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
    assert 'src="/static/app.js"' in response.text


def test_web_game_route_is_spa_entrypoint(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/games/900001")

    assert response.status_code == 200
    assert "Importa BGG CSV" in response.text


def test_web_reviews_route_is_spa_entrypoint(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/reviews")

    assert response.status_code == 200
    assert "Revisioni" in response.text


def test_web_updates_route_is_spa_entrypoint(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        response = client.get("/updates")

    assert response.status_code == 200
    assert "Aggiornamenti" in response.text


def test_static_assets_are_served(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        css = client.get("/static/app.css")
        js = client.get("/static/app.js")

    assert css.status_code == 200
    assert "--accent:" in css.text
    assert js.status_code == 200
    assert "renderCatalog" in js.text
    assert "renderReviews" in js.text
    assert "renderUpdates" in js.text
