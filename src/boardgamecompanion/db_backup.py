"""Backup coerente del database SQLite, anche con l'applicazione in esecuzione.

Uso (es. in un container temporaneo con /config montato):
    python -m boardgamecompanion.db_backup /config/boardgamecompanion.sqlite3 /config/backups/nome.sqlite3
Usa l'API di backup di SQLite (consistente con WAL), poi verifica l'integrità della copia.
Non sovrascrive mai un file esistente.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def backup(source: Path, target: Path) -> dict[str, object]:
    target.parent.mkdir(parents=True, exist_ok=True)
    origin = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    try:
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise SystemExit(f"{target} esiste già: scegli un altro nome") from exc
        os.close(fd)
        copy = sqlite3.connect(target)
        try:
            origin.backup(copy)
        finally:
            copy.close()
    finally:
        origin.close()
    check = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        version = check.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0]
        plays = check.execute("SELECT COUNT(*) FROM game_plays").fetchone()[0]
    finally:
        check.close()
    return {"target": str(target), "integrity": integrity, "schema": version, "plays": plays,
            "bytes": target.stat().st_size}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    result = backup(Path(argv[0]), Path(argv[1]))
    print(result)
    return 0 if result["integrity"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
