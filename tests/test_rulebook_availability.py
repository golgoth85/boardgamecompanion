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


def test_arena_boxes_are_classified_without_inventing_rulebooks() -> None:
    for bgg_id in (312509, 309701, 303730):
        item = get_rulebook_availability(bgg_id)
        assert item is not None
        assert item["status"] == "official_page_no_dedicated_pdf"
        assert item["confidence"] == "high"


def test_middara_bounties_are_physical_bounty_book_cases() -> None:
    for bgg_id in (284955, 284716):
        item = get_rulebook_availability(bgg_id)
        assert item is not None
        assert item["status"] == "physical_bounty_book"
        assert item["action"] == "retry_official"


def test_skyrim_expansions_use_cards_and_reference_material() -> None:
    for bgg_id in (350624, 350623):
        item = get_rulebook_availability(bgg_id)
        assert item is not None
        assert item["status"] == "rules_in_cards_reference"
        assert item["confidence"] == "high"


def test_unknown_game_has_no_curated_classification() -> None:
    assert get_rulebook_availability(999999999) is None
