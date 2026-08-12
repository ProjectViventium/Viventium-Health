# Viventium-Health: vision, requirements, architecture, and learnings

**Status:** WHOOP-first API, minimal-click product onboarding, official export, readable manual-image
evidence, and parent-agent cognitive A/B implemented; final installed-browser acceptance in progress

**Owner:** Project Viventium

**Date:** 2026-07-26

## Vision

Viventium-Health gives Viventium a faithful sensory edge for health and body-related evidence. It
connects wearables, rings, watches, apps, sensors, official exports, and future devices without
forcing their data into a schema imagined in advance.

The component is deliberately humble. It collects what a source actually returned, when it returned
it, and enough transport provenance to retrieve and verify it later. Viventium—not the connector—
decides whether the evidence is relevant and how to reason about it. Any interpretation must remain
evidence-cited, non-diagnostic, uncertainty-aware, and separate from raw evidence and saved memory.

“All health things” is an extensibility direction, not a promise that one API exposes every device.
Cloud APIs, device-local stores, and exports are different acquisition lanes. Viventium-Health keeps
one stable archive/reader contract while adding the smallest source-specific adapter each lane needs.

## Core outcome metric

Evaluate every path as:

`Quality (intelligence, relevance, usefulness, alignment) + Performance (fast, smooth, reliable)`

For this component, quality begins with fidelity and honest provenance. A fast answer based on a
partial, stale, failed, or misinterpreted pull is a regression. Performance comes from daily bounded
polling, correction windows, pagination, compact listings, and chunked reads—not from deleting raw
detail or pre-normalizing it.

## Product requirements

1. Preserve the exact full body returned by each selected official endpoint and each page.
2. Pair every body with UTC fetch time, source/resource, request path/query, HTTP status, safe
   response headers, byte length, hash, retry attempt, and page number.
3. Never overwrite a capture. A later sync or correction is another piece of evidence.
4. Do not introduce a database, cross-vendor schema, health ontology, or score conversion.
5. Do not filter fields from a successful response. Scope selection happens at consent; archiving is
   full for every granted endpoint.
6. Distinguish healthy empty data from missing auth, missing scope, expired/revoked grant, rate
   limit, provider failure, invalid response, network failure, and incomplete pagination.
7. Pull daily with a bounded overlap so late device sync and vendor corrections are recaptured.
8. Keep credentials, tokens, archives, logs, and private QA outside source control with owner-only
   permissions.
9. Give LLMs a bounded read-only inventory and byte-paged raw read. No model-facing auth, pull,
   delete, arbitrary path, URL fetch, or shell tool.
10. Add a source by adding an adapter, not by changing the archive or inventing common health fields.
11. Work for WHOOP owners using iOS or Android because WHOOP's vendor app handles wristband-to-cloud
    sync; Viventium-Health reads the official cloud API from the host computer.
12. Treat health evidence as a private evidence surface, not saved memory, Feelings state, or an
    automatically injected prompt block.
13. Give a local administrator one visible connect action when an approved app is provisioned. When
    it is not, combine private self-managed credential save and authorization into one action rather
    than hiding the provider prerequisite.
14. On consent completion, start the all-history pull and install the daily correction schedule
    automatically; either failure remains visible and independently recoverable.
15. Report provider item counts for every documented API family, not archive page counts or a vague
    connected badge.
16. Preserve an official WHOOP ZIP and every contained file exactly, including Journal CSVs, under
    strict traversal/link/encryption/count/size/expansion limits.
17. Accept bounded PNG/JPEG app screenshots as separately labeled unstructured evidence and expose
    them through a read-only integrity-checked MCP image tool. Never call screenshots structured
    longitudinal measurements.
18. A persisted but no-longer-refreshable grant must remain an honest degraded state with old
    archive evidence readable and a fresh one-click authorization action visible. Reconnecting must
    not require a failed revoke, terminal work, deleting the archive, or entering client credentials
    again when the client is already configured.
19. Authorization recovery is a connector-owned status contract, not duplicated UI knowledge of
    pull-result strings. Both initial authorization failure and refresh-after-401 failure set the
    recovery flag. A configured token with no API run yet also keeps a one-click reconnect escape
    hatch so migrated or interrupted state cannot trap the owner.

## Architecture

```text
WHOOP wristband
  -> WHOOP iOS/Android app sync
  -> WHOOP official OAuth API v2
  -> Viventium-Health provider adapter
       auth + refresh + endpoint paging + bounded retry only
  -> append-only raw archive
       exact .body bytes + immutable .meta.json + run receipts
  -> provider-neutral read index
  -> CLI or read-only stdio MCP
  -> model-selected, on-demand Viventium reasoning
```

Separation of concerns:

- Provider adapter: how to ask a source for bytes.
- Archive: how to preserve bytes durably and prove integrity.
- Reader: how to enumerate and page preserved bytes safely.
- Scheduler: when to invoke a pull.
- Viventium agent/periphery: whether evidence matters and what it may mean.

## Why raw files, not a health database

The earlier wearable spike proposed normalized observations. The implementation requirement
supersedes that proposal for Viventium-Health. A schema would force premature decisions about what
counts as a day, session, sleep, recovery, HRV, score, unit, missing value, correction, or equivalent
metric across vendors. WHOOP alone is cycle-oriented and exposes vendor score states; Oura has a
different daily/session model. The exact source payload is the only safe canonical evidence.

Raw storage does not mean ungoverned prompt dumping. Complete bytes live on disk; the LLM lists
small metadata and reads bounded chunks only when relevant.

## WHOOP-first official contract

Current official facts verified on 2026-08-10:

- OAuth 2.0 authorization code flow is required for user data.
- Authorization URL: `https://api.prod.whoop.com/oauth/oauth2/auth`.
- Token URL: `https://api.prod.whoop.com/oauth/oauth2/token`.
- Redirect URI must exactly match one registered in the WHOOP Developer Dashboard.
- WHOOP requires an eight-character `state` value when the app generates it.
- Bearer tokens authorize API requests; invalid or expired tokens return HTTP 401.
- `offline` is required to receive a refresh token.
- Refresh invalidates the previous access and refresh tokens, so refresh and persistence must be
  serialized and atomic.
- Official read scopes are cycles, recovery, sleep, workout, profile, and body measurement.
- WHOOP instructs apps to limit requested scopes to those actually used.
- Collection `start` and `end` query parameters are optional; omitting `start` applies no minimum
  time filter, while a supplied `end` fixes the upper capture boundary.
- Cycle, recovery, sleep, and workout collections use `records`, `next_token`, and request
  `nextToken`; an absent or empty token completes pagination.
- Default published limits are 100 requests/minute and 10,000/day. HTTP 429 and rate-limit headers
  make throttling observable, and `X-RateLimit-Reset` is seconds until the active window resets.
- Development apps are limited to 10 members before WHOOP approval; there is no ordinary public
  synthetic user-data sandbox.
- WHOOP's official data export includes CSV files such as physiological cycles, sleeps, workouts,
  and Journal entries.
- The app's 0–3 Stress Monitor is not documented as a developer API resource. It remains an explicit
  manual-image lane rather than a scraped/private API dependency.

Official sources:

- [Getting started and scope guidance](https://developer.whoop.com/docs/developing/getting-started/)
- [OAuth, rotation, state, revoke](https://developer.whoop.com/docs/developing/oauth/)
- [Refresh request format](https://developer.whoop.com/docs/tutorials/refresh-token-javascript)
- [API paths and scopes](https://developer.whoop.com/api/)
- [OpenAPI document](https://api.prod.whoop.com/developer/doc/openapi.json)
- [Pagination](https://developer.whoop.com/docs/developing/pagination/)
- [Rate limiting](https://developer.whoop.com/docs/developing/rate-limiting/)
- [App approval and 10-member development limit](https://developer.whoop.com/docs/developing/app-approval/)
- [Mobile export](https://support.whoop.com/s/article/How-to-Export-Your-Data)

### Scope decision

The product card promises visible coverage across all six documented read families and therefore
requests cycles, recovery, sleep, workout, profile, body measurement, and offline. Each scope backs
a displayed, archived resource; this remains compatible with WHOOP's guidance to request only scopes
the app actually uses. A CLI operator can configure a narrower official scope set without a code
change, and status calls out each missing grant rather than pretending the family is empty.

### Polling decision

Start with one daily pull over the previous three days. This catches common late sync and corrections
with tiny request volume. Initial connection may request all available history exposed through the
six official v2 read resources: collection requests omit the minimum-time filter, retain a fixed
current end boundary, and follow pagination until provider completion or the explicit 1,000-page
per-resource safety cap. Every run captures singleton resources only when their scopes are granted.
Long pulls proactively pause when the current minute budget is empty, use a one-minute fallback for
headerless 429 responses, and can rotate an expired token again on a later page.

Webhooks are deferred because they add a public HTTPS receiver, signature verification, duplicate
handling, and reconciliation while still omitting cycle/body events. Daily overlap is the smallest
reliable no-extra-cost path for the user's need.

## Integration landscape

| Source | Official continuous lane | Mobile requirement | Viventium-Health direction |
| --- | --- | --- | --- |
| WHOOP | OAuth API v2, optional webhooks | WHOOP app syncs device on iOS/Android | First adapter; daily cloud pull |
| Oura Ring | OAuth API v2, webhooks, synthetic sandbox | Oura app syncs ring on iOS/Android | Next direct cloud adapter |
| Fitbit / Google | Google Health API; legacy Fitbit API retirement underway | Vendor/platform sync | Future direct cloud adapter |
| Polar | AccessLink OAuth, REST, webhooks | Polar app/device sync | Strong future direct adapter |
| Withings | OAuth API and notifications | Vendor app/device sync | Strong future direct adapter |
| Ultrahuman | Personal-token and partner OAuth APIs | Vendor app sync | Future direct adapter after terms review |
| Garmin | Garmin Health API after program approval/licensing | Vendor app sync | Gated future adapter |
| Apple Watch / Apple Health | HealthKit is device-local, no general owner cloud REST API | Native iPhone app required | Official export first; native bridge only if earned |
| Android Health Connect | Device-local store, not a backend API | Native Android app required | Native bridge only if earned |
| Samsung Health | Android local SDK/partner registration | Native Android app required | Specialized future bridge |
| RingConn | No verified public owner cloud API | Platform sharing/export | Official export or platform bridge |
| Eight Sleep | No verified public developer API | Vendor app/cloud | Official export/partnership only |
| Amazfit / Zepp | No verified self-service historical health cloud API | Platform sharing/export | Official export or platform bridge |

This inventory is an acquisition map, not a normalized-data promise. Future adapters preserve each
source independently under the same raw archive contract.

## Options evaluated

### Direct official vendor APIs — selected

Best provenance, no aggregator fee, cross-platform for cloud-backed devices, and stable enough to
support daily polling. Cost is one adapter per vendor.

### Official exports — implemented WHOOP fallback

Fast and token-free for Journal coverage, recovery from an unavailable developer app, and future
devices without cloud APIs. Manual exports are not a dependable daily connector. The implemented
WHOOP importer preserves the ZIP and every entry byte-for-byte, recognizes only stable official
filename families for discovery, and keeps unknown future files instead of discarding them.

### Manual image evidence — implemented app-only fallback

PNG/JPEG screenshots cover visible WHOOP app context that the public API and export do not expose,
including Stress Monitor. They are private, exact, integrity-checked, and model-readable through MCP
image content, but remain unstructured/manual. There is no OCR-derived canonical measurement and no
claim of automated longitudinal completeness.

### Apple HealthKit / Health Connect — later

They increase device breadth but require native iOS/Android apps, per-type permissions, background
execution, store review, and device QA. They are not needed for WHOOP or Oura cloud access.

### Commercial aggregators — rejected for v1

They offer breadth but add recurring cost, another health-data processor, vendor lock-in, and their
own normalization. Previously reviewed public entry prices were material relative to a one-owner
connector. Re-evaluate only after several direct adapters prove adapter maintenance is the real
bottleneck.

### Self-hosted Open Wearables — lab candidate, not adopted

Promising breadth and MCP work, but its PostgreSQL/Redis/application stack is the opposite of this
module's intentionally tiny raw archive. Device-local stores would still need mobile SDKs.

### Community WHOOP MCP — reference only

The audited `AshwanthramKL/whoop-mcp` v0.8.5 proved a local read-only MCP is feasible and had 198
passing tests after an undeclared Parquet dependency was added. It was not adopted because its
stdio-only fit was incomplete for prior Viventium assumptions, scopes were hard-coded broad,
published dependencies omitted PyArrow, its full source pin selected a PyArrow version with a known
2026 advisory, live health checks contacted PyPI despite privacy wording, arbitrary export paths
were exposed, exported files lacked enforced owner-only permissions, and handshake versioning
reported the SDK rather than connector version. Viventium-Health keeps the useful tests and avoids
the dependency/analysis/export surface entirely.

### Scraping/private APIs — rejected

Browser sessions and reverse-engineered endpoints are brittle, credential-heavy, difficult to
reconcile, and may violate terms. They remain isolated research possibilities only when no official
lane exists and the user explicitly accepts the risk.

## Privacy and security

Health payloads are sensitive private evidence even when a vendor calls them wellness data.

- OAuth client secrets and tokens are stored separately from archives with owner-only permissions.
- Authorization headers and token responses are never archived or logged.
- The public repository contains only synthetic fixtures and sanitized counts/hashes.
- Request metadata stores path and non-secret query parameters, never full headers.
- MCP record reads are by opaque generated ID, not arbitrary path.
- MCP image reads accept only archived PNG/JPEG records, enforce a 10 MiB cap, verify declared
  length and SHA-256, and omit image bytes from structured metadata.
- Browser-to-local-API setup, callbacks, export ZIPs, and screenshots are administrator-only and
  available only when the local-subscription and health feature gates are active.
- The host-wide MCP reader declares the reusable `local_owner` audience and the common MCP loading
  boundary denies it before discovery/process startup for ordinary accounts or missing request
  identity. Disabling health omits the MCP server entirely.
- Client secrets, OAuth callback codes/state, ZIP bytes, screenshot bytes, original filenames,
  archive IDs, and private paths never enter argv, environment variables, logs, or product status.
- ZIP import rejects traversal, backslashes, NULs, links/non-regular entries, encryption, excessive
  entries, per-entry size excess, and aggregate expansion before archiving file contents.
- Exact repeat export ZIPs are detected by SHA-256 and reuse the existing immutable run instead of
  consuming unbounded duplicate storage.
- Pending OAuth state expires after ten minutes, grant scopes are never inferred from requested
  scopes, and one owner-checked onboarding lock serializes callback exchange, backfill, and schedule
  setup across browser/helper retries.
- Raw payload text is untrusted LLM evidence and cannot instruct the connector.
- Disconnect/revoke and archive deletion are explicit operator actions; v1 does not silently expire
  or delete private evidence.
- The connector never writes raw health bytes to Viventium saved memory, Feelings, telemetry, or
  public QA. A bounded record chunk explicitly read for an agent request necessarily enters that
  request's tool context and may inherit the host's ordinary conversation retention; it is not a
  second canonical health store.

Owner-only file permissions reduce accidental local exposure but are not full disk encryption. Full
disk encryption and host account security remain deployment prerequisites. A future multi-user or
server deployment needs stronger secret storage and tenant isolation before adoption.

Threat model: an ordinary LibreChat account must not read or mutate host-wide health state; a
malicious callback must not bypass OAuth state/redirect validation; an uploaded archive/image must
not escape the health root or exhaust unbounded resources; an untrusted provider body/image must not
gain tool authority; logs/status must not become a covert secret or identity channel. Controls are
admin and feature gates, exact OAuth validation, stdin-only secret-bearing transport, fixed command
arguments with no shell, bounded uploads/output/timeouts, archive-generated IDs, owner-only storage,
hash verification, append-only records, and a read-only MCP surface. The accepted deployment remains
one local host owner, not per-chat-user health tenancy.

## LLM use

The model gets four simple capabilities:

1. list capture runs;
2. list response records;
3. read a record in bounded byte chunks.
4. read a bounded verified PNG/JPEG record as MCP image content.

The tools describe sources, timestamps, HTTP truth, hashes, byte size, and paging. They do not say
what “good recovery,” “poor sleep,” or any health condition means. The agent can inspect raw evidence
when the user's request makes it useful and cite the source/resource/fetch time in its answer.

The reader must make operational ambiguity impossible:

- `records: []` from a successful 200 body is provider evidence;
- no matching archive is an empty local inventory;
- a failed/incomplete run is a failure, not “WHOOP has no data”;
- a truncated MCP chunk says exactly how to request the next bytes.

## Natural use cases

- Managed first connection: local administrator clicks Connect, consents at WHOOP, and Viventium
  automatically starts full-history import plus daily corrections.
- Self-managed first connection: administrator creates a private WHOOP developer app, enters its
  credentials once, and uses the combined Save and connect action; the 10-member provider cap is
  stated visibly.
- Export fallback: owner imports one official ZIP; the exact bundle, known CSV families including
  Journal, and unknown files remain discoverable without claiming continuous sync; selecting the
  same exact ZIP again reports it already imported without duplicating the archive.
- App-only evidence: owner adds a PNG/JPEG WHOOP screenshot in one picker action; it is counted and
  Viventium can inspect it as image evidence without converting it to an API metric.
- Daily pool: scheduler pulls the previous three days and appends every response/page.
- Late sync: device data appears after the first pull and is captured by a later overlapping run.
- Correction: vendor changes a sleep/recovery/workout; both old and new raw responses survive.
- LLM planning: Viventium lists recent records, reads relevant raw bytes, and answers with source
  and time without diagnosing.
- Empty state: no captures returns an honest empty archive with setup guidance.
- Missing/revoked auth: pull fails explicitly and existing archives remain readable.
- Rate limit/provider outage: failed responses are retained, retries are bounded, run is incomplete.
- Restart: rotating refresh token and archive index work in a new process.
- Disconnect: upstream grant is revoked without deleting historical evidence unless the user asks.
- Delete: an explicit scoped deletion can be designed later; no automatic retention is assumed.

## QA and acceptance

The durable cases live in `qa/cases.md`. The critical evidence chain is:

`requirement -> operator/LLM use case -> QA case -> exact expected result -> actual evidence -> gap`

Automated acceptance must prove exact bytes, append-only behavior, all-page collection pulls,
all-six/default and narrower scope selection, retry/failure truth, token rotation, locking, owner
permissions, export/image input hardening, read paging/image content, MCP protocol behavior,
scheduler generation, product API/UI gates, package installation, and public safety.

The live official contract test proves only that source paths still exist and unauthenticated access
fails closed. It is not owner-data acceptance.

Real owner acceptance requires:

1. actual WHOOP developer app and exact redirect URI;
2. explicit owner OAuth consent;
3. wristband -> mobile app -> WHOOP cloud sync;
4. backfill and a later daily overlapping pull;
5. a real late update/correction captured as a new immutable response;
6. access-token expiry/rotating refresh across restart;
7. revoke and clear auth state;
8. read-only LLM listing and full chunked read;
9. a cognitive A/B showing material usefulness without unsupported medical meaning.

Anything before those steps is `PARTIAL`, never “real WHOOP complete.”

Owner acceptance progress on 2026-07-27:

- steps 1–4 passed with all six read scopes plus offline refresh, two complete manual pulls, and a
  complete real LaunchAgent catch-up pull;
- step 6 passed: a live refresh rotated both tokens, persisted them owner-only, and a later process
  completed another pull;
- step 8 passed at the component boundary: all six records were read completely through the
  read-only MCP and their bytes matched archive hashes;
- step 5 remains open until WHOOP actually changes or late-syncs a record;
- step 7 remains open because revocation would intentionally interrupt the now-running daily pool;
- step 9 passed: after a real Viventium runtime restart, the main agent used bounded Health MCP
  reads to produce a source- and capture-time-cited, uncertainty-aware, non-diagnostic planning
  answer; the matched no-tool control correctly declined to infer current recovery.

The public evidence records only scopes, counts, statuses, integrity results, and permission modes.
It never records account identity, device identifiers, OAuth values, payloads, measurements, or
owner-specific filesystem paths.

## Learnings to preserve

- Cloud APIs make WHOOP/Oura independent of the owner's phone OS, but not independent of vendor app
  sync.
- Complete storage and bounded context are compatible: store everything, retrieve incrementally.
- A connector can stay schema-agnostic while parsing documented pagination control fields.
- Rotating refresh tokens make a single pull lock a correctness requirement, not optional polish.
- Poll overlap is the simplest correction mechanism; deduplication is not required when history is
  intentionally append-only.
- File timestamps alone are not evidence. Put an explicit fetched-at timestamp and hash in immutable
  metadata.
- Vendor scores are source facts, not cross-vendor or clinical truth.
- Device-local breadth is a separate mobile product, not a hidden requirement for cloud gadgets.
- Community connectors are useful design/test sources but should not be adopted without transport,
  scope, privacy, packaging, dependency, and real-account validation.
- No-cost means no paid intermediary or hosted service; it does not remove the one-time need to
  create a vendor developer app or maintain a tiny first-party connector.

## Future additions

Add Oura next by implementing only its OAuth, endpoint list, webhook/poll controls, and pagination.
The raw archive, reader, MCP, scheduler, permissions, and QA framework must remain unchanged.

Generalize the implemented exact WHOOP export contract only when another provider materially
broadens supported devices. Preserve source bytes and import metadata; do not parse every export
into a common schema.

Add native iOS/Android bridges only after explicit device demand proves that official cloud APIs and
exports are insufficient. That is a separate product surface with separate permissions and QA.
