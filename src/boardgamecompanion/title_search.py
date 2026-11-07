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
# Italian marks accents only on the last letter; "Crónicas" or "Zürich" are not Italian.
_FOREIGN_LETTER = re.compile(r"[ñçãõäöüßåøæ]|[áéíóúàèìòùâêîôû](?=\w)")


def _looks_italian(text: str) -> bool:
    words = re.findall(r"[^\W\d_]+", text.casefold())
    if not words or any(word in _FOREIGN_MARKERS for word in words):
        return False
    if any(_FOREIGN_LETTER.search(word) for word in words):
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


# BGG version names often label the release ("Italian edition 2016", "Ghenos Games
# Italian edition", "Multilingual first edition") instead of giving a localized title.
_EDITION_WORDS = frozenset(
    "edition editions version printing reprint release edizione versione ristampa "
    "italian english german french spanish multilingual".split()
)
_EDITION_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def is_edition_label(text: object, known_titles: Iterable[object] = ()) -> bool:
    """True when a BGG version name describes the release rather than titling the game.

    Words in parentheses are ignored ("… (Seconda edizione)"), and a name BGG also lists
    as an alternate title of the game is always accepted.
    """
    key = normalize_title_text(text)
    if not key:
        return True
    if key in {normalize_title_text(title) for title in known_titles}:
        return False
    outside = re.sub(r"\([^)]*\)", " ", str(text))
    words = normalize_title_text(outside).split()
    return (
        not words
        or any(word in _EDITION_WORDS for word in words)
        or bool(_EDITION_YEAR.search(outside))
    )


def stored_italian_title(metadata: dict[str, Any]) -> str:
    """The collected Italian edition title, unless it is only an edition label."""
    title = str(metadata.get("italian_title") or "").strip()
    if not title or is_edition_label(title, alternate_titles(metadata)):
        return ""
    return title


def display_title(title: object, metadata_json: object = None) -> str:
    """Title shown in the UI: the collected Italian edition title, else the heuristic."""
    metadata = metadata_dict(metadata_json)
    return stored_italian_title(metadata) or italian_title(title, alternate_titles(metadata))
