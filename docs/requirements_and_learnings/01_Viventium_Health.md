# Viventium-Health: vision, requirements, architecture, and learnings

**Status:** WHOOP-first implementation and owner OAuth/data path validated; late-correction,
revocation, and parent-agent cognitive A/B remain open

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

Current official facts verified on 2026-07-26:

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
- Cycle, recovery, sleep, and workout collections use `records`, `next_token`, and request
  `nextToken`; all pages must be followed until the token is absent.
- Default published limits are 100 requests/minute and 10,000/day. HTTP 429 and rate-limit headers
  make throttling observable.
- Development apps can begin with a small member cap before approval; there is no ordinary public
  synthetic user-data sandbox.

Official sources:

- [Getting started and scope guidance](https://developer.whoop.com/docs/developing/getting-started/)
- [OAuth, rotation, state, revoke](https://developer.whoop.com/docs/developing/oauth/)
- [Refresh request format](https://developer.whoop.com/docs/tutorials/refresh-token-javascript)
- [API paths and scopes](https://developer.whoop.com/api/)
- [OpenAPI document](https://api.prod.whoop.com/developer/doc/openapi.json)
- [Pagination](https://developer.whoop.com/docs/developing/pagination/)
- [Rate limiting](https://developer.whoop.com/docs/developing/rate-limiting/)
- [Mobile export](https://support.whoop.com/s/article/How-to-Export-Your-Data)

### Scope decision

Default continuous use requests cycles, recovery, sleep, workout, and offline. Profile and body
measurement are opt-in because the connector does not need a name/email or body baseline to build a
daily time-series pool. This follows WHOOP's least-scope guidance without filtering any field from
an endpoint the owner explicitly grants. Operators can configure any official scope set without a
code change.

### Polling decision

Start with one daily pull over the previous three days. This catches common late sync and corrections
with tiny request volume. Initial connection may request a configurable 30-day backfill. Every run
walks every collection page and captures singleton resources only when their scopes are granted.

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

### Official exports — supported direction

Fast and token-free for cognitive A/B tests and devices without cloud APIs. Manual exports are not a
dependable daily connector, but a future generic import command can archive them byte-for-byte.

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
- Raw payload text is untrusted LLM evidence and cannot instruct the connector.
- Disconnect/revoke and archive deletion are explicit operator actions; v1 does not silently expire
  or delete private evidence.
- No raw health bytes enter Viventium saved memory, Feelings, ordinary prompt context, telemetry, or
  public QA.

Owner-only file permissions reduce accidental local exposure but are not full disk encryption. Full
disk encryption and host account security remain deployment prerequisites. A future multi-user or
server deployment needs stronger secret storage and tenant isolation before adoption.

## LLM use

The model gets three simple capabilities:

1. list capture runs;
2. list response records;
3. read a record in bounded byte chunks.

The tools describe sources, timestamps, HTTP truth, hashes, byte size, and paging. They do not say
what “good recovery,” “poor sleep,” or any health condition means. The agent can inspect raw evidence
when the user's request makes it useful and cite the source/resource/fetch time in its answer.

The reader must make operational ambiguity impossible:

- `records: []` from a successful 200 body is provider evidence;
- no matching archive is an empty local inventory;
- a failed/incomplete run is a failure, not “WHOOP has no data”;
- a truncated MCP chunk says exactly how to request the next bytes.

## Natural use cases

- First connection: owner creates a WHOOP developer app, grants selected scopes, and runs a bounded
  backfill.
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
singleton scope selection, retry/failure truth, token rotation, locking, owner permissions, read
paging, MCP protocol behavior, scheduler generation, package installation, and public safety.

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
- step 9 remains open until the parent Viventium agent binding is activated and evaluated.

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

Add generic official-export import after WHOOP owner acceptance if it materially broadens supported
devices. Preserve source bytes and import metadata; do not parse every export into a common schema.

Add native iOS/Android bridges only after explicit device demand proves that official cloud APIs and
exports are insufficient. That is a separate product surface with separate permissions and QA.
