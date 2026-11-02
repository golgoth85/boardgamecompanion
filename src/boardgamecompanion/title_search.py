from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Iterable


def normalize_title_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = "".join(
        char if char.isalnum() else " "
        for char in text.casefold()
    )
    return re.sub(r"\s+", " ", text).strip()


def metadata_dict(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def alternate_titles(raw_metadata: object) -> list[str]:
    metadata = metadata_dict(raw_metadata)
    value = metadata.get("alternate_titles")
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        key = normalize_title_text(text)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def game_title_terms(
    *,
    title: object,
    original_title: object = None,
    metadata_json: object = None,
    extra_terms: Iterable[object] = (),
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in (
        title,
        original_title,
        *alternate_titles(metadata_json),
        *extra_terms,
    ):
        text = str(item or "").strip()
        key = normalize_title_text(text)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def title_query_matches(query: object, terms: Iterable[object]) -> bool:
    needle = normalize_title_text(query)
    if not needle:
        return False
    return any(
        needle in normalize_title_text(term)
        for term in terms
        if str(term or "").strip()
    )


_ITALIAN_MARKERS = frozenset(
    "il lo gli della delle dello dei degli nel nella nei nelle sul sulla alla alle allo agli "
    "dalla dalle uno per che sono".split()
)
_FOREIGN_MARKERS = frozenset(
    "the of and for with les des du de der die das und von el los las y et at in".split()
)
_ITALIAN_WEAK_MARKERS = frozenset("i le la di e un una del da con".split())
_ITALIAN_ACCENTED_END = re.compile(r"\w{2,}[àìòù]$")


def _looks_italian(text: str) -> bool:
    words = re.findall(r"[^\W\d_]+", text.casefold())
    if not words or any(word in _FOREIGN_MARKERS for word in words):
        return False
    if any(word in _ITALIAN_MARKERS or _ITALIAN_ACCENTED_END.match(word) for word in words):
        return True
    return sum(word in _ITALIAN_WEAK_MARKERS for word in words) >= 2


def italian_title(title: object, alternate_titles: Iterable[object] = ()) -> str:
    """The Italian title when BGG lists one among the alternate names, else ``title``.

    BGG does not tag the language of alternate names, so an alternate counts as Italian
    only when it carries Italian function words or accents; otherwise the primary
    title is kept.
    """
    primary = str(title or "").strip()
    for item in alternate_titles:
        text = str(item or "").strip()
        if text and _looks_italian(text):
            return text
    return primary
