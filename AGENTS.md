# AGENTS.md

## Mission

BoardGameCompanion is a self-hosted Docker/Unraid application for managing a physical board-game collection, locating and archiving rulebooks, and querying those documents with RAG.

## Non-negotiable domain rules

1. The BoardGameGeek `objectid` is the canonical external identifier when known.
2. The application must work without a BGG API token. BGG CSV import is a first-class path.
3. Never require authenticated scraping of BoardGameGeek.
4. Rulebook provenance must always be stored. A downloaded document is not trusted merely because its filename looks plausible.
5. Official publisher/localizer sources outrank community sources.
6. Community translations must be visibly marked as unofficial.
7. Do not write directly to Floppy's database. Integrate through its supported HTTP API.
8. Do not make Floppy the sole source of truth. The internal domain model must remain usable independently.
9. A board-game item may have zero, one or many documents.
10. RAG answers must retain document identity and page-level citation metadata.

## Persistent filesystem contract

- `/config`: database and application configuration.
- `/data/import`: inbound collection exports such as BGG CSV.
- `/data/manuals`: rulebooks and related documents.

Never store persistent state only inside the container filesystem.

## Rulebook confidence

Initial policy:

- official publisher: 100
- official localizer/distributor: 100
- official mirrored/uploaded source: 95
- known community source: 70
- generic discovery result: 40

Only high-confidence results may become unattended downloads. Lower-confidence results must enter a review queue.

## Provider architecture

Rulebook discovery must use isolated provider adapters. Do not put publisher-specific parsing logic in generic resolver code.

Every provider should return normalized candidates containing at least:

- source/provider
- URL
- language
- document type
- official/unofficial status
- confidence
- edition/version clues when available

## Development rules

- Keep changes small and testable.
- Add tests for import parsing, matching, provider normalization and destructive state changes.
- No feature may silently overwrite a user's manual or collection metadata.
- Imports must be idempotent.
- Preserve unknown CSV fields where practical instead of discarding potentially useful source data.
- Secrets belong in environment variables or runtime configuration, never in the repository.
- Prefer additive schema migrations.
- Treat network content as untrusted input.

## Git workflow

- Work on feature branches.
- Keep `main` deployable.
- Do not force-push `main`.
- Do not merge failing CI.
- Use conventional, scoped commit messages where practical.

## Initial milestones

P0. Foundation: Docker, health endpoint, CI/GHCR, Unraid template.
P1. BGG CSV importer and internal catalog.
P2. Floppy synchronization adapter.
P3. Physical-copy/barcode model and scanner workflow.
P4. Rulebook document model, storage and manual upload.
P5. Official rulebook provider framework and IT/EN resolver.
P6. Review queue and scheduled document update checks.
P7. RAG ingestion and page-cited Q&A.
