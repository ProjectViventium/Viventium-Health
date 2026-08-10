# Spec: Viventium-Health WHOOP-first raw evidence bridge

## Status

Accepted for implementation on 2026-07-26 by the user's explicit request to build the isolated
module after documenting the vision and requirements.

## Assumptions

1. Viventium-Health runs on the computer hosting Viventium, not on the wearable or phone.
2. WHOOP's own iOS or Android app remains responsible for syncing the wristband to WHOOP's cloud.
3. A cloud connector therefore serves both iOS and Android owners without a Viventium mobile app.
4. “Raw + full” means the exact bytes returned by every selected official endpoint and every page,
   not a hand-picked or normalized subset of fields.
5. V1 uses a direct daily pull and no webhooks. A bounded three-day overlap captures late updates
   and corrections without requiring a public callback service.
6. Private runtime state is outside the git checkout. No health record or credential is a fixture.
7. The public repository is source-available under the Project Viventium licensing posture.

## Objective

Build a small, dependable module that:

- authorizes one WHOOP owner through the official OAuth 2.0 flow;
- pulls every configured official WHOOP resource and every collection page;
- stores each HTTP response body byte-for-byte with capture time, request facts, status, selected
  response headers, length, and SHA-256 in a separate immutable metadata sidecar;
- repeats a correction window daily without overwriting prior captures;
- exposes a provider-neutral, read-only, paged CLI and stdio MCP surface for LLM consumption;
- can add Oura or another source by adding an adapter, without changing the archive or reader;
- requires no database, hosted service, aggregator, subscription, or non-standard runtime library.

## Non-goals

- health recommendations, diagnoses, alerts, thresholds, baselines, trends, correlations, or scores;
- a normalized observation model or cross-vendor field mapping;
- saved-memory writes, RAG ingestion, embeddings, dashboards, mobile apps, or browser scraping;
- a public HTTP service, webhooks, multi-user tenancy, or commercial aggregator;
- pretending an API pull can retrieve data that the wearable has not yet synced upstream.

## Tech stack

- Python 3.10 or newer
- Python standard library only at runtime
- `unittest` for deterministic tests
- official WHOOP OAuth 2.0 and REST API v2
- MCP stdio protocol `2025-06-18`, implemented as newline-delimited UTF-8 JSON-RPC

No third-party runtime dependency is accepted for v1. This avoids the packaging and vulnerable
Parquet dependency found in the audited community WHOOP connector while keeping the module small.

## Commands

```bash
# Development
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src tests

# Operator flow (implemented by this spec)
viventium-health whoop configure
viventium-health whoop connect
viventium-health whoop disconnect
viventium-health pull whoop --all-history
viventium-health pull whoop --lookback-days 3
viventium-health runs --provider whoop --limit 10
viventium-health records --provider whoop --limit 50
viventium-health read <record-id> --offset 0 --max-bytes 65536
viventium-health mcp
viventium-health schedule install --provider whoop --hour 6 --minute 0
viventium-health schedule status
viventium-health schedule uninstall
```

`configure`, `connect`, and schedule mutation are explicit operator actions. The MCP server exposes
only `health_list_runs`, `health_list_records`, and `health_read_record`. `disconnect` revokes the
grant upstream before removing the local token and never deletes historical evidence.

## Project structure

```text
src/viventium_health/
  archive.py       exact-byte append-only archive and read index
  auth.py          owner-only OAuth client/token files
  whoop.py         official WHOOP URLs, resources, OAuth, paging, retry
  mcp.py           read-only stdio JSON-RPC/MCP adapter
  schedule.py      macOS user LaunchAgent generation and status
  cli.py           explicit operator commands
  __main__.py      python -m entrypoint
tests/             unit and localhost integration tests
docs/              one feature source of truth, specification, decisions
qa/                durable cases and dated public-safe run evidence
```

## Interfaces

### Provider adapter

An adapter supplies only request mechanics:

```python
class ProviderAdapter(Protocol):
    name: str
    def pull(self, archive: RawArchive, start: datetime, end: datetime) -> PullResult: ...
```

The common layer never imports WHOOP response models. A provider may parse only protocol control
fields required to continue transport, such as WHOOP's documented `next_token`.

### Raw record

Every response creates two files in one immutable run directory:

```text
<record-id>.body.json   # exact bytes returned by the provider
<record-id>.meta.json   # capture facts; never contains an auth header or token
```

If a response is not JSON, the body extension is `.body.bin`. Metadata schema:

```json
{
  "schema_version": 1,
  "record_id": "random opaque id",
  "provider": "whoop",
  "resource": "cycles",
  "fetched_at": "2026-07-26T12:34:56.123456Z",
  "request": {"method": "GET", "path": "/developer/v2/cycle", "query": {}},
  "response": {
    "status": 200,
    "content_type": "application/json",
    "headers": {},
    "byte_length": 1234,
    "sha256": "..."
  },
  "attempt": 1,
  "page": 1
}
```

The body file is written first to an owner-only temporary file, fsynced, and atomically renamed.
The metadata file is committed only after the body is durable. Existing record IDs are never reused.
Runs receive immutable `run.started.json` and `run.finished.json` receipts; a crash leaves an honest
started-only run.

### Archive location

Default local state:

```text
~/Library/Application Support/Viventium/health/
  secrets/
  archive/<provider>/<YYYY>/<MM>/<DD>/<run-id>/
  logs/
  locks/
```

The root is configurable with `VIVENTIUM_HEALTH_HOME` or `--root` for testing and future compiled
Viventium configuration. Directories use owner-only permissions; secret and archive files use
owner-read/write permissions. No state path is placed in the repository.

### WHOOP resources

The first adapter declares the current official v2 read resources rather than modeling their body:

- cycles collection
- recovery collection
- sleep collection
- workout collection
- basic profile singleton when its scope was explicitly granted
- body measurement singleton when its scope was explicitly granted

The default continuous scopes are `read:cycles read:recovery read:sleep read:workout offline`.
Profile and body scopes remain explicit because WHOOP asks apps to limit scopes to those they use.
The operator can request them without code changes. Whatever a granted endpoint returns is archived
in full without field filtering.

## Failure semantics

- Every received HTTP response, including 401, 403, 429, and 5xx, is archived exactly once per
  attempt before retry or failure classification.
- Network failures create metadata-only attempt receipts with the error class and no fabricated body.
- 429 and 5xx are retried a bounded number of times, honoring a bounded `Retry-After` or
  `X-RateLimit-Reset` delay. WHOOP defines `X-RateLimit-Reset` as seconds until reset; it is used
  only for 429 responses and is not interpreted as an epoch timestamp. A headerless 429 waits one
  minute before the next bounded attempt, while 5xx retains short exponential retry.
- A collection pauses before its next page when WHOOP reports no remaining minute-window requests.
- Each page may receive one 401 refresh-and-retry cycle; repeated 401 on the same page fails instead
  of looping, while a later page may refresh a newly expired token again.
- Refresh-token rotation is serialized by the pull lock and persisted atomically before another
  request may use it.
- One active pull per state root is allowed. A live lock fails fast; a stale dead-process lock is
  recoverable and documented.
- A partial run is not “no data.” The finished receipt names successful, failed, and incomplete
  resources and the CLI exits non-zero when any selected resource is incomplete.
- `--all-history` and `--lookback-days` are mutually exclusive. The all-history request omits only
  the collection `start` filter, keeps a fixed current `end`, follows every `next_token`, and records
  `requested_start: null` so the open boundary is explicit rather than fabricated.
- Pagination remains bounded at 1,000 pages per resource (25,000 records at WHOOP's current maximum
  page size). Reaching that cap returns `pagination_limit` and a non-zero CLI status. `record_count`
  is the exact number of archived response/error records for the run and does not share list limits.
- An omitted, null, or empty `next_token` completes a collection exactly as WHOOP's pagination
  contract specifies; non-string and repeated non-empty tokens remain explicit failures.

## LLM consumption contract

- Listing is bounded and returns opaque record IDs, provider/resource, capture timestamp, status,
  byte count, and hash—not filesystem paths.
- Reading accepts only an archive-generated record ID, never an arbitrary path.
- Reading is chunked by byte offset and returns `next_offset` plus `complete`; full storage never
  implies unbounded prompt injection.
- UTF-8 bodies are returned as text. Other bytes are base64 encoded without interpretation.
- External payload text is untrusted evidence, never instructions to the MCP server or host agent.
- The MCP has no write, pull, auth, revoke, delete, shell, URL-fetch, or arbitrary-file tool.

## Daily scheduling

The first supported scheduler is a macOS user LaunchAgent because Viventium's current local product
surface is macOS. It calls the installed Python executable directly, uses a calendar interval, starts
once on load for catch-up, and runs a three-day correction window. It contains no credential value.
Linux/Windows users can invoke the same idempotent pull command from their native scheduler; native
installer support is later work.

The schedule is not installed during package installation or tests. It is created only by the
explicit `schedule install` command after credentials and an OAuth token exist.

## Code style

- typed public functions; dataclasses only where they remove ambiguity;
- dependency injection for clock, sleep, URL opener, and paths at test boundaries;
- no response-body DTOs, score helpers, or health-domain utilities;
- errors name the boundary and safe corrective action without leaking bodies or secrets.

Example:

```python
body, response = http_get(request)
record = archive.write_response(
    provider="whoop",
    resource=resource.name,
    body=body,
    fetched_at=clock.now(),
    status=response.status,
)
```

## Testing strategy

- Unit: atomic archive writes, exact bytes/hash, permissions, path safety, indexes, read paging,
  token rotation, scope parsing, schedule rendering.
- Local integration: a real localhost HTTP server exercises OAuth token exchange/refresh, bearer
  requests, pagination, retries, failures, and a full CLI pull without mocks at the HTTP layer.
- MCP subprocess: initialize, initialized notification, tool discovery, list/read calls, invalid
  record, stdout purity, and protocol error shapes.
- Live contract: download WHOOP's official OpenAPI document, verify configured resource paths,
  collection controls, and unauthenticated 401 behavior. No owner data.
- Owner acceptance: real device/app/cloud sync, OAuth, daily repeat, late correction, restart,
  refresh rotation, revoke, and LLM read. OAuth, complete repeated pulls, rotating refresh across
  processes, real daily scheduling, and full MCP replay passed on 2026-07-27; late correction,
  explicit revocation remains open. Parent-agent activation, post-restart persistence, and a
  controlled cognitive-value A/B passed on 2026-07-27.

## Boundaries

Always:

- archive exact bytes before parsing transport controls;
- timestamp in UTC with microseconds;
- keep permissions owner-only;
- preserve all pages, attempts, statuses, and prior runs;
- test missing auth, partial data, retries, restart, and privacy.

Ask first:

- add a new provider OAuth grant or request new scopes;
- expose a networked MCP transport;
- add interpretation, alerting, saved-memory, mobile, or webhook behavior;
- delete or change retention of private archives.

Never:

- commit health data or credentials;
- log bodies or secrets;
- overwrite an archive record;
- infer a health meaning in connector code;
- accept a user-supplied URL or filesystem path through MCP.

## Success criteria

1. A two-page fake WHOOP collection is archived byte-for-byte, including both page bodies and
   immutable metadata.
2. All configured resources run; one failure cannot be mistaken for a healthy empty result.
3. A repeated pull creates new records and leaves the first run unchanged.
4. Rotating refresh tokens survive a new process and never appear in output or archives.
5. The CLI and MCP can list and page through every archived byte using opaque IDs only.
6. The daily LaunchAgent is deterministic, credential-free, owner-scoped, and tested without being
   installed on the development machine.
7. The official live contract matches the adapter and unauthenticated endpoints fail closed.
8. All automated tests, build, packaging, public-safety scans, and an installed-wheel smoke pass.
9. Real owner completion is claimed only after the explicit owner acceptance run.

## Open gates

- Observe a real WHOOP late sync/correction as a new immutable capture and test explicit revocation
  when interrupting the active daily pool is acceptable.
- Keep the parent Viventium config/MCP integration pinned to a reviewed component release. Its live
  activation and cognitive-value A/B passed; the owning integration remains outside this isolated
  component.
