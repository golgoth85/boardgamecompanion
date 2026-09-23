from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable
from itertools import permutations

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


@pytest.mark.parametrize(
    ("source", "official"),
    [
        (RulebookSource.OFFICIAL_PUBLISHER, True),
        (RulebookSource.OFFICIAL_LOCALIZER, True),
        (RulebookSource.OFFICIAL_MIRROR, True),
        (RulebookSource.COMMUNITY, False),
        (RulebookSource.GENERIC, False),
    ],
)
def test_candidate_accepts_exact_python_bool_for_every_source(source, official):
    item = RulebookCandidate(
        provider="typed-official",
        source_kind=source,
        url="https://example.com/rules.pdf",
        official=official,
    )
    assert item.official is official


@pytest.mark.parametrize("source", list(RulebookSource))
@pytest.mark.parametrize(
    "official",
    ["true", "false", "0", "1", 0, 1, None],
)
def test_candidate_rejects_non_boolean_official_values_for_every_source(
    source,
    official,
):
    with pytest.raises(ValueError, match="official must be a Python bool"):
        RulebookCandidate(
            provider="typed-official",
            source_kind=source,
            url="https://example.com/rules.pdf",
            official=official,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/rules.pdf",
        "https://LOCALHOST./rules.pdf",
        "https://rules.localhost/rules.pdf",
        "https://127.0.0.1/rules.pdf",
        "https://127.0.0.1./rules.pdf",
        "https://[::1]/rules.pdf",
        "https://[::ffff:127.0.0.1]/rules.pdf",
        "https://[::ffff:8.8.8.8]/rules.pdf",
        "https://169.254.169.254/rules.pdf",
        "https://10.0.0.1/rules.pdf",
        "https://224.0.0.1/rules.pdf",
        "https://0.0.0.0/rules.pdf",
        "https://100.64.0.1/rules.pdf",
        "https://240.0.0.1/rules.pdf",
        "https://１２７。０。０。１/rules.pdf",
    ],
)
def test_candidate_rejects_non_public_literal_hosts_and_localhost(url):
    with pytest.raises(ValueError):
        candidate(
            provider="unsafe-host",
            source=RulebookSource.COMMUNITY,
            url=url,
            official=False,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://2130706433/rules.pdf",
        "https://127.1/rules.pdf",
        "https://0x7f000001/rules.pdf",
        "https://0177.0.0.1/rules.pdf",
    ],
)
def test_candidate_rejects_ambiguous_legacy_ipv4_forms(url):
    with pytest.raises(ValueError, match="ambiguous IPv4"):
        candidate(
            provider="legacy-ip",
            source=RulebookSource.COMMUNITY,
            url=url,
            official=False,
        )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://8.8.8.8/rules.pdf", "https://8.8.8.8/rules.pdf"),
        (
            "https://[2606:4700:4700::1111]/rules.pdf",
            "https://[2606:4700:4700::1111]/rules.pdf",
        ),
    ],
)
def test_candidate_allows_global_literal_ip_addresses(url, expected):
    item = candidate(
        provider="public-ip",
        source=RulebookSource.COMMUNITY,
        url=url,
        official=False,
    )
    assert item.url == expected


@pytest.mark.parametrize(
    "metadata",
    [
        {1: "x"},
        {"nested": {1: "x", "a": "y"}},
        {"value": {1, 2}},
        {"value": frozenset({1, 2})},
        {"value": object()},
        {"value": b"bytes"},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": float("-inf")},
    ],
    ids=[
        "non-string-key",
        "nested-non-string-key",
        "set",
        "frozenset",
        "custom-object",
        "bytes",
        "nan",
        "positive-infinity",
        "negative-infinity",
    ],
)
def test_candidate_rejects_noncanonical_metadata(metadata):
    with pytest.raises(ValueError):
        RulebookCandidate(
            provider="metadata",
            source_kind=RulebookSource.COMMUNITY,
            url="https://example.com/rules.pdf",
            official=False,
            metadata=metadata,
        )


def test_candidate_rejects_recursive_metadata_containers():
    recursive = []
    recursive.append(recursive)

    with pytest.raises(ValueError, match="recursive containers"):
        RulebookCandidate(
            provider="metadata",
            source_kind=RulebookSource.COMMUNITY,
            url="https://example.com/rules.pdf",
            official=False,
            metadata={"recursive": recursive},
        )


def test_candidate_metadata_is_canonical_deeply_immutable_snapshot():
    source_metadata = {
        "z": 3,
        "nested": {
            "items": [1, 2, {"enabled": True}],
            "label": "rules",
        },
        "a": None,
    }
    item = RulebookCandidate(
        provider="metadata",
        source_kind=RulebookSource.COMMUNITY,
        url="https://example.com/rules.pdf",
        official=False,
        metadata=source_metadata,
    )
    tie_key_before = RulebookResolver._deterministic_tie_key(item)

    source_metadata["nested"]["items"].append(99)
    source_metadata["nested"]["label"] = "changed"
    source_metadata["later"] = "mutation"

    assert item.metadata["nested"]["items"] == (1, 2, {"enabled": True})
    assert item.metadata["nested"]["label"] == "rules"
    assert "later" not in item.metadata
    assert RulebookResolver._deterministic_tie_key(item) == tie_key_before

    with pytest.raises(TypeError):
        item.metadata["new"] = "value"
    with pytest.raises(TypeError):
        item.metadata["nested"]["new"] = "value"


def test_metadata_tie_key_ignores_mapping_insertion_order_recursively():
    first_metadata = {
        "b": 2,
        "nested": {"z": 3, "a": [1, 2, 3]},
        "a": 1,
    }
    second_metadata = {
        "a": 1,
        "nested": {"a": [1, 2, 3], "z": 3},
        "b": 2,
    }
    first = RulebookCandidate(
        provider="same",
        source_kind=RulebookSource.COMMUNITY,
        url="https://example.com/rules.pdf",
        official=False,
        metadata=first_metadata,
    )
    second = RulebookCandidate(
        provider="same",
        source_kind=RulebookSource.COMMUNITY,
        url="https://example.com/rules.pdf",
        official=False,
        metadata=second_metadata,
    )

    assert RulebookResolver._deterministic_tie_key(
        first
    ) == RulebookResolver._deterministic_tie_key(second)


def test_metadata_accepts_supported_json_like_sequences_and_finite_numbers():
    item = RulebookCandidate(
        provider="metadata",
        source_kind=RulebookSource.COMMUNITY,
        url="https://example.com/rules.pdf",
        official=False,
        metadata={
            "list": [None, True, 3, 1.25, "x"],
            "tuple": ("a", {"nested": [False, 2]}),
        },
    )

    assert item.metadata["list"] == (None, True, 3, 1.25, "x")
    assert item.metadata["tuple"] == ("a", {"nested": (False, 2)})


def test_metadata_tie_key_is_process_independent_across_hash_seeds():
    script = """
from boardgamecompanion.rulebooks import RulebookCandidate, RulebookResolver, RulebookSource
pairs = {("gamma", 3), ("alpha", 1), ("beta", 2)}
nested_pairs = {("zeta", "z"), ("eta", "e")}
candidate = RulebookCandidate(
    provider="same",
    source_kind=RulebookSource.COMMUNITY,
    url="https://example.com/rules.pdf",
    official=False,
    metadata={
        key: value for key, value in pairs
    } | {
        "nested": {key: value for key, value in nested_pairs}
    },
)
print(RulebookResolver._deterministic_tie_key(candidate)[-1])
"""
    outputs = []
    for seed in ("1", "2", "8675309"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-c", script],
                env=env,
                text=True,
            ).strip()
        )
    assert len(set(outputs)) == 1


def test_invalid_metadata_provider_failure_does_not_drop_healthy_result():
    class InvalidMetadataProvider:
        name = "invalid-metadata"

        def discover(self, requested_query):
            del requested_query
            yield RulebookCandidate(
                provider=self.name,
                source_kind=RulebookSource.COMMUNITY,
                url="https://bad.example/rules.pdf",
                official=False,
                metadata={"nested": {1: "invalid"}},
            )

    healthy = candidate(
        provider="healthy",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://publisher.example/rules.pdf",
    )
    result = RulebookResolver(
        [
            InvalidMetadataProvider(),
            StaticProvider("healthy", [healthy]),
        ]
    ).resolve(query())

    assert [item.candidate for item in result.candidates] == [healthy]
    assert [(failure.provider, failure.error_type) for failure in result.failures] == [
        ("invalid-metadata", "ValueError"),
    ]


@pytest.mark.parametrize(
    ("left_url", "right_url"),
    [
        (
            "https://example.com/a/../rules.pdf",
            "https://example.com/rules.pdf",
        ),
        (
            "https://example.com/%7Erules.pdf",
            "https://example.com/~rules.pdf",
        ),
        (
            "https://example.com/%72ules.pdf",
            "https://example.com/rules.pdf",
        ),
        (
            "https://example.com/folder%2frules.pdf",
            "https://example.com/folder%2Frules.pdf",
        ),
    ],
)
def test_rfc_equivalent_url_paths_deduplicate(left_url, right_url):
    left = candidate(
        provider="left",
        source=RulebookSource.COMMUNITY,
        url=left_url,
        official=False,
        bgg_id=None,
    )
    right = candidate(
        provider="right",
        source=RulebookSource.COMMUNITY,
        url=right_url,
        official=False,
        bgg_id=None,
    )
    result = RulebookResolver([StaticProvider("provider", [left, right])]).resolve(
        query()
    )
    assert len(result.candidates) == 1


@pytest.mark.parametrize(
    ("left_url", "right_url"),
    [
        (
            "https://example.com/folder%2Frules.pdf",
            "https://example.com/folder/rules.pdf",
        ),
        (
            "https://example.com/Rules.pdf",
            "https://example.com/rules.pdf",
        ),
        (
            "https://example.com/rules.pdf?token=%7E",
            "https://example.com/rules.pdf?token=~",
        ),
        (
            "https://example.com/rules.pdf?a=1&b=2",
            "https://example.com/rules.pdf?b=2&a=1",
        ),
    ],
)
def test_semantically_distinct_or_conservatively_preserved_urls_do_not_deduplicate(
    left_url,
    right_url,
):
    left = candidate(
        provider="left",
        source=RulebookSource.COMMUNITY,
        url=left_url,
        official=False,
        bgg_id=None,
    )
    right = candidate(
        provider="right",
        source=RulebookSource.COMMUNITY,
        url=right_url,
        official=False,
        bgg_id=None,
    )
    result = RulebookResolver([StaticProvider("provider", [left, right])]).resolve(
        query()
    )
    assert len(result.candidates) == 2


def test_candidate_rejects_invalid_path_percent_encoding():
    with pytest.raises(ValueError, match="invalid percent-encoding"):
        candidate(
            provider="bad-percent",
            source=RulebookSource.COMMUNITY,
            url="https://example.com/%ZZ/rules.pdf",
            official=False,
        )


def test_resolution_is_fully_order_independent_for_three_equal_score_duplicates():
    duplicates = [
        candidate(
            provider="z-provider",
            source=RulebookSource.OFFICIAL_PUBLISHER,
            url="https://example.com/a/../rules.pdf",
            bgg_id=None,
        ),
        candidate(
            provider="a-provider",
            source=RulebookSource.OFFICIAL_PUBLISHER,
            url="https://example.com/rules.pdf",
            bgg_id=None,
        ),
        candidate(
            provider="m-provider",
            source=RulebookSource.OFFICIAL_PUBLISHER,
            url="https://example.com/%72ules.pdf",
            bgg_id=None,
        ),
    ]
    other = candidate(
        provider="other",
        source=RulebookSource.OFFICIAL_PUBLISHER,
        url="https://beta.example/rules.pdf",
        bgg_id=None,
    )
    candidates = (*duplicates, other)

    baseline = None
    for ordering in permutations(candidates):
        result = RulebookResolver(
            [StaticProvider("permuted", ordering)]
        ).resolve(query())
        if baseline is None:
            baseline = result
        else:
            assert result == baseline

    assert baseline is not None
    assert len(baseline.candidates) == 2
    deduplicated = next(
        item
        for item in baseline.candidates
        if item.candidate.url.startswith("https://example.com/")
    )
    assert deduplicated.reasons.count("dedup_tie:deterministic") == 1
    assert all(
        item.reasons.count("tie_break:canonical_url-provider") == 1
        for item in baseline.candidates
    )
