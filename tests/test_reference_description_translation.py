from __future__ import annotations

from pathlib import Path

import pytest

from boardgamecompanion.bgg_reference import BggReferenceCatalog, BggReferenceImporter
from boardgamecompanion.database import Database
from boardgamecompanion.description_translation import (
    DescriptionTranslationError,
    ReferenceDescriptionTranslationService,
)

HEADER = (
    "id,name,yearpublished,rank,bayesaverage,average,usersrated,is_expansion,"
    "abstracts_rank,cgs_rank,childrensgames_rank,familygames_rank,partygames_rank,"
    "strategygames_rank,thematic_rank,wargames_rank\n"
)
DUMP = (HEADER + '224517,"Brass: Birmingham",2018,1,8.39,8.56,60686,0,,,,,,1,,\n').encode("utf-8")
DESCRIPTION = "An economic game about <i>canal</i> and rail.<br/>Build industries."


@pytest.fixture()
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "catalog.sqlite3")
    database.initialize()
    BggReferenceImporter(database).import_bytes(DUMP, "boardgames_ranks.csv")
    _set_description(database, DESCRIPTION)
    return database


def _set_description(database: Database, description: str | None) -> None:
    with database.transaction() as connection:
        connection.execute(
            "UPDATE bgg_reference_games SET description=? WHERE bgg_id=?",
            (description, 224517),
        )


def _fake_translate(calls: list[str]):
    def translate(self, source_text: str) -> tuple[str, str, str]:
        calls.append(source_text)
        return "Un gioco economico sui canali.", "gemini", "test-model"

    return translate


def test_translation_is_cached_per_source_and_hidden_from_detail(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        ReferenceDescriptionTranslationService,
        "_translate_with_providers",
        _fake_translate(calls),
    )
    service = ReferenceDescriptionTranslationService(database)

    assert service.status(224517)["status"] == "pending"
    first = service.translate(224517)
    second = service.translate(224517)

    assert len(calls) == 1
    assert first["translation"]["translated_text"] == "Un gioco economico sui canali."
    assert second["translation"]["provider"] == "gemini"
    assert service.status(224517)["status"] == "ready"
    detail = BggReferenceCatalog(database).detail(224517)
    assert detail is not None
    assert "description_it" not in detail["details"]


def test_changed_source_invalidates_translation(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        ReferenceDescriptionTranslationService,
        "_translate_with_providers",
        _fake_translate(calls),
    )
    service = ReferenceDescriptionTranslationService(database)
    service.translate(224517)

    _set_description(database, "A different description.")

    assert service.get_cached(224517) is None
    assert service.status(224517)["status"] == "pending"


def test_api_refresh_keeps_stored_translation(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ReferenceDescriptionTranslationService,
        "_translate_with_providers",
        _fake_translate([]),
    )
    service = ReferenceDescriptionTranslationService(database)
    service.translate(224517)

    BggReferenceCatalog(database).store_api_detail(
        224517,
        {"description": DESCRIPTION, "min_players": 2},
        "<items/>",
    )

    assert service.get_cached(224517) is not None


def test_missing_source_and_unknown_title_are_reported(database: Database) -> None:
    service = ReferenceDescriptionTranslationService(database)
    _set_description(database, None)

    assert service.status(224517)["status"] == "missing_source"
    with pytest.raises(DescriptionTranslationError, match="No BGG description"):
        service.translate(224517)
    with pytest.raises(DescriptionTranslationError, match="not found"):
        service.status(999999)
