from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.main import app
from boardgamecompanion.settings import settings


def configure_paths(tmp_path: Path) -> None:
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"


def clear_bgg_env() -> None:
    os.environ.pop("BGC_BGG_APPLICATION_TOKEN", None)


def test_bgg_settings_persist_without_returning_secret(tmp_path: Path) -> None:
    clear_bgg_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        initial = client.get("/api/settings/bgg")
        assert initial.status_code == 200
        assert initial.json()["configured"] is False

        saved = client.put(
            "/api/settings/bgg",
            json={"application_token": "super-secret-bgg-token"},
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["configured"] is True
        assert body["application_token_source"] == "stored"
        assert body["stored_application_token_configured"] is True
        assert "super-secret-bgg-token" not in saved.text
        assert "application_token" not in body

        reloaded = client.get("/api/settings/bgg")
        assert reloaded.status_code == 200
        assert reloaded.json() == body
        assert "super-secret-bgg-token" not in reloaded.text

        kept = client.put(
            "/api/settings/bgg",
            json={"application_token": None},
        )
        assert kept.status_code == 200
        assert kept.json()["configured"] is True

        cleared = client.put(
            "/api/settings/bgg",
            json={
                "application_token": None,
                "clear_application_token": True,
            },
        )
        assert cleared.status_code == 200
        assert cleared.json()["configured"] is False


def test_bgg_environment_token_overrides_stored_value(tmp_path: Path) -> None:
    clear_bgg_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        client.put(
            "/api/settings/bgg",
            json={"application_token": "stored-token"},
        )

        os.environ["BGC_BGG_APPLICATION_TOKEN"] = "env-token"
        try:
            response = client.get("/api/settings/bgg")
        finally:
            clear_bgg_env()

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["application_token_source"] == "environment"
    assert body["overrides"]["application_token"] is True
    assert body["stored_application_token_configured"] is True
    assert "env-token" not in response.text
    assert "stored-token" not in response.text


def test_bgg_verify_requires_configured_token(tmp_path: Path) -> None:
    clear_bgg_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/settings/bgg/verify")

    assert response.status_code == 409
    assert "not configured" in response.json()["detail"]
