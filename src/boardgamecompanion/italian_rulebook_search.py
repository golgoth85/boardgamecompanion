"""Search for Italian rulebooks of games that only have them in other languages.

The search is review-only: every candidate goes to the review queue with
generic (40) or community (70) confidence, never to an automatic download.
Identity is the game title found in the page or in the PDF name; language is
read from the file name first and from the page text second, and only Italian
candidates are kept.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from boardgamecompanion.bgg_rulebook_search import _is_allowed_download, _is_bgg_filepage
from boardgamecompanion.cloud_ai import CloudAIError
from boardgamecompanion.database import Database
from boardgamecompanion.deepseek_search import DeepSeekWeb, public_url
from boardgamecompanion.rulebook_review import RulebookReviewQueue
from boardgamecompanion.rulebooks import (
    RulebookCandidate,
    RulebookProviderError,
    RulebookQuery,
    RulebookSource,
)

MAX_SEARCHES = 4
MAX_FETCHES = 5
MAX_CANDIDATES = 6
SEARCH_KEY = "italian_rulebook_search_at"

_LANGUAGE_TOKENS = {
    "it": {"ita", "it", "italiano", "italiana", "italian", "regolamento", "regole", "istruzioni", "manuale"},
    "en": {"en", "eng", "english", "rulebook", "rules", "rule", "rulesheet", "howtoplay"},
    "fr": {"fr", "fra", "french", "francais", "regle", "regles"},
    "de": {"de", "ger", "deu", "german", "deutsch", "spielregel", "spielregeln", "anleitung", "regeln"},
    "es": {"es", "esp", "spa", "spanish", "espanol", "reglas", "reglamento"},
    "nl": {"nl", "dutch", "spelregels"},
    "pl": {"pl", "polish", "zasady", "instrukcja"},
}
_IT_WORDS = frozenset(
    "il lo la gli le della delle dei degli del che per con una uno sono turno giocatore "
    "giocatori carta carte partita ogni quando puoi deve essere anche nel nella".split()
)
_EN_WORDS = frozenset(
    "the and of to with your each player players card cards turn game when you must "
    "this that from into".split()
)
# Common suffixes of Italian publisher names, dropped from search queries.
_PUBLISHER_NOISE = re.compile(r"\b(?:s\.?r\.?l\.?|s\.?p\.?a\.?|edizioni|editore|italia|italy)\b\.?", re.I)


def _plain(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z]+", _plain(value))


def filename_language(url: str, label: str = "") -> str | None:
    """Language from the file name (and link label), when it says so."""
    path = unquote(urlsplit(url).path)
    name = path.rsplit("/", 1)[-1]
    words = set(_tokens(name)) | set(_tokens(label))
    # "/it/" or "/ita/" path segments are as telling as the file name.
    words |= {segment for segment in _tokens(path.rsplit("/", 1)[0]) if segment in {"it", "ita", "en", "eng"}}
    found = {language for language, tokens in _LANGUAGE_TOKENS.items() if words & tokens}
    if "it" in found and len(found) == 1:
        return "it"
    if len(found) == 1:
        return found.pop()
    if "it" in found and words & {"ita", "italiano", "italiana", "italian"}:
        # "rulebook ITA", "regole-eng-ita"? Explicit Italian names win only when unambiguous.
        return "it" if not words & {"eng", "english", "en"} else None
    return None


def text_language(text: str) -> str | None:
    words = _tokens(text[:6000])
    if len(words) < 30:
        return None
    italian = sum(word in _IT_WORDS for word in words)
    english = sum(word in _EN_WORDS for word in words)
    if italian >= 8 and italian > english * 2:
        return "it"
    if english >= 8 and english > italian * 2:
        return "en"
    return None


def _titles(query: RulebookQuery) -> list[str]:
    values = [query.italian_title, query.title, query.original_title]
    found: list[str] = []
    for value in values:
        plain = _plain(value)
        if plain and len(plain) >= 3 and plain not in found:
            found.append(plain)
    return found


def _mentions(haystack: str, titles: list[str]) -> bool:
    text = f" {_plain(haystack)} "
    return any(f" {title} " in text for title in titles)


def _slug_mentions(url: str, titles: list[str]) -> bool:
    name = " ".join(_tokens(unquote(urlsplit(url).path)))
    return any(f" {title} " in f" {name} " for title in titles)


def _publisher_name(value: str) -> str:
    return " ".join(_PUBLISHER_NOISE.sub(" ", value).split())


class ItalianRulebookProvider:
    """DeepSeek Search/Fetch looking only for Italian rulebooks."""

    name = "deepseek_italian_rulebook_search"

    def __init__(self, client: Any):
        self.web = DeepSeekWeb(client)

    def queries(self, query: RulebookQuery) -> list[str]:
        italian = (query.italian_title or query.title)[:65]
        bgg = (query.original_title or query.title)[:60]
        searches = [f'"{italian}" regolamento italiano pdf']
        if _plain(italian) != _plain(bgg):
            searches.append(f'"{bgg}" regolamento italiano pdf')
        else:
            searches.append(f'"{italian}" regole del gioco pdf ita')
        publisher = next((_publisher_name(name) for name in query.italian_publishers if _publisher_name(name)), "")
        if publisher:
            searches.append(f'"{italian}" {publisher[:40]} regolamento')
        searches.append(f'"{bgg}" regolamento italiano site:boardgamegeek.com')
        return searches[:MAX_SEARCHES]

    def discover(self, query: RulebookQuery) -> tuple[RulebookCandidate, ...]:
        titles = _titles(query)
        candidates: list[RulebookCandidate] = []
        state = {"seen": set(), "fetched": 0}
        try:
            for search in self.queries(query):
                if self._collect(query, titles, self.web.search(search, count=6), candidates, state):
                    break
        except CloudAIError as exc:
            if not candidates:
                raise RulebookProviderError(str(exc)) from exc
        return tuple(candidates)

    def _collect(self, query: RulebookQuery, titles: list[str], results: list[dict],
                 candidates: list[RulebookCandidate], state: dict) -> bool:
        for result in results:
            source = result["url"]
            if source in state["seen"]:
                continue
            state["seen"].add(source)
            direct_pdf = urlsplit(source).path.lower().endswith(".pdf")
            page = result
            if not direct_pdf and state["fetched"] < MAX_FETCHES:
                try:
                    page = self.web.fetch(result)
                except CloudAIError:
                    continue
                finally:
                    state["fetched"] += 1
            title = page.get("title", "")
            content = page.get("content", "") or result.get("snippet", "")
            headings = " ".join(re.findall(r"^#+\s+(.+)$", content, re.M)[:10])
            page_mentions = _mentions(f"{title} {headings} {content[:3000]}", titles)
            page_language = text_language(content)
            links = [source] if direct_pdf else []
            if not direct_pdf:
                links += re.findall(r'https://[^\s<>"\)\]]+', content)[:150]
            for raw in links:
                try:
                    url = public_url(raw.rstrip(".,;"))
                except ValueError:
                    continue
                if not (urlsplit(url).path.lower().endswith(".pdf") or _is_allowed_download(url)):
                    continue
                if any(candidate.url == url for candidate in candidates):
                    continue
                language = filename_language(url)
                if language is None and direct_pdf:
                    language = filename_language(url, title) or page_language
                elif language is None:
                    # A PDF linked from an Italian page about this game, with a neutral name.
                    language = page_language
                if language != "it":
                    continue
                if not (page_mentions or _slug_mentions(url, titles) or _mentions(title, titles)):
                    continue
                community = _is_bgg_filepage(source) and _is_allowed_download(url)
                evidence = ["title_in_source" if page_mentions else "title_in_file_name"]
                candidates.append(RulebookCandidate(
                    provider=self.name,
                    source_kind=RulebookSource.COMMUNITY if community else RulebookSource.GENERIC,
                    url=url,
                    language="it",
                    document_type="rulebook",
                    official=False,
                    confidence=70 if community else 40,
                    title=(title or "Regolamento italiano")[:500],
                    game_title=query.title,
                    metadata={
                        "source_url": source,
                        "identity_evidence": evidence,
                        "language_evidence": "file_name" if filename_language(url) == "it" else "page_text",
                        "search_provider": "deepseek",
                        "search_language": "it",
                        "requested_bgg_id": query.bgg_id,
                    },
                ))
                if len(candidates) >= MAX_CANDIDATES:
                    return True
        return False


def italian_edition(versions: list[dict[str, Any]]) -> tuple[str | None, tuple[str, ...]]:
    """Title and publishers of the Italian editions listed by BGG."""
    from boardgamecompanion.italian_titles import choose_italian_title

    publishers: list[str] = []
    for version in versions:
        if "Italian" in (version.get("languages") or []):
            publishers.extend(str(name) for name in version.get("publishers") or [] if name)
    return choose_italian_title(versions), tuple(dict.fromkeys(publishers))


class ItalianRulebookSearchService:
    def __init__(
        self,
        database: Database,
        provider: ItalianRulebookProvider | None,
        *,
        query_for: Callable[[int], RulebookQuery],
        versions: Callable[[int], list[dict[str, Any]]] | None = None,
    ):
        self.database = database
        self.provider = provider
        self.query_for = query_for
        self.versions = versions

    def games_without_italian(self) -> list[dict[str, Any]]:
        """Owned games with rulebooks, none of them in Italian."""
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT g.id, g.bgg_id, g.title, g.item_type, e.metadata_json,
                       GROUP_CONCAT(DISTINCT lower(substr(COALESCE(doc.language, 'und'), 1, 2))) AS languages,
                       (SELECT COUNT(*) FROM rulebook_review_items r
                         WHERE r.board_game_id = g.id AND r.status = 'pending'
                           AND lower(substr(r.language, 1, 2)) = 'it'
                       ) AS pending_italian
                FROM board_games g
                JOIN game_documents doc ON doc.board_game_id = g.id AND doc.document_type = 'rulebook'
                LEFT JOIN board_game_enrichments e ON e.board_game_id = g.id
                WHERE EXISTS (SELECT 1 FROM collection_entries c
                              WHERE c.board_game_id = g.id AND COALESCE(c.own, 0) = 1)
                GROUP BY g.id
                HAVING SUM(lower(substr(COALESCE(doc.language, ''), 1, 2)) = 'it') = 0
                ORDER BY g.item_type = 'expansion', g.title COLLATE NOCASE
                """
            ).fetchall()
        items = []
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except ValueError:
                metadata = {}
            items.append({
                "bgg_id": int(row["bgg_id"]),
                "title": row["title"],
                "italian_title": metadata.get("italian_title"),
                "expansion": row["item_type"] == "expansion",
                "languages": sorted(set(str(row["languages"] or "").split(",")) - {""}),
                "pending_italian": int(row["pending_italian"] or 0),
                "last_italian_search_at": metadata.get(SEARCH_KEY),
            })
        return items

    def search(self, bgg_id: int) -> dict[str, Any]:
        if self.provider is None:
            raise RulebookProviderError(
                "Ricerca web non configurata: serve DeepSeek come provider di ricerca nelle Impostazioni AI."
            )
        query = self.query_for(bgg_id)
        italian_title, publishers = query.italian_title, query.italian_publishers
        if self.versions is not None:
            try:
                found_title, found_publishers = italian_edition(self.versions(bgg_id))
            except Exception:  # BGG is evidence, not a requirement
                found_title, found_publishers = None, ()
            italian_title = italian_title or found_title
            publishers = publishers or found_publishers
        query = replace(query, italian_title=italian_title, italian_publishers=tuple(publishers))
        candidates = self.provider.discover(query)
        queue = RulebookReviewQueue(self.database)
        created = 0
        items = []
        for candidate in candidates:
            item, was_created = queue.submit(bgg_id=int(bgg_id), candidate=candidate)
            created += int(was_created)
            items.append({
                "id": item["id"],
                "status": item["status"],
                "created": bool(was_created),
                "url": candidate.url,
                "title": candidate.title,
                "confidence": candidate.confidence,
            })
        self._mark_searched(bgg_id)
        return {
            "bgg_id": int(bgg_id),
            "italian_title": italian_title,
            "italian_publishers": list(publishers),
            "queries": self.provider.queries(query),
            "candidates_found": len(candidates),
            "review_items_created": created,
            "review_items": items,
        }

    def _mark_searched(self, bgg_id: int) -> None:
        now = datetime.now(UTC).isoformat()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """SELECT g.id, e.metadata_json FROM board_games g
                   LEFT JOIN board_game_enrichments e ON e.board_game_id = g.id
                   WHERE g.bgg_id = ?""",
                (int(bgg_id),),
            ).fetchone()
            if row is None or row["metadata_json"] is None:
                return
            metadata = json.loads(row["metadata_json"] or "{}")
            metadata[SEARCH_KEY] = now
            connection.execute(
                "UPDATE board_game_enrichments SET metadata_json = ? WHERE board_game_id = ?",
                (json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":")), row["id"]),
            )
