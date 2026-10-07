from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from boardgamecompanion.app_settings import AppSettingsStore, activate_embedding_provider
from boardgamecompanion.database import Database
from boardgamecompanion.main import app
from boardgamecompanion.settings import settings


def configure_paths(tmp_path: Path) -> None:
    settings.config_dir = tmp_path / "config"
    settings.import_dir = tmp_path / "import"
    settings.manuals_dir = tmp_path / "manuals"


def clear_bgg_env() -> None:
    os.environ.pop("BGC_BGG_APPLICATION_TOKEN", None)
    os.environ.pop("BGC_BGG_USERNAME", None)


def clear_youtube_env() -> None:
    os.environ.pop("BGC_YOUTUBE_API_KEY", None)


def clear_apify_env() -> None:
    os.environ.pop("BGC_APIFY_TOKEN", None)
    settings.apify_token = None


def test_bgg_settings_persist_without_returning_secret(tmp_path: Path) -> None:
    clear_bgg_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        initial = client.get("/api/settings/bgg")
        assert initial.status_code == 200
        assert initial.json()["configured"] is False

        saved = client.put(
            "/api/settings/bgg",
            json={
                "application_token": "super-secret-bgg-token",
                "username": "test-user",
            },
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["configured"] is True
        assert body["application_token_source"] == "stored"
        assert body["stored_application_token_configured"] is True
        assert body["username"] == "test-user"
        assert body["collection_sync_configured"] is True
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
            json={"application_token": "stored-token", "username": "stored-user"},
        )

        os.environ["BGC_BGG_APPLICATION_TOKEN"] = "env-token"
        os.environ["BGC_BGG_USERNAME"] = "env-user"
        try:
            response = client.get("/api/settings/bgg")
        finally:
            clear_bgg_env()

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["application_token_source"] == "environment"
    assert body["overrides"]["application_token"] is True
    assert body["overrides"]["username"] is True
    assert body["username"] == "env-user"
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


def test_rag_settings_persist_priority_and_hide_secrets(tmp_path: Path) -> None:
    configure_paths(tmp_path)

    payload = {
        "embedding_provider_order": ["lmstudio", "ollama", "gemini"],
        "generation_provider_order": ["lmstudio", "gemini"],
        "ollama_url": "http://ollama.test:11434",
        "ollama_embedding_model": "nomic-embed-text",
        "ollama_generation_model": "qwen3:8b",
        "lmstudio_url": "http://lmstudio.test:1234",
        "lmstudio_api_key": "lmstudio-secret",
        "lmstudio_embedding_model": "text-embedding-qwen3-embedding-0.6b",
        "lmstudio_generation_model": "qwen3-14b",
        "lmstudio_generation_timeout_seconds": 300,
        "lmstudio_generation_max_tokens": 384,
        "lmstudio_generation_disable_thinking": True,
        "gemini_url": "https://generativelanguage.googleapis.com",
        "gemini_api_key": "gemini-secret",
        "gemini_embedding_model": "gemini-embedding-2",
        "gemini_generation_model": "gemini-3.5-flash-lite",
    }

    with TestClient(app) as client:
        saved = client.put("/api/settings/rag", json=payload)
        assert saved.status_code == 200
        body = saved.json()
        assert body["embedding_provider_order"] == ["lmstudio", "ollama", "gemini"]
        assert body["generation_provider_order"] == ["lmstudio", "gemini"]
        assert body["effective_embedding_provider"] == "lmstudio"
        assert body["effective_generation_provider"] == "lmstudio"
        assert body["automatic_fallback"] is False
        assert body["providers"]["lmstudio"]["generation_max_tokens"] == 384
        assert body["providers"]["lmstudio"]["generation_disable_thinking"] is True
        assert body["providers"]["lmstudio"]["api_key_configured"] is True
        assert body["providers"]["gemini"]["api_key_configured"] is True
        assert "lmstudio-secret" not in saved.text
        assert "gemini-secret" not in saved.text

        reloaded = client.get("/api/settings/rag")
        assert reloaded.status_code == 200
        assert reloaded.json() == body
        assert "lmstudio-secret" not in reloaded.text
        assert "gemini-secret" not in reloaded.text


def test_embedding_provider_promotion_preserves_recovery_chain(tmp_path: Path) -> None:
    configure_paths(tmp_path)
    database = Database(settings.database_path)
    database.initialize()
    store = AppSettingsStore(database)

    store.set(
        "rag_embedding_provider_order",
        '["gemini","lmstudio"]',
        sensitive=False,
    )
    promoted = activate_embedding_provider(database, "lmstudio")
    assert promoted.embedding_provider_order == ("lmstudio", "gemini")

    recovered = activate_embedding_provider(database, "gemini")
    assert recovered.embedding_provider_order == ("gemini", "lmstudio")



def test_rag_settings_reject_duplicate_provider_priority(tmp_path: Path) -> None:
    configure_paths(tmp_path)

    with TestClient(app) as client:
        response = client.put(
            "/api/settings/rag",
            json={
                "embedding_provider_order": ["lmstudio", "lmstudio"],
                "generation_provider_order": ["lmstudio"],
            },
        )

    assert response.status_code == 400
    assert "duplicates" in response.json()["detail"]


def test_youtube_settings_persist_without_returning_secret(tmp_path: Path) -> None:
    clear_youtube_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        initial = client.get("/api/settings/youtube")
        assert initial.status_code == 200
        assert initial.json()["configured"] is False

        saved = client.put(
            "/api/settings/youtube",
            json={"api_key": "youtube-secret-key"},
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["configured"] is True
        assert body["api_key_source"] == "stored"
        assert body["stored_api_key_configured"] is True
        assert "youtube-secret-key" not in saved.text
        assert "api_key" not in body

        reloaded = client.get("/api/settings/youtube")
        assert reloaded.status_code == 200
        assert reloaded.json() == body
        assert "youtube-secret-key" not in reloaded.text

        cleared = client.put(
            "/api/settings/youtube",
            json={"api_key": None, "clear_api_key": True},
        )
        assert cleared.status_code == 200
        assert cleared.json()["configured"] is False


def test_youtube_environment_key_overrides_stored_value(tmp_path: Path) -> None:
    clear_youtube_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        stored = client.put(
            "/api/settings/youtube",
            json={"api_key": "stored-youtube-key"},
        )
        assert stored.status_code == 200

        os.environ["BGC_YOUTUBE_API_KEY"] = "env-youtube-key"
        try:
            response = client.get("/api/settings/youtube")
        finally:
            clear_youtube_env()

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["api_key_source"] == "environment"
    assert body["overrides"]["api_key"] is True
    assert body["stored_api_key_configured"] is True
    assert "env-youtube-key" not in response.text
    assert "stored-youtube-key" not in response.text



def test_crowdfunding_settings_persist_without_returning_token(tmp_path: Path) -> None:
    clear_apify_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        initial = client.get("/api/settings/crowdfunding")
        assert initial.status_code == 200
        assert initial.json()["configured"] is False

        saved = client.put(
            "/api/settings/crowdfunding",
            json={"apify_token": "test-apify-token"},
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["configured"] is True
        assert body["apify_token_source"] == "stored"
        assert body["stored_apify_token_configured"] is True
        assert body["kickstarter"]["provider"] == "apify"
        assert "test-apify-token" not in saved.text
        assert "apify_token" not in body

        reloaded = client.get("/api/settings/crowdfunding")
        assert reloaded.status_code == 200
        assert reloaded.json() == body
        assert "test-apify-token" not in reloaded.text

        kept = client.put(
            "/api/settings/crowdfunding",
            json={"apify_token": None},
        )
        assert kept.status_code == 200
        assert kept.json()["configured"] is True

        cleared = client.put(
            "/api/settings/crowdfunding",
            json={"apify_token": None, "clear_apify_token": True},
        )
        assert cleared.status_code == 200
        assert cleared.json()["configured"] is False


def test_crowdfunding_environment_token_overrides_stored_value(tmp_path: Path) -> None:
    clear_apify_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        stored = client.put(
            "/api/settings/crowdfunding",
            json={"apify_token": "stored-test-token"},
        )
        assert stored.status_code == 200

        os.environ["BGC_APIFY_TOKEN"] = "runtime-test-token"
        try:
            response = client.get("/api/settings/crowdfunding")
        finally:
            clear_apify_env()

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["apify_token_source"] == "environment"
    assert body["overrides"]["apify_token"] is True
    assert body["stored_apify_token_configured"] is True
    assert "runtime-test-token" not in response.text
    assert "stored-test-token" not in response.text


def test_crowdfunding_verify_requires_configured_token(tmp_path: Path) -> None:
    clear_apify_env()
    configure_paths(tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/settings/crowdfunding/verify")

    assert response.status_code == 409
    assert "not configured" in response.json()["detail"]
