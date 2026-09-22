# BoardGameCompanion

Self-hosted companion for a physical board-game collection, designed for Docker/Unraid.

## Current capabilities

- Import a BoardGameGeek collection CSV without a BGG API token.
- Preserve the BGG `objectid` as the canonical external identifier.
- Idempotent imports backed by SQLite.
- Store game metadata and collection-state/physical-copy fields exposed by BGG CSV.
- Search and filter the catalog through a REST API.
- Persist uploaded BGG CSV snapshots under `/data/import`.

Planned next: Floppy synchronization, barcode workflow, rulebook discovery/archive and page-cited RAG.

## Container

Default port: `8787`

Persistent mounts:

- `/config` — SQLite database and configuration
- `/data/import` — BGG CSV import snapshots
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

OpenAPI/Swagger UI: `http://<server>:8787/docs`

## BGG CSV import

Export your collection from BoardGameGeek and upload it through:

```text
POST /api/imports/bgg-csv
multipart field: file
```

The importer requires `objectid` and `objectname`. It retains the original row as source metadata and maps the useful BGG fields into the internal catalog.

Re-importing the exact same CSV re-validates the rows and leaves existing records unchanged. A later changed export updates matching records by BGG `objectid` / BGG collection `collid` without creating duplicates.

Missing rows are **not deleted automatically**. This is intentional because an `owned` export is only a partial view of a BGG account and must not erase wishlist or other states imported from a broader export.

## Catalog API

```text
GET /api/catalog/stats
GET /api/games
GET /api/games/{bgg_id}
```

`GET /api/games` supports:

- `q`
- `item_type`
- `owned`
- `limit`
- `offset`

## Development

See `AGENTS.md` and `docs/ARCHITECTURE.md`.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Or:

```bash
docker compose up --build
```
