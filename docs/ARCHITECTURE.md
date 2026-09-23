# Architecture

## Principles

BoardGameCompanion separates the user's collection from external catalogs and integrations. BGG, Floppy, publishers and RAG services are adapters around an internal domain model.

## Core domain

### BoardGame

Represents the conceptual game or expansion.

Suggested fields:

- internal UUID
- BGG object ID
- title / original title
- year
- item type: standalone or expansion
- player count
- play time
- community rating/rank/weight
- source metadata snapshot

### OwnedCopy

Represents the user's physical copy.

Suggested fields:

- board-game ID
- barcode/EAN/UPC
- language
- edition/version
- publisher/localizer
- acquisition date/source/price
- inventory location
- quantity
- private notes

This distinction is intentional: one BoardGame can have multiple physical copies or editions.

### Document

Represents a manual or related rules document.

Suggested fields:

- board-game ID
- type: rulebook, rules-reference, FAQ, errata, campaign-book, scenario-book, player-aid, expansion-rules
- language
- edition/version
- official flag
- provider/source
- original URL
- local path
- SHA-256
- retrieval timestamp
- confidence
- RAG indexing status

### ExternalLink

Maps internal objects to external systems such as Floppy.

## Import

BGG CSV must be accepted without BGG API access. Imports are idempotent and keyed primarily by BGG `objectid`.

The original row should be retained as source metadata so future versions can make use of fields not yet modeled.

## Database migrations

Schema changes are applied through ordered, versioned migrations recorded in `schema_migrations`.
A pre-migration database is adopted by the baseline migration without rewriting existing rows.
New phases must add an additive migration instead of extending an unversioned startup schema.

## Rulebook resolver

The resolver orchestrates provider adapters and ranks normalized candidates. Provider-specific HTML/API parsing remains inside adapters.

Resolution order should prefer:

1. official publisher
2. official localizer
3. trusted official mirror
4. known community repository
5. controlled generic discovery

A title match alone is insufficient for unattended download. Matching may also use year, BGG ID, publisher, expansion/base-game identity, language and edition clues.

## RAG

Documents are indexed per game while retaining language, document type, version and page identity.

Retrieval priority should prefer current official documents in the user's language, then official English documentation, then explicitly marked community material.

Answers should cite document and page and should not silently merge contradictory versions.

## External services

Optional integrations:

- Floppy: catalog/collection synchronization over HTTP API.
- Ollama: local generation/embedding endpoint.
- Qdrant: vector store.

BoardGameCompanion must degrade gracefully when optional services are unavailable.
