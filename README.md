# BoardGameCompanion

Self-hosted companion for a physical board-game collection, designed for Docker/Unraid.

## Current capabilities

- Responsive web catalog at `/`.
- Import or update a BoardGameGeek collection CSV directly from the web UI.
- Search and filter by title, base game/expansion and ownership state.
- Sort by title, year, BGG rating, BGG rank or complexity.
- Dedicated game detail pages at `/games/{bgg_id}`.
- Preserve the BGG `objectid` as the canonical external identifier.
- Idempotent imports backed by SQLite.
- Store game metadata and collection-state/physical-copy fields exposed by BGG CSV.
- Persist uploaded BGG CSV snapshots under `/data/import`.
- REST API and OpenAPI/Swagger remain available.
- Floppy connection health/capability checks.
- Read-only Floppy board-game catalog comparison with BGG-ID-first matching.

Because the BGG CSV export does not contain cover-image URLs, the current UI uses generated cover placeholders. Real cover art belongs to the later metadata-enrichment phase.

The Floppy integration is deliberately read-only at this stage. BoardGameCompanion reads the live Floppy OpenAPI schema and will not enable write synchronization until the actual media/collection contracts exposed by the configured Floppy instance are validated.

Planned next: validated Floppy write synchronization, barcode workflow, rulebook discovery/archive and page-cited RAG.

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

Web UI: `http://<server>:8787/`

OpenAPI/Swagger UI: `http://<server>:8787/docs`

## BGG CSV import

From the web UI, choose **Importa BGG CSV** and select the collection export.

API equivalent:

```text
POST /api/imports/bgg-csv
multipart field: file
```

The importer requires `objectid` and `objectname`. It retains the original row as source metadata and maps the useful BGG fields into the internal catalog.

Re-importing the exact same CSV re-validates the rows and leaves existing records unchanged. A later changed export updates matching records by BGG `objectid` / BGG collection `collid` without creating duplicates.

Missing rows are **not deleted automatically**. This is intentional because an `owned` export is only a partial view of a BGG account and must not erase wishlist or other states imported from a broader export.


## Floppy integration

Configure Floppy from the BoardGameCompanion web UI:

1. open **Impostazioni**;
2. enter the Floppy base URL;
3. enter the API Token from Floppy **Settings → Integrations**;
4. optionally adjust timeout/TLS verification;
5. choose **Salva** or **Salva e verifica**.

Settings are persisted in the SQLite database under `/config`. The API token is never returned to the browser or exposed by the settings API after it has been saved.

The home page can then verify Floppy connectivity and compare the owned local catalog with Floppy using:

1. explicit BGG ID when Floppy exposes one;
2. exact normalized title + publication year as a lower-confidence fallback.

A `manual` Floppy `media_id` is never assumed to be a BGG ID.

API endpoints:

```text
GET /api/settings/floppy
PUT /api/settings/floppy
GET /api/integrations/floppy/status
GET /api/integrations/floppy/preview
```

The preview performs no writes or deletes in Floppy.

### Advanced environment overrides

For automated deployments, these optional environment variables override values saved in the app:

```text
BGC_FLOPPY_URL
BGC_FLOPPY_API_KEY
BGC_FLOPPY_TIMEOUT_SECONDS
BGC_FLOPPY_VERIFY_TLS
```

They are intentionally not present in the default Unraid template.

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
- `sort` — `title`, `year_desc`, `rating_desc`, `rank_asc`, `weight_desc`
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
