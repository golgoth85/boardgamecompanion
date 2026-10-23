"""Pick a few rulebook passages that show, in broad strokes, how a game works.

Selection is lexical and reads stored chunks directly: description writing must
never depend on the embedding provider (LM Studio may be asleep and waking it is
not something a text rewrite is allowed to trigger).
"""
from __future__ import annotations

import re
from typing import Any

from boardgamecompanion.database import Database

MAX_EXCERPT_CHARS = 900
MAX_TOTAL_CHARS = 4200
PER_TOPIC = 2
MIN_HITS = 2

TOPICS: dict[str, tuple[str, ...]] = {
    "obiettivo e fine della partita": (
        "obiettivo", "scopo del gioco", "scopo", "vittoria", "vincitore", "vince",
        "fine della partita", "fine del gioco", "punti vittoria",
        "goal", "objective", "winner", "wins", "end of the game", "victory",
    ),
    "svolgimento di un turno": (
        "turno", "azioni", "azione", "fase", "round", "giocatore di turno",
        "turn", "action", "phase", "on your turn",
    ),
    "modalità e struttura": (
        "scenario", "scenari", "campagna", "modalità", "cooperativo", "solitario",
        "capitolo", "scenarios", "campaign", "mode", "cooperative", "solo", "chapter",
    ),
}

LANGUAGE_PRIORITY = {"it": 0, "en": 1}


def _score(text: str, keywords: tuple[str, ...]) -> int:
    folded = text.casefold()
    return sum(len(re.findall(rf"\b{re.escape(word)}", folded)) for word in keywords)


def rank_excerpts(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Choose up to PER_TOPIC chunks per topic, without repeats, within the budget."""
    picked: dict[tuple[int, int], dict[str, Any]] = {}
    for topic, keywords in TOPICS.items():
        scored = []
        for chunk in chunks:
            key = (int(chunk["page_number"]), int(chunk["chunk_index"]))
            if key in picked:
                continue
            hits = _score(chunk["text"], keywords)
            if hits >= MIN_HITS:
                # Density, not raw count, so a long page of rules does not always win.
                scored.append((hits / max(len(chunk["text"]), 1), -key[0], key, chunk))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        for _, _, key, chunk in scored[:PER_TOPIC]:
            picked[key] = {"topic": topic, "chunk": chunk}

    result: list[dict[str, Any]] = []
    total = 0
    for key in sorted(picked):
        text = " ".join(picked[key]["chunk"]["text"].split())[:MAX_EXCERPT_CHARS]
        if total + len(text) > MAX_TOTAL_CHARS:
            break
        total += len(text)
        result.append({"page": key[0], "topic": picked[key]["topic"], "text": text})
    return result


def select_excerpts(database: Database, board_game_id: int) -> dict[str, Any] | None:
    """Return excerpts from the best indexed rulebook of a game, or None."""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT document_id,chunk_run_id,page_number,chunk_index,text,language,
                   is_official,created_at
            FROM document_chunks
            WHERE board_game_id=? AND document_type='rulebook'
            """,
            (int(board_game_id),),
        ).fetchall()
    if not rows:
        return None

    documents: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = documents.setdefault(
            row["document_id"],
            {"language": row["language"], "official": int(row["is_official"]), "runs": {}},
        )
        entry["runs"].setdefault(row["chunk_run_id"], row["created_at"])
    best_id = min(
        documents,
        key=lambda doc_id: (
            LANGUAGE_PRIORITY.get(str(documents[doc_id]["language"])[:2].lower(), 2),
            -documents[doc_id]["official"],
            doc_id,
        ),
    )
    runs = documents[best_id]["runs"]
    run_id = max(runs, key=lambda key: (runs[key], key))
    chunks = [
        dict(row)
        for row in rows
        if row["document_id"] == best_id and row["chunk_run_id"] == run_id
    ]
    excerpts = rank_excerpts(chunks)
    if not excerpts:
        return None
    return {
        "language": documents[best_id]["language"],
        "official": bool(documents[best_id]["official"]),
        "pages_in_document": max(int(chunk["page_number"]) for chunk in chunks),
        "excerpts": excerpts,
    }
