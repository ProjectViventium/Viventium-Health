# Viventium-Health QA cases

## Case catalog

| Case ID | Requirement | User outcome | Surface | Expected result | Status |
| --- | --- | --- | --- | --- | --- |
| `VH-001` | Exact raw archival | No provider field is lost or rewritten. | Archive | Body bytes and SHA-256 exactly match the HTTP response; metadata is separate. | PASS — 2026-07-26 |
| `VH-002` | Append-only history | Corrections and repeated pulls remain auditable. | Archive/CLI | Second pull creates new records; first run bytes and metadata are unchanged. | PASS — 2026-07-26 |
| `VH-003` | Complete pagination | “Full pull” means all collection pages. | WHOOP connector | Every `next_token` is followed; every page response is archived before parsing. | PASS — 2026-07-26 |
| `VH-004` | Scope-controlled full resources | Every granted selected endpoint is captured without field filtering. | WHOOP OAuth/API | Product default covers all six documented reads plus offline; narrower CLI grants remain explicit. | PASS — 2026-08-10 |
| `VH-005` | Rotating OAuth | Daily pulls survive token expiry and restart. | WHOOP OAuth | Refresh rotates atomically, old token is replaced, no token reaches output/archive/log. | PASS — 2026-07-26 |
| `VH-006` | Failure truth | Empty data is not confused with failed retrieval. | WHOOP/CLI | 401, 403, 429, 5xx, network error, invalid JSON control, and partial paging are distinct. | PASS — 2026-07-26 |
| `VH-007` | Bounded retry and locking | Daily work is reliable without refresh races or runaway requests. | Pull runtime | One pull per root; bounded retry honors safe delay; dead stale lock recovers. | PASS — 2026-07-26 |
| `VH-008` | Private storage | Health evidence and credentials remain private. | Filesystem/git | Directories/files are owner-only; secret/public scans are clean; state is ignored. | PASS — 2026-07-26 |
| `VH-009` | Read-only LLM access | Viventium can consume every byte without broad authority. | CLI/MCP | List uses opaque IDs; read is byte-paged; no path/auth/pull/delete/network tool exists. | PASS — 2026-07-26 |
| `VH-010` | MCP protocol | A real MCP host can discover and call the reader. | stdio subprocess | Initialize/initialized/list/call pass; stdout contains MCP JSON only; errors are structured. | PASS — 2026-07-26 |
| `VH-011` | Daily schedule | A host can maintain the pool without paid services. | macOS LaunchAgent | Generated job has no secret, calls fixed executable/args, uses calendar + load catch-up. | PASS — 2026-07-26 |
| `VH-012` | Official contract drift | Adapter paths remain grounded in WHOOP's current API. | Live official API/OpenAPI | Paths/scopes/paging match current OpenAPI; missing bearer returns 401. | PASS — 2026-07-26 |
| `VH-013` | Package/user flow | A fresh environment can install and use the component. | wheel/CLI | Build, isolated install, help, empty state, fake pull, list, read, MCP all work. | PASS — 2026-07-26 |
| `VH-014` | Real owner WHOOP acceptance | Actual device data reaches the LLM evidence pool reliably. | WHOOP app/cloud/OAuth/CLI/MCP | Sync, backfill, overlap, correction, refresh/restart, revoke, and full read all pass. | PARTIAL — OAuth, repeated/scheduled pull, rotation/restart, integrity, full MCP read PASS 2026-07-27; correction/revoke open |
| `VH-015` | Cognitive value | More raw data improves judgment, not just detail. | Viventium agent | A/B answer is more useful and evidence-cited, remains non-diagnostic, and retrieves only when relevant. | PASS — 2026-07-27; real browser A/B after runtime restart |
| `VH-016` | Complete initial history and rate-limit timing | First connection can retrieve the provider's available API history without an invented earliest date. | WHOOP/CLI | `--all-history` omits optional `start`, fixes `end`, accepts empty pagination completion, proactively throttles, retries headerless 429 by minute, refreshes on later pages, reports an exact count, and fails explicitly at the safety cap. | PASS-AUTOMATED — 2026-08-10; live owner run pending OAuth |
| `VH-017` | Minimal-click, truthful onboarding | Other local owners can connect without terminal work or hidden provider limits. | Viventium UI/helper/API/CLI | Provisioned app is one Connect action plus provider consent; self-managed setup combines save/connect; callback stays private; history and schedule start automatically; counts/status remain readable. | PASS-AUTOMATED — 2026-08-10; installed browser/provider-consent rerun pending |
| `VH-018` | Official export fallback | Journal and provider-export fields survive even without API availability. | Viventium UI/API/CLI/archive/MCP | Exact bounded ZIP and every safe entry are append-only; Journal is discoverable; traversal, links, encryption, and expansion abuse fail closed. | PASS-AUTOMATED — 2026-08-10; installed browser upload pending |
| `VH-019` | Readable manual WHOOP evidence | App-only views such as Stress Monitor can be supplied without scraping or false structure. | Viventium UI/API/CLI/archive/MCP image | One PNG/JPEG upload stores exact private bytes, counts separately, verifies integrity, returns MCP image content, and rejects spoofed/oversized/non-image input. | PASS-AUTOMATED — 2026-08-10; installed browser upload pending |
| `VH-020` | Host-owner access isolation | Shared/public agents cannot expose host-wide private health evidence to ordinary accounts. | LibreChat agent/tool runtime, API, compiler | A structural `local_owner` MCP audience denies missing/non-admin identity before tool startup; API mutations are admin-only; disabled health omits the server. | PASS-AUTOMATED — 2026-08-10; installed cross-role browser check pending |
| `VH-021` | Bounded recovery and repeat input | Abandoned OAuth, concurrent callback retries, background work, and duplicate ZIPs recover without runaway polling, clobbering progress, or storage growth. | UI/API/CLI/archive | OAuth state expires in ten minutes; onboarding is single-flight; spawned work has a lifetime; degraded UI names recovery; exact ZIP hash is idempotent. | PASS-AUTOMATED — 2026-08-10; installed browser persistence check pending |

## Natural user-use-case checklist

| Use case | Case links | Result required |
| --- | --- | --- |
| First run with no config | `VH-006`, `VH-013` | Clear setup action; no files falsely presented as data. |
| Configure and connect WHOOP | `VH-004`, `VH-005`, `VH-014` | Exact scopes and redirect are visible before consent; token stays private. |
| Connect from Viventium settings | `VH-017` | One product action when provisioned, combined save/connect otherwise; helper callback triggers backfill and schedule. |
| Initial backfill | `VH-001`–`VH-004`, `VH-007`, `VH-016` | Every selected resource/page through the fixed capture time is captured once per attempt with an honest open-start run receipt. |
| Normal daily pull | `VH-002`, `VH-005`, `VH-011` | Three-day overlap appends a new complete run with no operator work. |
| Late phone sync/correction | `VH-002`, `VH-014` | Later raw response is retained beside earlier evidence; nothing is overwritten. |
| Missing/revoked auth | `VH-005`, `VH-006` | Explicit auth blocker; old archive remains readable. |
| Rate limit/provider outage | `VH-006`, `VH-007` | Bounded retry and incomplete status; never “no WHOOP data.” |
| Restart | `VH-005`, `VH-011`, `VH-014` | Rotated credential and schedule still work from a new process. |
| LLM asks for recent evidence | `VH-009`, `VH-010`, `VH-015` | Bounded list/read, exact provenance, no interpretation from connector. |
| Import official WHOOP export | `VH-018` | Exact ZIP/files survive; Journal is readable; unsafe bundles fail before file import. |
| Add Stress/app screenshot | `VH-019` | Exact PNG/JPEG is private, separately counted, and available to the model as unstructured image evidence. |
| Ordinary account opens a shared agent | `VH-020` | Host-owner health MCP tools do not initialize and no health payload is readable. |
| Retry consent or reselect the same export | `VH-021` | Stale consent stops, concurrent callbacks fail closed, and the existing exact export is reused. |
| Public review/release | `VH-008`, `VH-012`, `VH-013` | No private state; official contract and installed artifact are proven. |

## Evidence rules

Dated reports must state exactly what ran and what did not. Record synthetic counts, status codes,
byte lengths, hashes, test totals, durations, and conclusions only. Do not record health bodies,
OAuth values, local absolute paths, usernames, emails, device IDs, WHOOP user IDs, request IDs, or
screenshots containing private data.

Latest evidence: [2026-07-27 Viventium cognitive acceptance](reports/2026-07-27-viventium-cognitive-acceptance.md)
and [2026-07-27 owner WHOOP acceptance](reports/2026-07-27-whoop-owner-acceptance.md).
