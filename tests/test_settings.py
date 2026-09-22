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


def clear_floppy_env() -> None:
    for key in (
        "BGC_FLOPPY_URL",
        "BGC_FLOPPY_API_KEY",
        "BGC_FLOPPY_TIMEOUT_SECONDS",
        "BGC_FLOPPY_VERIFY_TLS",
    ):
        os.environ.pop(key, None)


def test_floppy_settings_persist_without_returning_secret(tmp_path: Path) -> None:
    clear_floppy_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        initial = client.get("/api/settings/floppy")
        assert initial.status_code == 200
        assert initial.json()["api_key_configured"] is False
        assert initial.json()["timeout_seconds"] == 45

        saved = client.put(
            "/api/settings/floppy",
            json={
                "url": "http://floppy:8000/",
                "api_key": "super-secret-token",
                "timeout_seconds": 12,
                "verify_tls": False,
            },
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["url"] == "http://floppy:8000"
        assert body["api_key_configured"] is True
        assert body["api_key_source"] == "stored"
        assert body["timeout_seconds"] == 12
        assert body["verify_tls"] is False
        assert "super-secret-token" not in saved.text
        assert "api_key" not in body

        reloaded = client.get("/api/settings/floppy")
        assert reloaded.status_code == 200
        assert reloaded.json() == body
        assert "super-secret-token" not in reloaded.text

        kept = client.put(
            "/api/settings/floppy",
            json={
                "url": "http://floppy:8000",
                "api_key": None,
                "timeout_seconds": 9,
                "verify_tls": True,
            },
        )
        assert kept.status_code == 200
        assert kept.json()["api_key_configured"] is True

        cleared = client.put(
            "/api/settings/floppy",
            json={
                "url": "http://floppy:8000",
                "api_key": None,
                "clear_api_key": True,
                "timeout_seconds": 9,
                "verify_tls": True,
            },
        )
        assert cleared.status_code == 200
        assert cleared.json()["api_key_configured"] is False


def test_environment_url_and_token_override_stored_values(tmp_path: Path) -> None:
    clear_floppy_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        client.put(
            "/api/settings/floppy",
            json={
                "url": "http://stored-floppy:8000",
                "api_key": "stored-token",
                "timeout_seconds": 8,
                "verify_tls": True,
            },
        )

        os.environ["BGC_FLOPPY_URL"] = "http://env-floppy:9000"
        os.environ["BGC_FLOPPY_API_KEY"] = "env-token"
        try:
            response = client.get("/api/settings/floppy")
        finally:
            clear_floppy_env()

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "http://env-floppy:9000"
    assert body["api_key_configured"] is True
    assert body["url_source"] == "environment"
    assert body["api_key_source"] == "environment"
    assert body["overrides"]["url"] is True
    assert body["overrides"]["api_key"] is True
    assert "env-token" not in response.text
    assert "stored-token" not in response.text


def test_floppy_settings_validate_url_and_timeout(tmp_path: Path) -> None:
    clear_floppy_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        bad_url = client.put(
            "/api/settings/floppy",
            json={"url": "floppy:8000", "timeout_seconds": 8, "verify_tls": True},
        )
        bad_timeout = client.put(
            "/api/settings/floppy",
            json={"url": "", "timeout_seconds": 120, "verify_tls": True},
        )

    assert bad_url.status_code == 422
    assert bad_timeout.status_code == 422
