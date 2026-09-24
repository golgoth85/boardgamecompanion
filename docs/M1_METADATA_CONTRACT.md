# M1 — BGG metadata enrichment through Floppy

## Boundary

BoardGameCompanion does not store or resolve a BGG API token. It authenticates
only to Floppy. Floppy remains responsible for BGG credentials, provider access,
rate limiting, retry and provider-side caching.

The BGG CSV import remains the canonical local catalog source. Enrichment never
overwrites title, publication year, BGG rating, collection state or physical-copy
data imported from CSV.

## Cached enrichment

The local cache stores, per board game and provider:

- provider/source/media identity and source URL;
- cover URL and synopsis;
- categories;
- provider rating and rating count;
- provider year, player range, play time and minimum age;
- designers and publishers;
- payload SHA-256;
- fetched_at and updated_at timestamps.

fetched_at records the latest successful provider fetch. updated_at changes only
when the cached provider payload changes.

## Refresh policy

Refresh is explicit per game through
POST /api/games/{bgg_id}/metadata/refresh.

No catalog read triggers a provider request. A Floppy/BGG failure therefore does
not prevent catalog or detail reads and does not delete previously cached data.

## UI

Cached cover art and provider metadata are displayed when available. A failed
remote cover falls back to the generated local initials. The detail page exposes
an explicit metadata refresh action and keeps CSV-derived BGG data visibly
separate from cached provider data.

## Deferred

M1 does not add edition, language, version or product-code enrichment because
the current Floppy BGG provider boundary does not expose trustworthy edition-level
data. BGG product codes are not treated as UPC/EAN/ISBN barcodes.
