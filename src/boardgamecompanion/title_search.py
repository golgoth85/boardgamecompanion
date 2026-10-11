from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Iterable


def normalize_title_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold())
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
