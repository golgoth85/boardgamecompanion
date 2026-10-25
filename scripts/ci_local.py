#!/usr/bin/env python3
"""Controlli di validazione di BoardGameCompanion, da eseguire nel container di sviluppo.

Elenco unico dei test: pytest dell'applicazione (senza e2e) e test browser e2e
(Chromium + Playwright per Python; se mancano, l'e2e risulta saltato o fallito
e la UI va provata con ~/.local/bin/ui-node). Ogni controllo gira offline, non
scrive nella sorgente e cancella le directory temporanee dei test riusciti, così
/tmp (tmpfs) non si riempie. Uscita 0 solo se tutti i controlli sono passati.

Uso:
  python scripts/ci_local.py                       # tutti i controlli
  python scripts/ci_local.py --list                # elenca i controlli ed esce
  python scripts/ci_local.py --only NOME ...       # solo i controlli indicati
  python scripts/ci_local.py --allow-missing-deps  # solo prove locali: dipendenza mancante = SKIP
  python scripts/ci_local.py --skip-e2e            # senza test browser (solo prove locali)
Solo libreria standard.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_TAIL = 2000
MAX_TAILS = 3
# Il runner del guest concede 1700 s; qui ci si ferma prima e si stampa il riepilogo.
DEFAULT_TOTAL_TIMEOUT = 1500
DEAD_PROXY = "http://127.0.0.1:9"
MISSING_PY = re.compile(r"No module named '?([A-Za-z0-9_\.]+)'?")
MISSING_NODE = re.compile(r"Cannot find module '([^']+)'")
NPM_MISSING_BIN = re.compile(r"(?:sh: \d+: )?([\w.-]+): not found")


@dataclass
class Check:
    name: str
    argv: list[str]
    cwd: Path
    timeout: int
    env: dict[str, str] = field(default_factory=dict)  # aggiunte all'ambiente di base


@dataclass
class Context:
    root: Path  # sorgente originale (sola lettura nel guest)
    src: Path  # radice su cui girano i controlli (= root, salvo copia scrivibile)
    work: Path  # directory scrivibile temporanea
    data_dir: Path  # DATA_DIR effettivo


@dataclass
class Result:
    name: str
    status: str  # PASS | FAIL | TIMEOUT | SKIP | NON ESEGUITO
    seconds: float
    note: str = ""
    output: str = ""


def prepend_path(env: dict[str, str], key: str, value: str) -> None:
    parts = [p for p in env.get(key, "").split(os.pathsep) if p]
    if value not in parts:
        env[key] = os.pathsep.join([value, *parts])


def base_env(ctx: Context) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # la sorgente puo' essere in sola lettura
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"  # i plugin si caricano esplicitamente con -p
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.setdefault(key, DEAD_PROXY)
    env.setdefault("NO_PROXY", "127.0.0.1,localhost")
    env["DATA_DIR"] = str(ctx.data_dir)
    configure_env(env, ctx)
    return env


def tool(name: str, fallback: str) -> str:
    return shutil.which(name) or (fallback if Path(fallback).exists() else name)


def kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_process(argv: list[str], cwd: Path, env: dict[str, str], timeout: float) -> tuple[int | None, str]:
    """Esegue argv in un gruppo di processi proprio; None come codice = timeout."""
    try:
        proc = subprocess.Popen(
            argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            errors="replace", start_new_session=True,
        )
    except OSError as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    try:
        out, _ = proc.communicate(timeout=max(1.0, timeout))
        return proc.returncode, out or ""
    except subprocess.TimeoutExpired as exc:
        kill_group(proc)
        try:
            tail, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            tail, _ = proc.communicate()
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return None, str(partial) + (tail or "")


def local_module(top: str, ctx: Context) -> bool:
    for base in (ctx.src, ctx.src / "src"):
        if (base / top).exists() or (base / f"{top}.py").exists():
            return True
    return False


def missing_dependency(output: str, ctx: Context) -> str | None:
    """Nome di una dipendenza esterna mancante, se l'errore e' quello (non un test rotto)."""
    for match in MISSING_PY.finditer(output):
        top = match.group(1).split(".")[0]
        if not local_module(top, ctx):
            return top
    for match in MISSING_NODE.finditer(output):
        name = match.group(1)
        if not name.startswith((".", "/")):
            return name
    return None


def run_check(check: Check, ctx: Context, timeout: float, allow_missing_deps: bool) -> Result:
    started = time.monotonic()
    env = base_env(ctx)
    env.update(check.env)
    limit = min(check.timeout, timeout)
    code, out = run_process(check.argv, check.cwd, env, limit)
    elapsed = round(time.monotonic() - started, 1)
    if code is None:
        return Result(check.name, "TIMEOUT", elapsed, f"oltre {int(limit)} s", out)
    if code == 0:
        return Result(check.name, "PASS", elapsed)
    dep = missing_dependency(out, ctx)
    if dep:
        status = "SKIP" if allow_missing_deps else "FAIL"
        return Result(check.name, status, elapsed, f"dipendenza mancante: {dep}", out)
    return Result(check.name, "FAIL", elapsed, f"codice {code}", out)


PYTEST = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
          "-o", "tmp_path_retention_policy=failed"]
CHROMIUM = "/usr/bin/chromium"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skip-e2e", action="store_true",
                        help="non esegue tests/e2e (serve Chromium + Playwright; il profilo del registro li richiede)")


def extra_notes(args: argparse.Namespace) -> list[str]:
    return ["Test browser e2e: NON eseguiti (--skip-e2e)."] if args.skip_e2e else []


def configure_env(env: dict[str, str], ctx: Context) -> None:
    prepend_path(env, "PYTHONPATH", str(ctx.src / "src"))
    for key, name in (("BGC_CONFIG_DIR", "config"), ("BGC_IMPORT_DIR", "import"), ("BGC_MANUALS_DIR", "manuals")):
        env.setdefault(key, str(ctx.data_dir / name))
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    env.setdefault("BGC_CHROMIUM_EXECUTABLE", CHROMIUM)


def prepare(ctx: Context) -> Context:
    return ctx


def build_checks(ctx: Context, args: argparse.Namespace) -> list[Check]:
    root = ctx.src
    checks = [Check("pytest-application", PYTEST + ["tests", "--ignore=tests/e2e"], root, 720)]
    if not getattr(args, "skip_e2e", False):
        checks.append(Check("pytest-browser-e2e", PYTEST + ["tests/e2e"], root, 900))
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controlli di validazione del repository.")
    parser.add_argument("--list", action="store_true", help="elenca i controlli ed esce")
    parser.add_argument("--only", nargs="+", metavar="NOME", help="esegue solo i controlli indicati")
    parser.add_argument("--fail-fast", action="store_true", help="si ferma al primo controllo fallito")
    parser.add_argument("--allow-missing-deps", action="store_true",
                        help="solo per prove locali: una dipendenza esterna mancante da' SKIP e non fallisce")
    parser.add_argument("--total-timeout", type=int, default=DEFAULT_TOTAL_TIMEOUT, help="budget complessivo in secondi")
    parser.add_argument("--keep-data", action="store_true", help="non cancella la directory temporanea di lavoro")
    add_arguments(parser)
    args = parser.parse_args(argv)

    if args.list:
        list_ctx = Context(ROOT, ROOT, ROOT, Path(os.environ.get("DATA_DIR") or tempfile.gettempdir()))
        for c in build_checks(list_ctx, args):
            print(f"{c.name:34} timeout={c.timeout:>4}s  cwd={c.cwd.relative_to(ROOT) if c.cwd.is_relative_to(ROOT) else c.cwd}")
        return 0

    deadline = time.monotonic() + args.total_timeout
    work = Path(tempfile.mkdtemp(prefix="ci-local-"))
    data_env = os.environ.get("DATA_DIR")
    data_dir = Path(data_env) if data_env else work / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    results: list[Result] = []
    notes: list[str] = []
    try:
        ctx = Context(ROOT, ROOT, work, data_dir)
        try:
            ctx = prepare(ctx)
        except (RuntimeError, OSError, shutil.Error) as exc:
            print(f"[ci_local] preparazione fallita: {exc}", flush=True)
            results.append(Result("preparazione", "FAIL", 0.0, str(exc)))
            checks: list[Check] = []
        else:
            checks = build_checks(ctx, args)
        known = {c.name for c in checks}
        if args.only:
            unknown = sorted(set(args.only) - known)
            if unknown and checks:
                parser.error("controlli sconosciuti: " + ", ".join(unknown))
        selected = [c for c in checks if not args.only or c.name in args.only]
        notes = extra_notes(args)
        for index, check in enumerate(selected):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                results.extend(Result(c.name, "NON ESEGUITO", 0.0, "budget complessivo esaurito") for c in selected[index:])
                break
            print(f"[ci_local] {check.name} ...", flush=True)
            result = run_check(check, ctx, remaining, args.allow_missing_deps)
            results.append(result)
            print(f"[ci_local] {check.name}: {result.status} ({result.seconds}s)", flush=True)
            if result.status in ("FAIL", "TIMEOUT") and args.fail_fast:
                results.extend(Result(c.name, "NON ESEGUITO", 0.0, "--fail-fast") for c in selected[index + 1:])
                break
    finally:
        if not args.keep_data:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"[ci_local] directory di lavoro conservata: {work}")

    bad = [r for r in results if r.status in ("FAIL", "TIMEOUT", "NON ESEGUITO")]
    skipped = [r for r in results if r.status == "SKIP"]
    shown = 0
    for r in results:
        if r.status in ("FAIL", "TIMEOUT") and r.output and shown < MAX_TAILS:
            shown += 1
            print(f"\n--- {r.name}: ultime righe dell'output ---\n{r.output[-OUTPUT_TAIL:]}")
    print("\n=== Riepilogo ci_local ===")
    for r in results:
        note = f"  {r.note}" if r.note else ""
        print(f"{r.name:34} {r.status:13} {r.seconds:>7.1f}s{note}")
    for line in notes:
        print(line)
    total = sum(r.seconds for r in results)
    print(f"Totale: {len(results)} controlli, {len(bad)} da correggere, {len(skipped)} saltati, {total:.1f}s")
    if skipped and not bad:
        print("ESITO: PASS PARZIALE (controlli saltati per --allow-missing-deps: NON valido come PASS di CI)")
    else:
        print("ESITO: " + ("PASS" if not bad else "FAIL"))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
