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
- Camera-first physical-copy barcode lookup with native BarcodeDetector plus a local ZXing fallback; manual entry remains available.
- Persist uploaded BGG CSV snapshots under `/data/import`.
- REST API and OpenAPI/Swagger remain available.
- Floppy connection health/capability checks.
- Floppy board-game comparison and guarded add-only collection synchronization.
- Manual PDF archive plus guarded provider-independent rulebook fetch foundation.
- Persistent rulebook review queue with auditable unattended/manual approval state.
- Scheduled guarded re-checks for approved rulebook candidates with version-by-hash archival and run audit.

Browser camera access requires a secure context (HTTPS, or localhost); on plain LAN HTTP the scanner exposes the manual fallback instead.

Because the BGG CSV export does not contain cover-image URLs, the current UI uses generated cover placeholders. Real cover art belongs to the later metadata-enrichment phase.

Floppy synchronization is add-only and guarded by a dry-run plan hash. BoardGameCompanion never removes Floppy media, collection copies or history during sync.

Post-P6B roadmap: finish barcode hardening, add BGG metadata enrichment through the existing Floppy provider boundary, then deliver P7 as independently reviewable PDF-ingest, indexing/retrieval, answer/citation and UI phases. See `docs/ROADMAP.md`.

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

The home page can verify Floppy connectivity and compare the owned local catalog with both tracked board games and the Floppy collection. Matching uses, in order:

1. a previously persisted BoardGameCompanion ↔ Floppy link;
2. explicit BGG ID when Floppy exposes one;
3. exact normalized title + publication year as a lower-confidence fallback.

A `manual` Floppy `media_id` is never assumed to be a BGG ID.

### Add-only synchronization

**Confronta cataloghi** always performs a dry-run first. The preview separates games into:

- already owned in Floppy;
- tracked in Floppy but missing from its collection;
- media missing entirely from Floppy;
- ambiguous matches, which block automatic write sync.

When the live Floppy OpenAPI schema exposes the validated media and collection write contracts, the UI offers a sync button. Each apply request:

- requires the exact `plan_hash` returned by the preceding preview;
- re-reads Floppy before writing and rejects a stale plan;
- processes at most 20 items from the UI (API maximum: 50);
- only adds missing records;
- never deletes Floppy media, collection entries or history;
- persists BGG ↔ Floppy links locally for idempotence and recovery.

For a missing game, BoardGameCompanion first tries Floppy's BGG provider. If provider resolution is unavailable, it can create a manual Floppy board-game item and retains the canonical BGG ID in its local link. Infrastructure/authentication failures do not trigger this fallback.

At present one owned BGG row maps to one Floppy collection copy; quantity-aware multi-copy synchronization is intentionally deferred.

API endpoints:

```text
GET  /api/settings/floppy
PUT  /api/settings/floppy
GET  /api/integrations/floppy/status
GET  /api/integrations/floppy/preview
POST /api/integrations/floppy/sync
```

The sync endpoint accepts the dry-run `plan_hash` and an optional `batch_size`.

### Advanced environment overrides

For automated deployments, these optional environment variables override values saved in the app:

```text
BGC_FLOPPY_URL
BGC_FLOPPY_API_KEY
BGC_FLOPPY_TIMEOUT_SECONDS
BGC_FLOPPY_VERIFY_TLS
```

They are intentionally not present in the default Unraid template.

## Rulebook updates

Approved rulebook candidates are monitored independently from the review queue at `/updates`. New targets are due immediately; subsequent successful checks use the configured interval (30 days by default). Failed checks use bounded exponential backoff and remain auditable without changing the approval decision.

The scheduler reuses the guarded P5B fetch path and archives a new `game_documents` version only when the fetched SHA-256 is new for that game. Existing document metadata is not overwritten. Lease claims carry a monotonically increasing fencing generation and are renewed by a heartbeat while work is in flight; both archive insertion and completion verify the exact fence so a stale worker cannot publish a document after another worker has reclaimed the target. Scheduled archive destinations are opened through no-follow directory descriptors rooted under the manuals directory. Corrupt post-claim review data is recorded as a failed attempt and does not stop later due targets in the same batch.

The update worker shuts down gracefully by waiting for an already-running bounded job instead of cancelling only the asyncio wrapper. The `/updates` UI also refreshes periodically so background scheduler transitions do not remain indefinitely stale.

API endpoints:

```text
GET   /api/rulebook-updates
GET   /api/rulebook-updates/{review_id}
PATCH /api/rulebook-updates/{review_id}
POST  /api/rulebook-updates/{review_id}/run
GET   /api/rulebook-updates/{review_id}/runs
```

Optional environment overrides:

```text
BGC_RULEBOOK_FETCH_MAX_BYTES
BGC_RULEBOOK_UPDATE_WORKER_ENABLED
BGC_RULEBOOK_UPDATE_POLL_SECONDS
BGC_RULEBOOK_UPDATE_DEFAULT_INTERVAL_SECONDS
BGC_RULEBOOK_UPDATE_RETRY_BASE_SECONDS
BGC_RULEBOOK_UPDATE_RETRY_MAX_SECONDS
BGC_RULEBOOK_UPDATE_LEASE_SECONDS
BGC_RULEBOOK_UPDATE_BATCH_SIZE
```

Provider-specific discovery and replacement-URL search are intentionally not part of scheduled updates. A new candidate must still pass through the resolver and P6A approval policy.

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
