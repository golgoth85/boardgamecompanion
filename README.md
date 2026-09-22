# BoardGameCompanion

Self-hosted companion for a physical board-game collection, designed for Docker/Unraid.

## Goals

- Import a BoardGameGeek collection from CSV without requiring the BGG API.
- Keep the BGG `objectid` as the canonical external identifier.
- Integrate with Floppy without making Floppy the only source of truth.
- Associate physical copies with barcodes, language, edition and shelf/location.
- Discover, download and archive official rulebooks in Italian and English.
- Index manuals for per-game RAG with document/page citations.
- Prefer official publisher/localizer sources; use community sources only as explicit fallbacks.

## Status

Foundation / pre-alpha.

The initial container exposes a health endpoint and establishes the persistent filesystem contract. BGG CSV import, Floppy synchronization, rulebook providers and RAG are the first implementation milestones.

## Container

Default port: `8787`

Persistent mounts:

- `/config` — application configuration/database
- `/data/import` — BGG CSV imports
- `/data/manuals` — downloaded/uploaded manuals

Example:

```bash
docker run -d \
  --name boardgamecompanion \
  -p 8787:8787 \
  -v /mnt/user/appdata/boardgamecompanion:/config \
  -v /mnt/user/boardgames/import:/data/import \
  -v /mnt/user/boardgames/manuals:/data/manuals \
  ghcr.io/golgoth85/boardgamecompanion:latest
```

Health check:

```text
GET /health
```

## Planned data flow

```text
BGG collection.csv
      |
      v
BoardGameCompanion
  |-- catalog / owned copies
  |-- barcode mapping
  |-- rulebook resolver (IT/EN)
  |-- manual archive
  |-- RAG index
  |
  +--> Floppy REST API
```

## Rulebook source policy

1. Official publisher
2. Official localizer/distributor
3. Official upload hosted elsewhere
4. Community source explicitly marked as unofficial
5. Controlled web discovery requiring review

Automatic downloads will only be accepted above a confidence threshold and will record provenance, URL, hash, language, document type and retrieval time.

## Development

See `AGENTS.md` and `docs/ARCHITECTURE.md`.

```bash
docker compose up --build
```

Then open `http://localhost:8787/health`.
