from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.main import app
from boardgamecompanion.settings import settings

FIXTURE = Path(__file__).parent / "fixtures" / "bgg_collection_sample.csv"


def test_tutorial_video_api_is_optional_until_youtube_key_is_configured(
    tmp_path: Path,
) -> None:
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"

    with TestClient(app) as client:
        with FIXTURE.open("rb") as handle:
            imported = client.post(
                "/api/imports/bgg-csv",
                files={"file": ("collection.csv", handle, "text/csv")},
            )
        assert imported.status_code == 200

        listed = client.get("/api/games/900001/tutorial-videos")
        assert listed.status_code == 200
        assert listed.json() == {
            "bgg_id": 900001,
            "configured": False,
            "count": 0,
            "items": [],
        }

        discovery = client.post("/api/games/900001/tutorial-videos/discover")
        assert discovery.status_code == 409
        assert "not configured" in discovery.json()["detail"]
