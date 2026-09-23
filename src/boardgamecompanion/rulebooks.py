from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from numbers import Integral
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable
from urllib.parse import SplitResult, urlsplit, urlunsplit

from boardgamecompanion.documents import normalize_document_type, normalize_language


class RulebookSource(StrEnum):
    OFFICIAL_PUBLISHER = "official_publisher"
    OFFICIAL_LOCALIZER = "official_localizer"
    OFFICIAL_MIRROR = "official_mirror"
    COMMUNITY = "community"
    GENERIC = "generic"


SOURCE_CONFIDENCE: dict[RulebookSource, int] = {
    RulebookSource.OFFICIAL_PUBLISHER: 100,
    RulebookSource.OFFICIAL_LOCALIZER: 100,
    RulebookSource.OFFICIAL_MIRROR: 95,
    RulebookSource.COMMUNITY: 70,
    RulebookSource.GENERIC: 40,
}

SOURCE_PRIORITY: dict[RulebookSource, int] = {
    RulebookSource.OFFICIAL_PUBLISHER: 5,
    RulebookSource.OFFICIAL_LOCALIZER: 4,
    RulebookSource.OFFICIAL_MIRROR: 3,
    RulebookSource.COMMUNITY: 2,
    RulebookSource.GENERIC: 1,
}

OFFICIAL_SOURCES = {
    RulebookSource.OFFICIAL_PUBLISHER,
    RulebookSource.OFFICIAL_LOCALIZER,
    RulebookSource.OFFICIAL_MIRROR,
}


class RulebookProviderError(RuntimeError):
    pass


def _clean_optional(value: str | None, *, max_length: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(f"Value exceeds {max_length} characters")
    return text


_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _normalize_positive_identifier(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    if isinstance(value, Integral):
        normalized = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not re.fullmatch(r"[0-9]+", text):
            raise ValueError(f"{field_name} must be a positive integer")
        normalized = int(text)
    else:
        raise ValueError(f"{field_name} must be a positive integer")
    if normalized <= 0:
        raise ValueError(f"{field_name} must be positive")
    return normalized


def _normalize_http_hostname(hostname: str) -> str:
    host = hostname.rstrip(".")
    if not host or "%" in host:
        raise ValueError("Rulebook candidate URL contains an invalid hostname")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if ":" in host:
            raise ValueError("Rulebook candidate URL contains an invalid hostname")
        try:
            ascii_host = host.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError(
                "Rulebook candidate URL contains an invalid hostname"
            ) from exc
        if len(ascii_host) > 253:
            raise ValueError("Rulebook candidate URL contains an invalid hostname")
        labels = ascii_host.split(".")
        if any(not _HOST_LABEL_RE.fullmatch(label) for label in labels):
            raise ValueError("Rulebook candidate URL contains an invalid hostname")
        return ascii_host
    else:
        normalized = address.compressed.lower()
        return f"[{normalized}]" if address.version == 6 else normalized


def _canonical_http_url(value: str) -> str:
    text = str(value or "").strip()
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        raise ValueError("Rulebook candidate URL must not contain whitespace or controls")
    if "\\" in text:
        raise ValueError("Rulebook candidate URL must not contain backslashes")

    parts = urlsplit(text)
    if parts.scheme.lower() not in {"http", "https"}:
        raise ValueError("Rulebook candidate URL must use http or https")
    if not parts.hostname:
        raise ValueError("Rulebook candidate URL must include a hostname")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Rulebook candidate URL must not contain credentials")

    host = _normalize_http_hostname(parts.hostname)
    port = parts.port
    default_port = (parts.scheme.lower() == "http" and port == 80) or (
        parts.scheme.lower() == "https" and port == 443
    )
    netloc = host if port is None or default_port else f"{host}:{port}"
    normalized = SplitResult(
        scheme=parts.scheme.lower(),
        netloc=netloc,
        path=parts.path or "/",
        query=parts.query,
        fragment="",
    )
    return urlunsplit(normalized)


def _normalize_match_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text))


@dataclass(frozen=True, slots=True)
class RulebookQuery:
    bgg_id: int
    title: str
    original_title: str | None = None
    year: int | None = None
    item_type: str | None = None
    publishers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        bgg_id = _normalize_positive_identifier(self.bgg_id, field_name="bgg_id")
        title = str(self.title or "").strip()
        if not title:
            raise ValueError("title is required")
        object.__setattr__(self, "bgg_id", bgg_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "original_title", _clean_optional(self.original_title))
        if self.year is not None:
            object.__setattr__(self, "year", int(self.year))
        object.__setattr__(self, "item_type", _clean_optional(self.item_type, max_length=64))
        object.__setattr__(
            self,
            "publishers",
            tuple(
                text
                for value in self.publishers
                if (text := _clean_optional(value, max_length=500)) is not None
            ),
        )


@dataclass(frozen=True, slots=True)
class RulebookCandidate:
    provider: str
    source_kind: RulebookSource | str
    url: str
    language: str = "und"
    document_type: str = "rulebook"
    official: bool = False
    confidence: int | None = None
    title: str | None = None
    version_label: str | None = None
    edition: str | None = None
    bgg_id: int | None = None
    game_title: str | None = None
    year: int | None = None
    publisher: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        provider = str(self.provider or "").strip()
        if not provider:
            raise ValueError("provider is required")
        try:
            source_kind = RulebookSource(self.source_kind)
        except ValueError as exc:
            raise ValueError(f"Unsupported rulebook source kind: {self.source_kind}") from exc

        official = bool(self.official)
        if (source_kind in OFFICIAL_SOURCES) != official:
            expected = "official" if source_kind in OFFICIAL_SOURCES else "unofficial"
            raise ValueError(
                f"{source_kind.value} candidates must be marked {expected}"
            )

        source_confidence_ceiling = SOURCE_CONFIDENCE[source_kind]
        confidence = (
            source_confidence_ceiling
            if self.confidence is None
            else int(self.confidence)
        )
        if not 0 <= confidence <= source_confidence_ceiling:
            raise ValueError(
                f"confidence for {source_kind.value} must be between 0 "
                f"and {source_confidence_ceiling}"
            )

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "source_kind", source_kind)
        object.__setattr__(self, "url", _canonical_http_url(self.url))
        object.__setattr__(self, "language", normalize_language(self.language))
        object.__setattr__(
            self,
            "document_type",
            normalize_document_type(self.document_type),
        )
        object.__setattr__(self, "official", official)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "title", _clean_optional(self.title))
        object.__setattr__(self, "version_label", _clean_optional(self.version_label))
        object.__setattr__(self, "edition", _clean_optional(self.edition))
        object.__setattr__(self, "game_title", _clean_optional(self.game_title))
        object.__setattr__(self, "publisher", _clean_optional(self.publisher))
        if self.bgg_id is not None:
            object.__setattr__(
                self,
                "bgg_id",
                _normalize_positive_identifier(
                    self.bgg_id,
                    field_name="candidate bgg_id",
                ),
            )
        if self.year is not None:
            object.__setattr__(self, "year", int(self.year))
        object.__setattr__(self, "metadata", dict(self.metadata))


@runtime_checkable
class RulebookProvider(Protocol):
    name: str

    def discover(self, query: RulebookQuery) -> Iterable[RulebookCandidate]:
        ...


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    provider: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ResolvedRulebookCandidate:
    candidate: RulebookCandidate
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RulebookResolution:
    query: RulebookQuery
    candidates: tuple[ResolvedRulebookCandidate, ...]
    failures: tuple[ProviderFailure, ...]

    @property
    def best(self) -> ResolvedRulebookCandidate | None:
        return self.candidates[0] if self.candidates else None


class RulebookResolver:
    def __init__(self, providers: Iterable[RulebookProvider]):
        self.providers = tuple(providers)

    @staticmethod
    def _language_rank(language: str, preferred_languages: tuple[str, ...]) -> int:
        primary = language.split("-", 1)[0]
        primary_order = tuple(
            dict.fromkeys(
                preferred.split("-", 1)[0]
                for preferred in preferred_languages
            )
        )
        if primary not in primary_order:
            return 0

        group_index = primary_order.index(primary)
        same_primary = tuple(
            preferred
            for preferred in preferred_languages
            if preferred.split("-", 1)[0] == primary
        )
        group_stride = len(preferred_languages) + 1
        group_rank = (len(primary_order) - group_index) * group_stride
        if language in same_primary:
            exact_rank = len(same_primary) - same_primary.index(language)
        else:
            exact_rank = 0
        return group_rank + exact_rank

    @staticmethod
    def _candidate_score(
        query: RulebookQuery,
        candidate: RulebookCandidate,
        preferred_languages: tuple[str, ...],
    ) -> tuple[int, tuple[str, ...]]:
        reasons: list[str] = [
            f"confidence:{candidate.confidence}",
            f"source:{candidate.source_kind.value}",
        ]

        bgg_exact = candidate.bgg_id == query.bgg_id
        if bgg_exact:
            reasons.append("bgg_id:exact")

        language_rank = RulebookResolver._language_rank(
            candidate.language,
            preferred_languages,
        )
        if language_rank:
            reasons.append(f"language:{candidate.language}")
        max_language_rank = max(
            (
                RulebookResolver._language_rank(language, preferred_languages)
                for language in preferred_languages
            ),
            default=0,
        )

        query_titles = {
            value
            for value in (
                _normalize_match_text(query.title),
                _normalize_match_text(query.original_title),
            )
            if value
        }
        candidate_title = _normalize_match_text(candidate.game_title)
        title_exact = bool(candidate_title and candidate_title in query_titles)
        if title_exact:
            reasons.append("title:exact")

        year_exact = query.year is not None and candidate.year == query.year
        if year_exact:
            reasons.append("year:exact")

        # Mixed-radix encoding preserves the documented lexicographic precedence:
        # confidence > exact BGG identity > language > source > title > year.
        # The language radix is derived from this resolution request, so lower-order
        # fields cannot overtake exact identity even with many preferred languages.
        score = int(candidate.confidence)
        score = score * 2 + int(bgg_exact)
        score = score * (max_language_rank + 1) + language_rank
        score = score * (max(SOURCE_PRIORITY.values()) + 1) + SOURCE_PRIORITY[
            candidate.source_kind
        ]
        score = score * 2 + int(title_exact)
        score = score * 2 + int(year_exact)

        return score, tuple(reasons)

    @staticmethod
    def _deterministic_tie_key(candidate: RulebookCandidate) -> tuple[Any, ...]:
        return (
            candidate.url,
            candidate.provider.casefold(),
            candidate.provider,
            candidate.language,
            candidate.document_type,
            candidate.title or "",
            candidate.version_label or "",
            candidate.edition or "",
            candidate.game_title or "",
            candidate.publisher or "",
            candidate.bgg_id or 0,
            candidate.year or 0,
        )

    def resolve(
        self,
        query: RulebookQuery,
        *,
        preferred_languages: Iterable[str] = ("it", "en"),
        document_types: Iterable[str] = ("rulebook",),
    ) -> RulebookResolution:
        languages = tuple(
            dict.fromkeys(normalize_language(value) for value in preferred_languages)
        )
        allowed_types = {
            normalize_document_type(value)
            for value in document_types
        }

        failures: list[ProviderFailure] = []
        ranked: list[ResolvedRulebookCandidate] = []

        for provider in self.providers:
            provider_name = str(getattr(provider, "name", provider.__class__.__name__)).strip()
            try:
                for candidate in provider.discover(query):
                    if not isinstance(candidate, RulebookCandidate):
                        raise TypeError(
                            f"Provider yielded {type(candidate).__name__}, "
                            "expected RulebookCandidate"
                        )
                    if candidate.document_type not in allowed_types:
                        continue
                    if candidate.bgg_id is not None and candidate.bgg_id != query.bgg_id:
                        continue
                    score, reasons = self._candidate_score(
                        query,
                        candidate,
                        languages,
                    )
                    ranked.append(
                        ResolvedRulebookCandidate(
                            candidate=candidate,
                            score=score,
                            reasons=reasons,
                        )
                    )
            except Exception as exc:
                failures.append(
                    ProviderFailure(
                        provider=provider_name or provider.__class__.__name__,
                        error_type=exc.__class__.__name__,
                        message=str(exc),
                    )
                )

        best_by_url: dict[str, ResolvedRulebookCandidate] = {}
        for item in ranked:
            current = best_by_url.get(item.candidate.url)
            if current is None or item.score > current.score:
                best_by_url[item.candidate.url] = item
            elif item.score == current.score:
                chosen = min(
                    (current, item),
                    key=lambda value: self._deterministic_tie_key(value.candidate),
                )
                best_by_url[item.candidate.url] = ResolvedRulebookCandidate(
                    candidate=chosen.candidate,
                    score=chosen.score,
                    reasons=chosen.reasons + ("dedup_tie:deterministic",),
                )

        deduplicated = tuple(best_by_url.values())
        score_counts = {
            score: sum(1 for item in deduplicated if item.score == score)
            for score in {item.score for item in deduplicated}
        }
        ordered_items = sorted(
            deduplicated,
            key=lambda item: (
                -item.score,
                self._deterministic_tie_key(item.candidate),
            ),
        )
        ordered = tuple(
            item
            if score_counts[item.score] == 1
            else ResolvedRulebookCandidate(
                candidate=item.candidate,
                score=item.score,
                reasons=item.reasons + ("tie_break:canonical_url-provider",),
            )
            for item in ordered_items
        )
        return RulebookResolution(
            query=query,
            candidates=ordered,
            failures=tuple(failures),
        )
