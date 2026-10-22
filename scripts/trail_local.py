#!/usr/bin/env python3
"""Mappa strutturale Trail facoltativa; nessuna integrazione automatica degli agenti."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.23.1"
INSTALL = Path.home() / ".local/share" / f"trail-code-{VERSION}"
CACHE = Path("/temp/boardgamecompanion/trail-code-local") / hashlib.sha256(
    str(ROOT).encode()
).hexdigest()[:12]


def storage_check() -> None:
    mount = subprocess.run(
        ["findmnt", "-n", "-o", "TARGET,FSTYPE", "-T", "/temp"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    if mount != ["/temp", "fuse.shfs"]:
        raise RuntimeError("/temp deve essere il mount NAS fuse.shfs; nessun ripiego locale")
    # Controllare anche i genitori già esistenti: una sottocartella può stare
    # su un disco diverso da quello indicato dalla radice della share.
    paths = [Path("/temp"), *reversed(CACHE.parents[:-1]), CACHE]
    for path in dict.fromkeys(paths):
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_dir() or not os.access(path, os.W_OK):
            raise RuntimeError(f"Cartella non scrivibile o non ammessa: {path}")
        location = os.getxattr(path, "system.LOCATION").decode().split(",")
        if not location or any(
            not disk.startswith("disk") or not disk[4:].isdigit() or disk == "disk2"
            for disk in location
        ):
            raise RuntimeError(f"Collocazione non ammessa per {path}: {location}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "map", "ask", "callers", "skeleton", "status"])
    parser.add_argument("value", nargs="?", help="domanda, simbolo o file relativo al repository")
    parser.add_argument("--check", action="store_true", help="con build: controlla soltanto la freschezza")
    parser.add_argument("--source", action="store_true", help="con ask: include gli estratti di codice")
    args = parser.parse_args()
    needs_value = args.command in {"ask", "callers", "skeleton"}
    if (needs_value != (args.value is not None)
            or (args.check and args.command != "build")
            or (args.source and args.command != "ask")):
        parser.error("valore solo per ask/callers/skeleton; --check solo con build; --source solo con ask")
    if args.value is not None and args.value.startswith("-"):
        parser.error("il valore non può essere un'opzione della CLI")
    if args.command == "skeleton":
        source = (ROOT / args.value).resolve()
        if not source.is_relative_to(ROOT) or not source.is_file():
            parser.error("skeleton richiede un file dentro questo checkout")
    storage_check()
    package = INSTALL / "node_modules/@trailhq/trail-code/package.json"
    if not package.is_file() or json.loads(package.read_text())["version"] != VERSION:
        raise RuntimeError(f"Installare Trail {VERSION} come descritto in docs/TRAIL-PILOT.md")
    cli = INSTALL / "node_modules/.bin/trail"
    env = os.environ.copy()
    env.update({
        "DO_NOT_TRACK": "1", "CI": "1", "GRAFT_DIR": str(CACHE),
        "GRAFT_NO_GITIGNORE": "1", "GRAFT_NO_IGNORE": "1",
        # Trail verifica anche la propria versione in background. npm offline
        # impedisce che quella verifica contatti il registry durante l'uso.
        "npm_config_offline": "true", "npm_config_update_notifier": "false",
        "npm_config_cache": str(CACHE / ".npm-cache"),
    })
    command = [str(cli), "--dir", str(CACHE), args.command]
    if args.command == "build":
        command += ["--only-dir", "src", "--only-dir", "tests", "--no-gitignore", "--no-ignore"]
        if args.check:
            command.append("--check")
    elif args.command == "ask":
        command += [args.value, "--limit", "4"]
        if args.source:
            command.append("--source")
    elif needs_value:
        command.append(args.value)
    command.append(str(ROOT))
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    for output, stream in [(result.stdout, sys.stdout), (result.stderr, sys.stderr)]:
        # Questa riga include una richiesta di riportare risparmi stimati da
        # file interi. Non è una misura del nostro flusso di lavoro.
        stream.writelines(
            line for line in output.splitlines(keepends=True)
            if not line.startswith(("[trail] tokens saved", "[graft] tokens saved"))
        )
    return result.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Trail locale: {error}", file=sys.stderr)
        sys.exit(1)
