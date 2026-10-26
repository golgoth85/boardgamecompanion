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
    assert 'id="scannerDialog"' in response.text
    assert 'id="settingsCollapseExpansions"' in response.text
    assert "Giochi giocati" in response.text
    assert 'id="settingsDialogTitle">Impostazioni<' in response.text
    assert "Priorità provider" in response.text
    assert 'id="bggApplicationToken"' in response.text
    assert 'id="youtubeApiKey"' in response.text
    assert 'data-settings-tab="crowdfunding"' in response.text
    assert 'id="apifyToken"' in response.text
    assert 'id="verifyApifyToken"' in response.text
    assert 'id="lmstudioWolEnabled"' in response.text
    assert 'id="lmstudioWolMac"' in response.text
    assert 'id="lmstudioWakeButton"' in response.text
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
    assert ".assistant-thread" in extra_css.text
    assert ".tutorial-video-grid" in extra_css.text
    assert js.status_code == 200
    assert "renderCatalog" in js.text
    assert "renderReviews" in js.text
    assert "renderUpdates" in js.text
    assert "renderDiscovery" in js.text
    assert "renderCrowdfunding" in js.text
    assert "renderSuggestions" in js.text
    assert "/api/catalog/suggestions" in js.text
    assert "Potrebbe piacerti perché" in js.text
    assert "game_summary_it" in js.text
    assert "why_it_fits" in js.text
    assert "data-suggestions-sort" in js.text
    assert "object-fit:contain" in extra_css.text
    assert "Più diversi" in js.text
    assert 'openSettingsDialog("crowdfunding")' in js.text
    assert "Configura Kickstarter" in js.text
    assert "tutorialDiscoveryAction" in js.text
    assert "tutorialVideoCard" in js.text
    assert "tutorial-video-frame" in js.text
    assert "scannerPhotoCanvas" in js.text
    assert "result.auto_match" in js.text
    assert 'aria-label="Scansiona barcode"' in js.text
    assert '<span aria-hidden="true">+</span>' in js.text
    assert "aspect-ratio: 4 / 3" in css.text
    assert "-webkit-line-clamp: 2" in css.text
    assert zxing.status_code == 200
    assert "ZXingBrowser" in zxing.text


def test_icon_sprite_covers_every_referenced_icon(tmp_path: Path) -> None:
    import re

    _configure(tmp_path)
    with TestClient(app) as client:
        sprite = client.get("/static/icons.svg")
        index = client.get("/")
        js = client.get("/static/app.js")
        personal = client.get("/static/personal-components.js")
        utils = client.get("/static/ui-utils.js")

    assert sprite.status_code == 200
    defined = set(re.findall(r'<symbol id="(i-[a-z-]+)"', sprite.text))
    sources = index.text + js.text + personal.text + utils.text
    used = set(re.findall(r"/static/icons\.svg#(i-[a-z-]+)", sources))
    used |= {f"i-{name}" for name in re.findall(r'icon\(\s*"([a-z-]+)"', js.text)}
    used |= {f"i-{name}" for name in ("crown", "diamond", "gem", "hourglass")}
    assert used
    assert used <= defined, used - defined


def test_static_assets_are_revalidated_after_deploys(tmp_path: Path) -> None:
    _configure(tmp_path)
    with TestClient(app) as client:
        first = client.get("/static/app.js")
        assert first.status_code == 200
        assert first.headers["cache-control"] == "no-cache"
        again = client.get("/static/app.js", headers={"If-None-Match": first.headers["etag"]})
        assert again.status_code == 304 and again.content == b""
        assert again.headers["cache-control"] == "no-cache"

        # The versioned third-party bundle never changes: keep it cached.
        bundle = client.get("/static/zxing-browser-0.2.1.min.js")
        assert "immutable" in bundle.headers["cache-control"]

        for path in ("/", "/games/1", "/lists", "/wishlist", "/reviews"):
            assert client.get(path).headers["cache-control"] == "no-cache", path


def test_game_page_has_regenerate_button_but_no_publisher_box() -> None:
    script = (Path(__file__).parents[1] / "src/boardgamecompanion/web/app.js").read_text(encoding="utf-8")
    assert 'id="regenerateDescription"' in script
    assert "gamePublisherDescription" not in script
