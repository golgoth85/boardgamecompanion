# Publisher-first Italian rulebook discovery

BoardGameCompanion resolves a candidate publisher/localizer **before** touching a
remote rulebook site. The edition's `version_publishers` values are retained
separately from the publishers returned by BGG XML API2. The edition values are
*selection hints*, not a claim that a website or PDF is verified.

## The generic path

1. `PublisherSiteResolver` matches the publisher/localizer's complete
   normalized name against a curated, exact-alias publisher website directory.
   The directory is in
   `src/boardgamecompanion/official_site_discovery.py`.
   It lists trusted HTTPS origin(s), official search URL template(s), product
   path markers and any narrowly approved external download host. It contains
   **no game-specific download URL**. Unknown or ambiguous websites cannot
   become official merely because an internet search returned them.
2. Each site is handled by a separate `PublisherSiteProvider` instance using
   the same generic search algorithm, so failure of one publisher cannot
   poison another. The provider consults `robots.txt` on the actual host,
   respects disallow rules, searches a capped number of pages, and follows
   only product links on its fixed HTTPS origin. The generic client uses an
   explicit BoardGameCompanion user-agent, **without browser impersonation**.
3. Both exact title / verified alias and the canonical BGG object ID are used
   as identity evidence, not just a similar filename. The official site may
   link a PDF through an explicitly allowed CDN or hosting service, but the
   source product/download page is retained in candidate provenance. A site
   mentioning both base and expansion BGG IDs is not exact BGG evidence.
4. Confidence 100 (unattended-eligible) requires a verified BGG identity plus
   either **exact page BGG ID and exact page title**, or **exact BGG-verified
   title alias and a BGG-verified publisher**. An edition publisher obtained
   only from a collection CSV cannot certify an automatic download.
   Confidence 90 / no asserted BGG ID instead enters human review. An Italian
   storefront alone cannot prove that an ambiguously labelled document is
   Italian; it is marked pending unless language evidence is explicit.
5. The existing review queue, guarded PDF fetcher, archived document provenance
   and RAG indexing are unchanged. The discovery HTTP client reads *small HTML
   pages only*; it does not download PDF bodies. IT precedes EN in the resolver
   and the automatic updater retains its English-fallback policy.

## Extending coverage

Add a publisher/localizer to the curated `VERIFIED_PUBLISHER_SITES` directory
only after independently verifying its official origin and exact aliases.
Configure search URL templates and, if applicable, a publisher-linked PDF
hosting origin; **no Python provider adapter is needed**. An unknown publisher
currently produces no auto-approved candidate until its origin is verified.
This is intentional: searching the open internet for an unverified publisher
website and treating the top search hit as official would undermine the trust
gate. If a site needs authenticated access, returns HTTP 403/429, prohibits
crawling, or exposes no public rulebook, do not bypass the restriction.
Use human review/manual upload when appropriate.

The previous production sample (#136 in `golgoth85/nas-control`) found 0/6
official Italian candidates. This change is a new source-level implementation,
**not proof of a repaired NAS runtime**. CI mocks verify matching and safety
properties; a later explicitly authorized runtime smoke must report, separately,
publisher resolution, candidate discovery, guarded PDF fetch, and IT/EN
fallback for four base games plus four expansions. Do not mark the operation
complete until live evidence verifies those distinct stages.
