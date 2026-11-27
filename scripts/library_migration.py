#!/usr/bin/env python3
"""Verifica, backup e ripristino dello schema 30 prima del passaggio alla ludoteca.

Eseguire con il pacchetto candidato accessibile da PYTHONPATH. Le operazioni
apply/restore richiedono che BoardGameCompanion sia fermo. Il backup rimane
nel volume di configurazione. L'output contiene soltanto totali e percorsi.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from boardgamecompanion.database import Database
from boardgamecompanion.db_backup import backup
from boardgamecompanion.migrations import _INVENTORY_COLUMNS


PROTECTED = (
    "game_plays", "play_sessions", "game_progress", "player_profiles",
    "game_documents", "document_parse_runs", "document_pages", "document_chunks",
    "chunk_embeddings", "saved_game_lists", "saved_game_list_items", "personal_wishlist",
)


def readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=30)


def schema(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]


def assert_integrity(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Controllo di integrità SQLite fallito")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("Riferimenti SQLite incoerenti")


def summary(connection: sqlite3.Connection) -> dict[str, int]:
    result = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("board_games", "collection_entries", *PROTECTED)
    }
    result["schema"] = schema(connection)
    result["owned"] = connection.execute(
        "SELECT COUNT(DISTINCT board_game_id) FROM collection_entries WHERE own=1"
    ).fetchone()[0]
    if result["schema"] == 30:
        fields = ("barcode", "notes", "language", "edition", "publishers",
                  "version_year_published", "acquisition_date", "acquired_from",
                  "price_paid", "price_currency", "condition_text", "inventory_location")
        expressions = ", ".join(f"COUNT(NULLIF(pc.{key}, ''))" for key in fields)
        copies = connection.execute(f"SELECT COUNT(*), {expressions} FROM physical_copies pc").fetchone()
        result["legacy_rows"] = copies[0]
        result.update({f"legacy_{field}": count for field, count in zip(fields, copies[1:])})
        result["legacy_notes_exclusive"] = connection.execute("""
            SELECT COUNT(*) FROM physical_copies pc
            LEFT JOIN collection_entries c ON c.id=pc.source_collection_entry_id
            WHERE NULLIF(trim(pc.notes), '') IS NOT NULL AND pc.notes IS NOT c.private_comment
        """).fetchone()[0]
    if result["schema"] == 31:
        result["product_hints"] = connection.execute("SELECT COUNT(*) FROM barcode_product_hints").fetchone()[0]
    return result


def fingerprint(connection: sqlite3.Connection, table: str, *, cleaned: bool) -> str:
    columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
    if table == "collection_entries":
        columns = [name for name in columns if name not in _INVENTORY_COLUMNS]
    paths = []
    if cleaned and table in {"collection_entries", "board_games"}:
        paths = [f"$.{key}" for key in _INVENTORY_COLUMNS.values()]
        expression = (
            f"CASE WHEN json_valid(source_metadata_json) THEN "
            f"json_remove(source_metadata_json, {','.join('?' for _ in paths)}) "
            "ELSE source_metadata_json END"
        )
        columns[columns.index("source_metadata_json")] = expression
    digest = hashlib.sha256()
    for row in connection.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY rowid", paths):
        digest.update(repr(row).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def assert_preserved(before: sqlite3.Connection, after: sqlite3.Connection, *, migrated: bool) -> None:
    for table in (*PROTECTED, "board_games", "collection_entries"):
        if fingerprint(before, table, cleaned=migrated) != fingerprint(after, table, cleaned=migrated):
            raise RuntimeError(f"Dati diversi nella tabella {table}")


def apply(database: Path, destination: Path) -> None:
    with closing(readonly(database)) as source:
        assert_integrity(source)
        if schema(source) != 30:
            raise RuntimeError("Atteso schema 30 prima della migrazione")
        print("PRIMA", summary(source), flush=True)
        snapshot = backup(database, destination)
        if snapshot["integrity"] != "ok" or snapshot["schema"] != 30:
            raise RuntimeError("Backup non verificato")
        with closing(readonly(destination)) as saved:
            assert_preserved(source, saved, migrated=False)
            if fingerprint(source, "physical_copies", cleaned=False) != fingerprint(saved, "physical_copies", cleaned=False):
                raise RuntimeError("Il backup non contiene tutte le righe di inventario")
        print("BACKUP", snapshot, flush=True)

    Database(database).initialize()
    with closing(readonly(destination)) as before, closing(readonly(database)) as after:
        assert_integrity(after)
        if schema(after) != 31:
            raise RuntimeError("Atteso schema 31 dopo la migrazione")
        if after.execute("SELECT 1 FROM sqlite_schema WHERE name='physical_copies'").fetchone():
            raise RuntimeError("La vecchia tabella è ancora nello schema")
        assert_preserved(before, after, migrated=True)
        print("DOPO", summary(after), flush=True)


def restore(database: Path, source: Path) -> None:
    replacement = database.with_name(database.name + ".restore-m30")
    with closing(readonly(source)) as saved:
        assert_integrity(saved)
        if schema(saved) != 30:
            raise RuntimeError("Atteso backup dello schema 30")
    snapshot = backup(source, replacement)
    if snapshot["integrity"] != "ok":
        raise RuntimeError("Copia di ripristino non verificata")
    with closing(readonly(source)) as saved, closing(readonly(replacement)) as check:
        assert_preserved(saved, check, migrated=False)
        if fingerprint(saved, "physical_copies", cleaned=False) != fingerprint(check, "physical_copies", cleaned=False):
            raise RuntimeError("La copia ripristinata ha perso dati di inventario")
    quarantine = database.parent / "backups" / "rollback-m31"
    quarantine.mkdir(mode=0o700)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        if sidecar.exists():
            sidecar.rename(quarantine / sidecar.name)
    metadata = database.stat()
    os.chown(replacement, metadata.st_uid, metadata.st_gid)
    database.rename(quarantine / database.name)
    os.replace(replacement, database)
    print("RIPRISTINATO", database, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "apply", "restore"))
    parser.add_argument("database", type=Path)
    parser.add_argument("backup", type=Path, nargs="?")
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "audit":
        with closing(readonly(args.database)) as connection:
            print("AUDIT", summary(connection))
    elif args.backup is None:
        parser.error("Serve il percorso del backup")
    elif args.action == "apply":
        apply(args.database, args.backup)
    else:
        restore(args.database, args.backup)


if __name__ == "__main__":
    main()
