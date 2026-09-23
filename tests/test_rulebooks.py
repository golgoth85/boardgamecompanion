from __future__ import annotations

from collections.abc import Iterable

import pytest

from boardgamecompanion.rulebooks import (
    SOURCE_CONFIDENCE,
    ResolvedRulebookCandidate,
    RulebookCandidate,
    RulebookQuery,
    RulebookResolution,
    RulebookResolver,
    RulebookSource,
)


class StaticProvider:
    def __init__(
        self,
        name: str,
        candidates: Iterable[RulebookCandidate],
    ):
        self.name = name
        self._candidates = tuple(candidates)

    def discover(self, query: RulebookQuery):
        del query
        yield from self._candidates


class BrokenProvider:
    name = "broken"

    def discover(self, query: RulebookQuery):
        del query
        raise RuntimeError("provider unavailable")


class PartialProvider:
    name = "partial"

    def __init__(self, candidate: RulebookCandidate):
        self.candidate = candidate

    def discover(self, query: RulebookQuery):
        del query
        yield self.candidate
        raise RuntimeError("failed after first result")


def candidate(
    *,
    provider: str,
    source: RulebookSource,
    url: str,
    language: str = "it",
    official: bool | None = None,
    confidence: int | None = None,
    bgg_id: int | None = 42,
    game_title: str | None = "Example Game",
    year: int | None = 2024,
) -> RulebookCandidate:
    if official is None:
        official = source in {
            RulebookSource.OFFICIAL_PUBLISHER,
            RulebookSource.OFFICIAL_LOCALIZER,
            RulebookSource.OFFICIAL_MIRROR,
        }
    return RulebookCandidate(
        provider=provider,
        source_kind=source,
        url=url,
        language=language,
        official=official,
        confidence=confidence,
        bgg_id=bgg_id,
        game_title=game_title,
        year=year,
    )


def query() -> RulebookQuery:
    return RulebookQuery(
        bgg_id=42,
        title="Example Game",
        original_title="Example Game Original",
        year=2024,
        item_type="base",
        publishers=("Example Publisher",),
    )


def test_candidate_normalizes_identity_language_url_and_default_confidence():
    item = candidate(
        provider="  publisher-example  ",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="HTTPS://Example.COM:443/rules.pdf#page=2",
        language="IT_it",
    )

    assert item.provider == "publisher-example"
    assert item.url == "https://example.com/rules.pdf"
    assert item.language == "it-it"
    assert item.document_type == "rulebook"
    assert item.official is True
    assert item.confidence == SOURCE_CONFIDENCE[RulebookSource.OFFICIAL_PUBLISHER]


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///tmp/rules.pdf",
        "ftp://example.com/rules.pdf",
        "https://user:secret@example.com/rules.pdf",
        "https:///rules.pdf",
    ],
)
def test_candidate_rejects_non_web_or_credentialed_urls(url):
    with pytest.raises(ValueError):
        candidate(
            provider="unsafe",
            source=RulebookSource.COMMUNITY,
            url=url,
            official=False,
        )


@pytest.mark.parametrize(
    ("source", "official"),
    [
        (RulebookSource.OFFICIAL_PUBLISHER, False),
        (RulebookSource.OFFICIAL_LOCALIZER, False),
        (RulebookSource.OFFICIAL_MIRROR, False),
        (RulebookSource.COMMUNITY, True),
        (RulebookSource.GENERIC, True),
    ],
)
def test_candidate_requires_source_and_official_flag_to_agree(source, official):
    with pytest.raises(ValueError):
        candidate(
            provider="bad-classification",
            source=source,
            url="https://example.com/rules.pdf",
            official=official,
        )


def test_candidate_cannot_raise_confidence_above_source_trust_ceiling():
    with pytest.raises(ValueError, match="community.*between 0 and 70"):
        candidate(
            provider="community",
            source=RulebookSource.COMMUNITY,
            url="https://community.example/rules.pdf",
            official=False,
            confidence=100,
        )


def test_resolver_prefers_language_then_source_with_equal_confidence():
    publisher_en = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules-en.pdf",
        language="en",
        bgg_id=None,
    )
    localizer_it = candidate(
        provider="localizer",
        source=RulebookSource.OFFICIAL_LOCALIZER,
        url="https://localizer.example/regolamento.pdf",
        language="it-IT",
        bgg_id=None,
    )
    publisher_it = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/regolamento.pdf",
        language="it",
        bgg_id=None,
    )

    result = RulebookResolver(
        [
            StaticProvider("publisher-en", [publisher_en]),
            StaticProvider("localizer-it", [localizer_it]),
            StaticProvider("publisher-it", [publisher_it]),
        ]
    ).resolve(query())

    assert [item.candidate for item in result.candidates] == [
        publisher_it,
        localizer_it,
        publisher_en,
    ]


def test_resolver_honors_exact_regional_language_preferences():
    gb = candidate(
        provider="publisher-gb",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules-gb.pdf",
        language="en-GB",
        bgg_id=None,
    )
    us = candidate(
        provider="publisher-us",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules-us.pdf",
        language="en-US",
        bgg_id=None,
    )
    generic_en = candidate(
        provider="publisher-en",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules-en.pdf",
        language="en",
        bgg_id=None,
    )

    result = RulebookResolver(
        [StaticProvider("publisher", [us, generic_en, gb])]
    ).resolve(
        query(),
        preferred_languages=("en-gb", "en-us"),
    )

    assert [item.candidate.language for item in result.candidates] == [
        "en-gb",
        "en-us",
        "en",
    ]


def test_primary_language_order_still_beats_later_exact_language():
    italian_variant = candidate(
        provider="localizer-it",
        source=RulebookSource.OFFICIAL_LOCALIZER,
        url="https://localizer.example/rules-it.pdf",
        language="it-CH",
        bgg_id=None,
    )
    english = candidate(
        provider="publisher-en",
        source=RulebookSource.OFFICIAL_LOCALIZER,
        url="https://localizer.example/rules-en.pdf",
        language="en",
        bgg_id=None,
    )

    result = RulebookResolver(
        [StaticProvider("localizer", [english, italian_variant])]
    ).resolve(
        query(),
        preferred_languages=("it-it", "en"),
    )

    assert result.best is not None
    assert result.best.candidate.language == "it-ch"


def test_resolver_source_confidence_dominates_lower_tier_exact_match():
    official = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules.pdf",
        language="en",
        bgg_id=None,
        game_title=None,
        year=None,
    )
    community = candidate(
        provider="community",
        source=RulebookSource.COMMUNITY,
        url="https://community.example/rules.pdf",
        language="it",
        official=False,
        bgg_id=42,
    )

    result = RulebookResolver(
        [
            StaticProvider("publisher", [official]),
            StaticProvider("community", [community]),
        ]
    ).resolve(query())

    assert result.best is not None
    assert result.best.candidate is official


def test_resolver_rejects_conflicting_bgg_id_and_non_rulebook_types():
    wrong_game = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/wrong.pdf",
        bgg_id=99,
    )
    faq = RulebookCandidate(
        provider="publisher",
        source_kind=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/faq.pdf",
        language="it",
        document_type="faq",
        official=True,
        bgg_id=42,
    )
    rulebook = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules.pdf",
    )

    result = RulebookResolver(
        [StaticProvider("publisher", [wrong_game, faq, rulebook])]
    ).resolve(query())

    assert [item.candidate for item in result.candidates] == [rulebook]


def test_resolver_can_include_additional_document_types_explicitly():
    faq = RulebookCandidate(
        provider="publisher",
        source_kind=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/faq.pdf",
        language="it",
        document_type="faq",
        official=True,
        bgg_id=42,
    )

    result = RulebookResolver([StaticProvider("publisher", [faq])]).resolve(
        query(),
        document_types=("rulebook", "faq"),
    )

    assert [item.candidate for item in result.candidates] == [faq]


def test_resolver_deduplicates_canonical_url_and_keeps_higher_ranked_result():
    generic = candidate(
        provider="search",
        source=RulebookSource.GENERIC,
        url="https://EXAMPLE.com:443/rules.pdf#download",
        official=False,
        confidence=40,
    )
    mirror = candidate(
        provider="official-mirror",
        source=RulebookSource.OFFICIAL_MIRROR,
        url="https://example.com/rules.pdf",
        official=True,
        confidence=95,
    )

    result = RulebookResolver(
        [
            StaticProvider("search", [generic]),
            StaticProvider("mirror", [mirror]),
        ]
    ).resolve(query())

    assert len(result.candidates) == 1
    assert result.candidates[0].candidate is mirror


def test_provider_failure_isolated_and_partial_results_are_retained():
    partial_item = candidate(
        provider="partial",
        source=RulebookSource.COMMUNITY,
        url="https://community.example/rules.pdf",
        official=False,
    )
    healthy_item = candidate(
        provider="healthy",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules.pdf",
    )

    result = RulebookResolver(
        [
            BrokenProvider(),
            PartialProvider(partial_item),
            StaticProvider("healthy", [healthy_item]),
        ]
    ).resolve(query())

    assert {item.candidate.url for item in result.candidates} == {
        partial_item.url,
        healthy_item.url,
    }
    assert [(failure.provider, failure.error_type) for failure in result.failures] == [
        ("broken", "RuntimeError"),
        ("partial", "RuntimeError"),
    ]


def test_resolution_exposes_explainable_score_reasons():
    item = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules.pdf",
        language="it",
    )

    result = RulebookResolver([StaticProvider("publisher", [item])]).resolve(query())

    assert isinstance(result, RulebookResolution)
    assert isinstance(result.best, ResolvedRulebookCandidate)
    assert result.best is not None
    assert "bgg_id:exact" in result.best.reasons
    assert "language:it" in result.best.reasons
    assert "title:exact" in result.best.reasons
    assert "year:exact" in result.best.reasons
    assert result.best.score > 0


@pytest.mark.parametrize("bad_id", [42.9, True, False, "42.9"])
def test_bgg_identity_rejects_non_integral_values(bad_id):
    with pytest.raises(ValueError):
        RulebookQuery(bgg_id=bad_id, title="Example Game")

    with pytest.raises(ValueError):
        candidate(
            provider="publisher",
            source=RulebookSource.OFFICIAL_PUBLISHER,
            url="https://publisher.example/rules.pdf",
            bgg_id=bad_id,
        )


def test_bgg_identity_accepts_numeric_strings_without_truncation():
    normalized_query = RulebookQuery(bgg_id="42", title="Example Game")
    normalized_candidate = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules.pdf",
        bgg_id="42",
    )

    assert normalized_query.bgg_id == 42
    assert normalized_candidate.bgg_id == 42


@pytest.mark.parametrize(
    "url",
    [
        "https://exa mple.com/rules.pdf",
        "https://-example.com/rules.pdf",
        "https://example-.com/rules.pdf",
        "https://example..com/rules.pdf",
        "https://example_.com/rules.pdf",
    ],
)
def test_candidate_rejects_malformed_hostnames(url):
    with pytest.raises(ValueError):
        candidate(
            provider="unsafe-host",
            source=RulebookSource.COMMUNITY,
            url=url,
            official=False,
        )


def test_candidate_normalizes_unicode_hostname_to_idna():
    item = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://MÜNICH.example/rules.pdf",
    )

    assert item.url == "https://xn--mnich-kva.example/rules.pdf"


def test_exact_bgg_identity_outranks_any_requested_language_position():
    exact_identity = candidate(
        provider="publisher-exact",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules-fr.pdf",
        language="fr",
        bgg_id=42,
    )
    preferred_language_without_identity = candidate(
        provider="publisher-it",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules-it.pdf",
        language="it",
        bgg_id=None,
    )

    result = RulebookResolver(
        [StaticProvider("publisher", [preferred_language_without_identity, exact_identity])]
    ).resolve(
        query(),
        preferred_languages=("it", "en", "de"),
    )

    assert result.best is not None
    assert result.best.candidate is exact_identity
    assert result.candidates[0].score > result.candidates[1].score


def test_equal_score_order_is_independent_of_provider_yield_order():
    alpha = candidate(
        provider="z-provider",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://alpha.example/rules.pdf",
        bgg_id=None,
    )
    beta = candidate(
        provider="a-provider",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://beta.example/rules.pdf",
        bgg_id=None,
    )

    forward = RulebookResolver([StaticProvider("provider", [beta, alpha])]).resolve(query())
    reverse = RulebookResolver([StaticProvider("provider", [alpha, beta])]).resolve(query())

    assert [item.candidate.url for item in forward.candidates] == [
        item.candidate.url for item in reverse.candidates
    ] == [alpha.url, beta.url]
    assert "tie_break:canonical_url-provider" in forward.candidates[0].reasons


def test_equal_score_dedup_is_independent_of_provider_order():
    first = candidate(
        provider="z-provider",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://example.com/rules.pdf",
        bgg_id=None,
    )
    second = candidate(
        provider="a-provider",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://EXAMPLE.com:443/rules.pdf#fragment",
        bgg_id=None,
    )

    forward = RulebookResolver(
        [StaticProvider("one", [first]), StaticProvider("two", [second])]
    ).resolve(query())
    reverse = RulebookResolver(
        [StaticProvider("two", [second]), StaticProvider("one", [first])]
    ).resolve(query())

    assert forward.best is not None
    assert reverse.best is not None
    assert forward.best.candidate.provider == reverse.best.candidate.provider == "a-provider"
    assert "dedup_tie:deterministic" in forward.best.reasons


def test_candidate_accepts_single_trailing_root_dot_but_rejects_empty_dns_labels():
    valid = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://Example.COM./rules.pdf",
    )
    assert valid.url == "https://example.com/rules.pdf"

    for url in (
        "https://example.com../rules.pdf",
        "https://example.com.../rules.pdf",
    ):
        with pytest.raises(ValueError):
            candidate(
                provider="publisher",
                source=RulebookSource.OFFICIAL_PUBLISHER,
                url=url,
            )


def test_candidate_uses_modern_idna_without_changing_sharp_s_domain_identity():
    item = candidate(
        provider="publisher",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://faß.de/rules.pdf",
    )

    assert item.url == "https://xn--fa-hia.de/rules.pdf"


def test_equal_score_dedup_uses_metadata_as_final_deterministic_discriminant():
    one = RulebookCandidate(
        provider="same-provider",
        source_kind=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://example.com/rules.pdf",
        language="it",
        official=True,
        bgg_id=None,
        game_title="Example Game",
        year=2024,
        metadata={"origin": "one"},
    )
    two = RulebookCandidate(
        provider="same-provider",
        source_kind=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://EXAMPLE.com:443/rules.pdf#page=1",
        language="it",
        official=True,
        bgg_id=None,
        game_title="Example Game",
        year=2024,
        metadata={"origin": "two"},
    )

    forward = RulebookResolver(
        [StaticProvider("one", [one]), StaticProvider("two", [two])]
    ).resolve(query())
    reverse = RulebookResolver(
        [StaticProvider("two", [two]), StaticProvider("one", [one])]
    ).resolve(query())

    assert forward.best is not None
    assert reverse.best is not None
    assert forward.best.candidate.metadata == reverse.best.candidate.metadata
    assert forward.best.candidate.metadata == {"origin": "one"}
    assert "dedup_tie:deterministic" in forward.best.reasons
