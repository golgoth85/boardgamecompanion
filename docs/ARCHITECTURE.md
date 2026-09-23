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

Candidate URLs are normalized only after validating a syntactically valid HTTP(S) hostname; internationalized DNS names use modern IDNA/UTS #46 processing rather than the legacy standard-library IDNA 2003 codec. Deterministic P5A checks reject localhost names, non-public literal IP addresses, IPv4-mapped IPv6 literals and ambiguous legacy numeric IPv4 forms without performing DNS resolution. Public-address classification is a project-owned security policy rather than a direct dependency on the runtime version of `ipaddress`; the policy explicitly covers non-global/special-use ranges (including newer IPv6 documentation space such as `3fff::/20`, IPv6 link-local `fe80::/10`, deprecated site-local `fec0::/10`, and deprecated IPv4 6to4 relay space `192.88.99.0/24`) while retaining current explicitly globally reachable IANA exceptions such as `2001:1::3/128`. The URL retained on the candidate is not aggressively rewritten. Deduplication uses a separate RFC-aware key that removes path dot-segments, decodes percent-encoded unreserved path characters and normalizes percent-escape hex case, while preserving the query string exactly so signed or otherwise query-sensitive URLs are not rewritten unnecessarily.

Metadata is snapshotted and canonicalized when RulebookCandidate is constructed. Mapping keys must be strings; recursively supported values are None, booleans, integers, finite floats, strings, mappings with string keys, and lists/tuples. Lists/tuples are stored as immutable tuples and mappings as read-only snapshots. Sets/frozensets, bytes, non-finite floats, non-string mapping keys, recursive containers and arbitrary objects are rejected. Ranking therefore never falls back to repr() and cannot be changed by later mutation of provider-owned metadata.

Canonical URL duplicates collapse to the highest-ranked candidate. Within equal source confidence, exact BGG identity is preferred first, then the requested language order (Italian before English by default), then publisher/localizer/mirror/community/generic source priority, followed by exact title/year clues. The score uses a mixed-radix hierarchy derived from the active language preference set, so no number of language preferences can overtake exact BGG identity. Language ranking preserves primary-language order while honoring explicit regional preferences within the same primary language (for example, en-GB before en-US when requested in that order). Exact score ties are resolved deterministically by canonical URL, normalized candidate identity and canonicalized metadata rather than provider/yield order. Tie reasons are idempotent, so equivalent candidate permutations produce the same selected candidate, score, reasons and final ordering. The score and matching reasons remain inspectable so later review-queue decisions are explainable.

Every candidate URL remains untrusted until the actual fetch. P5A deliberately performs only deterministic, network-free validation and canonicalization: it does not resolve DNS names, make HTTP requests or attempt to defend against runtime DNS changes. P5B performs those runtime checks in a separate guarded fetcher; provider-specific discovery remains outside both the resolver and fetcher.

## Guarded rulebook fetch (P5B)

`RulebookFetcher` accepts an already-normalized `RulebookCandidate` and keeps network I/O out of `RulebookResolver`. For each request target it reapplies the shared P5A HTTP(S) URL contract, resolves A/AAAA records, validates every returned address against the project-owned public-address policy, and rejects the entire target if any result is loopback, private, link-local, multicast, unspecified, reserved/special-use, IPv4-mapped IPv6, deprecated site-local, or otherwise outside the permitted public ranges. This policy is deliberately stable across the supported Python 3.12.x matrix and does not use `IPv4Address.is_global`/`IPv6Address.is_global` as the security boundary.

The validated address set is bound to the connection. Production transport opens a socket directly to one of the validated numeric IP addresses; it does not hand the hostname back to a resolver at connect time. HTTPS still uses the original hostname for SNI and certificate hostname validation, and the default TLS context must keep `check_hostname` enabled with `CERT_REQUIRED`. This closes the normal `resolve -> validate -> implicit re-resolve -> connect` DNS-rebinding/TOCTOU window. A monotonic absolute fetch deadline (300 seconds by default) is shared across the complete redirect chain and bounds DNS resolution, TCP connect, TLS, response headers and body transfer in addition to the per-operation connect/read timeouts. Production `getaddrinfo()` runs in a daemon worker and the caller waits only for the remaining deadline; unresolved OS calls are globally bounded to eight concurrent workers so repeated timeouts cannot cause unbounded resolver-thread growth. Deadline timers close the active connection while headers are being received and the active response while the body is being consumed, so a peer cannot evade the limit by slow-dripping bytes just below the socket read timeout. Tests use fake resolvers plus real local DNS/socket transport tests and do not require Internet DNS.

Redirects are handled manually. Raw `Location` values are rejected if they contain whitespace, control characters or backslashes before relative resolution can normalize them. Each accepted target is then resolved relative to the current URL, revalidated with the shared P5A URL rules, and subjected to a fresh DNS/address validation before any next request. Redirect count and loops are bounded, HTTPS-to-HTTP downgrade is rejected by default, credential-bearing or non-HTTP(S) locations are rejected, and request headers are rebuilt per hop from a fixed safe set. Authorization and Cookie headers are not accepted or propagated by this fetcher. Literal Unicode may remain in candidate/provenance URLs, but the HTTP request-target is UTF-8 percent-encoded at the transport boundary so valid P5A URLs cannot fail later with `UnicodeEncodeError`.

The download path uses explicit connect/read timeouts plus the absolute fetch deadline, requests `Accept-Encoding: identity`, rejects compressed responses, checks `Content-Length` when present, and also enforces the byte ceiling while streaming so absent, chunked, or misleading length headers cannot bypass the limit. The initial P5B content policy is PDF-only: declared PDF or generic binary MIME is accepted only when the body begins with the PDF signature; obvious HTML or other MIME mismatches and zero-byte bodies are rejected. HTTP informational responses other than the `100 Continue` behavior already handled by `http.client` are not consumed specially in P5B; for example, a standalone `103 Early Hints` is currently treated as a non-200 response rather than skipped to a later final response.

Validated bytes are hashed with SHA-256 while streaming to a temporary file under `/data/manuals`. Only after the size/content checks and hash complete is the file committed under its content hash with atomic no-replace publication: Linux uses `renameat2(RENAME_NOREPLACE)` when available, with a same-directory atomic hard-link fallback for runtimes/filesystems that do not support that flag. Partial files are removed on failure and an existing hash-named file is reused only after its size and hash are verified. Directory `fsync()` is best-effort: atomic no-overwrite namespace publication is guaranteed during normal operation, while final directory-entry durability across an abrupt power loss still depends on the underlying filesystem/FUSE implementation if directory fsync is unavailable. The structured fetch result retains the originating candidate, requested/final URLs, redirect chain, HTTP status, MIME, byte count, SHA-256, selected HTTP metadata, local path, and a structured failure code when the fetch fails. Failure results retain observed MIME/metadata/byte count/hash when available and preserve the rejected redirect target when it can be recorded without leaking credentials. Successful download does not upgrade source trust or imply approval.

P6 remains responsible for review queues, unattended-download policy, approval state and scheduled document update checks. P7 remains responsible for PDF parsing, ingestion, embeddings and page-cited RAG.

## Rulebook review queue (P6A)

P6A introduces a persistent, provider-independent review queue without exposing a public trust-escalation endpoint. Normalized `RulebookCandidate` values are submitted internally by trusted resolver/provider orchestration; HTTP clients may list queued items and record explicit approve/reject decisions, but they cannot manufacture an `official_publisher` or high-confidence candidate through the API.

The initial unattended policy is deliberately conservative. A candidate is policy-approved only when all of the following are true: it comes from an official publisher/localizer/mirror source, confidence is at least 95, its BGG ID exactly matches the target game, and its primary language is Italian or English. Any missing condition routes the candidate to `pending` review. Policy-approved candidates are persisted as `approved` with `decision_source=policy`; human decisions use `decision_source=user`. This keeps automated eligibility auditable without conflating it with manual approval.

Each normalized candidate is snapshotted as canonical JSON and keyed by SHA-256 together with its target game, making rediscovery idempotent while preserving provider, URL, language, document type, confidence, edition/version clues and metadata. Review transitions are atomic: `pending` may become `approved` or `rejected`; repeating the same decision is idempotent, while conflicting later decisions return a conflict instead of silently rewriting history. The web UI at `/reviews` consumes only the list/decision API. P6A does not schedule discovery, fetch approved items, or create/update `game_documents`; those execution concerns remain P6B.

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
