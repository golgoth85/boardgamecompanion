# Pre-UI-redesign readiness

This document freezes the backend and workflow contracts that the next UI redesign
should treat as stable. It is intentionally about behavior and information
architecture boundaries, not visual layout.

## Core workflow status

The following capabilities are considered implemented and must remain available
through the redesign:

- local catalog and physical-copy management;
- camera-first barcode lookup/import with manual fallback;
- optional direct BGG XML API2 metadata enrichment and cached cover/description;
- manual PDF upload;
- known-source rulebook discovery with trust/review policy;
- scheduled guarded rulebook updates;
- page-preserving PDF ingest, deterministic chunking and embedding currentness;
- game-scoped RAG with server-owned provenance and exact page citations;
- Google-assisted manual rulebook search as a human-reviewed fallback.

The Gemini rate-limit acceptance check and Docker restart-policy cleanup are
explicitly outside this readiness gate.

## Rulebook search interaction contract

A game detail page exposes exactly one primary rulebook-search action.

1. First click runs the existing known-source discovery pipeline, preferring
   Italian then English and preserving the current trust/review policy.
2. If that completed run finds candidates, the same control remains a
   known-source refresh action.
3. If providers fail, the same control remains a known-source retry action.
4. Only after a completed run returns zero candidates and zero provider failures
   does the same control switch to **Cerca PDF su Google**.
5. The Google click opens the already-hardened literal-title search in a new
   tab. It never imports, downloads, trusts or approves a document.
6. A manually downloaded PDF still enters through **+ Aggiungi PDF** and the
   normal archive/index/provenance path.

The clean-miss state is derived from persisted discovery state, so a reload does
not re-expose Google before the known-source attempt has completed.

## Backend trust boundaries the redesign must not weaken

- The browser never assigns document trust.
- Provider candidates continue through the existing resolver/review policy.
- RAG evidence identity, document/page metadata and citation provenance remain
  server-owned.
- Model-provided quotes are accepted only under the exact/unique whitespace-only
  canonicalization policy and are rendered as exact source substrings.
- Provider/model currentness checks remain mandatory.
- No implicit provider fallback is introduced.
- Barcode mappings remain local `barcode -> OwnedCopy -> BoardGame`.
- BGG metadata is cacheable enrichment, not a replacement for local catalog
  identity or physical-copy data.

## Acceptance before visual redesign

The pre-redesign cleanup uses three complementary acceptance layers:

- exact-head Python and Chromium CI for the consolidated interaction changes;
- live known-source discovery against a stratified four-base/four-expansion
  sample through NAS Control;
- live real-collection checks for at least one base game and one expansion across
  archive/index/RAG paths, reusing existing bounded NAS Control operations.

The visual redesign may radically reorganize navigation and presentation after
these gates, but should avoid changing the stable API/domain contracts in the
same change set.
