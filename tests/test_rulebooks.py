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
