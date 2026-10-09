from boardgamecompanion.rulebook_availability import get_rulebook_availability


def test_awaken_expansion_is_marked_as_no_specific_official_pdf() -> None:
    item = get_rulebook_availability(267408)
    assert item is not None
    assert item["status"] == "official_catalog_no_specific_pdf"
    assert item["confidence"] == "high"
    assert item["action"] == "retry_official"
    assert item["external_url"] is None


def test_component_driven_tmb_expansion_does_not_claim_missing_manual() -> None:
    item = get_rulebook_availability(349916)
    assert item is not None
    assert item["status"] == "rules_in_components"
    assert item["confidence"] == "high"
    assert "manuale autonomo" in str(item["label"]).lower()


def test_physical_only_ffg_rule_sheet_is_explicit() -> None:
    item = get_rulebook_availability(156053)
    assert item is not None
    assert item["status"] == "physical_rule_sheet"
    assert item["action"] == "retry_official"


def test_external_exact_manual_is_never_unattended() -> None:
    item = get_rulebook_availability(334888)
    assert item is not None
    assert item["status"] == "external_exact_manual"
    assert item["action"] == "open_external"
    assert str(item["external_url"]).startswith("https://")


def test_unresearched_game_has_no_curated_classification() -> None:
    assert get_rulebook_availability(350624) is None
