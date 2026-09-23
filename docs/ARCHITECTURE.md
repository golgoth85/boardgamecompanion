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
- type: rulebook, reference, faq, errata, campaign_book, scenario_book, player_aid, other
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

Provider results are normalized before ranking. Every candidate carries the provider identity, source class, HTTP(S) URL, language, document type, official/unofficial status, confidence and optional BGG/title/year/version/edition clues. Source classes use the initial confidence policy from `AGENTS.md`: publisher/localizer 100, official mirror 95, known community 70 and generic discovery 40. A provider may lower confidence within its source class, but it cannot raise confidence above that class ceiling; provider-supplied confidence therefore cannot promote community or generic material above the trust class assigned to it.

The resolver is failure-isolated: one provider cannot abort results from another provider, and candidates with an explicit conflicting BGG ID are rejected. BGG IDs accept positive integral values (including numeric strings) but reject booleans and non-integral numerics rather than truncating them. The official trust attribute must be an actual Python boolean and must agree with the source class; strings, integers and generic truthy/falsy values are rejected.

Candidate URLs are normalized only after validating a syntactically valid HTTP(S) hostname; internationalized DNS names use modern IDNA/UTS #46 processing rather than the legacy standard-library IDNA 2003 codec. Deterministic P5A checks reject localhost names, non-public literal IP addresses, IPv4-mapped IPv6 literals and ambiguous legacy numeric IPv4 forms without performing DNS resolution. The URL retained on the candidate is not aggressively rewritten. Deduplication uses a separate RFC-aware key that removes path dot-segments, decodes percent-encoded unreserved path characters and normalizes percent-escape hex case, while preserving the query string exactly so signed or otherwise query-sensitive URLs are not rewritten unnecessarily.

Metadata is snapshotted and canonicalized when RulebookCandidate is constructed. Mapping keys must be strings; recursively supported values are None, booleans, integers, finite floats, strings, mappings with string keys, and lists/tuples. Lists/tuples are stored as immutable tuples and mappings as read-only snapshots. Sets/frozensets, bytes, non-finite floats, non-string mapping keys, recursive containers and arbitrary objects are rejected. Ranking therefore never falls back to repr() and cannot be changed by later mutation of provider-owned metadata.

Canonical URL duplicates collapse to the highest-ranked candidate. Within equal source confidence, exact BGG identity is preferred first, then the requested language order (Italian before English by default), then publisher/localizer/mirror/community/generic source priority, followed by exact title/year clues. The score uses a mixed-radix hierarchy derived from the active language preference set, so no number of language preferences can overtake exact BGG identity. Language ranking preserves primary-language order while honoring explicit regional preferences within the same primary language (for example, en-GB before en-US when requested in that order). Exact score ties are resolved deterministically by canonical URL, normalized candidate identity and canonicalized metadata rather than provider/yield order. Tie reasons are idempotent, so equivalent candidate permutations produce the same selected candidate, score, reasons and final ordering. The score and matching reasons remain inspectable so later review-queue decisions are explainable.

Every candidate URL remains untrusted until the actual fetch. P5A deliberately performs only deterministic, network-free validation and canonicalization: it does not resolve DNS names, make HTTP requests or attempt to defend against runtime DNS changes. P5B must resolve A and AAAA records at fetch time, validate every resolved address against the public-address policy, repeat resolution/address validation for every redirect target, and bind the validated resolution to the connection strongly enough to defend against DNS rebinding and DNS-resolution/connect TOCTOU. Provider-specific HTTP discovery and guarded download/review behavior remain separate subphases.

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
