# WHOOP-first implementation QA — 2026-07-26

## Verdict

The isolated Viventium-Health component is `PASS` for synthetic implementation, official live
contract, packaging, installed CLI/MCP, and macOS LaunchAgent behavior. It is `BLOCKED` for real
owner/device data and cognitive-value acceptance because no owner OAuth grant or private evidence was
provided. Parent Viventium installation/config activation remains a separate integration, as required
by the accepted isolation boundary.

## Scope and environment

- Public-safe synthetic data only
- macOS arm64 host
- Python 3.14.6 and the declared minimum Python 3.10.20
- Python standard library only at runtime
- WHOOP official production OpenAPI and one unauthenticated production request
- No browser UI exists in this component, so Playwright/browser QA is not applicable
- No real health payload, owner identifier, credential, redirect, or device identifier was captured

## Executed evidence

| Gate | Actual execution | Result |
| --- | --- | --- |
| Automated suite | Warning-as-error suite on Python 3.14.6 and 3.10.20 | Each: 16 passed, 2 expected live tests skipped, 0 failed |
| Live WHOOP contract | Live-gated OpenAPI/path/scope/paging and missing-bearer tests | 2 passed, 0 failed |
| Exact/archive flow | Exact bytes/hash, immutable repeat, run receipts, network errors, paging | PASS |
| OAuth flow | Localhost token exchange, eight-character state, rotating refresh, 401 refresh, revoke | PASS |
| Failure matrix | 401, 403, 429, 503, network refusal, invalid JSON control, partial run | PASS |
| MCP subprocess | Initialize, initialized notification, tool list, record list/read, invalid ID, stdout purity | PASS |
| Wheel build/install | Isolated sdist/wheel build, no-dependency wheel install, version, empty CLI | PASS; 15 wheel members, 9 required runtime modules present |
| Installed artifact loop | Installed CLI list/read and installed stdio MCP over synthetic archive | PASS; one record, complete read, three MCP responses, zero stderr bytes |
| Fresh-clone minimum-runtime loop | Local clean clone, Python 3.10 suite/compile/build/install/CLI/MCP/public scan | PASS |
| Real LaunchAgent loop | Installed package, synthetic invalid grant, real `launchctl` bootstrap/RunAtLoad/status/bootout | PASS; job loaded, ran, classified auth-refresh failure, and was fully removed |
| Static lint | Ruff over `src` and `tests` | PASS after mechanical import/typing cleanup |
| Security scan | Bandit over runtime source | 0 medium/high; two reviewed low findings: fixed-argument `launchctl` subprocess use and official token URL mistaken for a password |
| Dependency audit | AST import inventory plus wheel metadata | PASS; no non-standard runtime imports and no runtime dependencies |
| Compile | `python3 -m compileall -q src tests` | PASS |
| Public safety | tracked-file identifier/secret/private-path scan and ignored-state review | PASS |

## Requirement traceability

| Requirement | Cases | Evidence | Result |
| --- | --- | --- | --- |
| Full exact provider responses | `VH-001`, `VH-003`, `VH-004` | Byte equality, SHA-256, all-page HTTP server, opt-in singleton scopes | PASS |
| Raw append-only storage, no DB | `VH-001`, `VH-002` | First run unchanged after corrected second capture; file-only package inventory | PASS |
| Reliable daily auth/pull | `VH-005`–`VH-007`, `VH-011` | Token rotation, lock, bounded retry, real launchd RunAtLoad degraded-auth execution | PASS for implemented/synthetic paths |
| LLM-safe access | `VH-009`, `VH-010` | Exactly three read-only tools, opaque IDs, byte bounds, path rejection, clean stdio | PASS |
| Official API truth | `VH-012` | Current OpenAPI paths/scopes/limit/nextToken plus live 401 | PASS |
| Installable artifact | `VH-013` | Isolated build, wheel install, installed CLI/read/MCP | PASS |
| Real WHOOP owner | `VH-014` | Requires developer app, consent, device/app/cloud sync, correction and restart | BLOCKED |
| Cognitive usefulness | `VH-015` | Requires private evidence and a real Viventium A/B | BLOCKED |

## User-use-case results

- First run/no config: `PASS`; empty inventory is distinct from missing OAuth token.
- Configure/begin consent: `PASS` with synthetic values; client secret did not appear in output.
- Multi-page backfill/daily pull mechanics: `PASS` against a real localhost HTTP server.
- Late correction: `PASS` at archive semantics; later capture coexists and earlier bytes do not change.
- Expired/revoked/missing auth: `PASS` for synthetic exchange, refresh, 401, revoke, and clear behavior.
- Rate limit/provider outage: `PASS`; received failures are archived and run status is not empty success.
- Restart persistence: `PASS` across subprocess and installed-artifact reads; real owner refresh restart remains `BLOCKED`.
- LLM listing/read: `PASS` at the stdio MCP boundary; actual parent-agent final-answer behavior is `BLOCKED` pending parent activation and private evidence.
- Daily scheduling: `PASS` for real launchd lifecycle and RunAtLoad execution with a synthetic degraded grant; a successful owner-data scheduled run remains part of `VH-014`.

## Independent review status

The required Claude Desktop review-only pass was attempted after the implementation and test proposal
were complete. Claude Desktop showed the requested Opus 5 / highest-effort controls but the account was
at its usage limit, so no independent-model verdict was produced. This is recorded as unavailable
supporting evidence, not a pass. Static, security, protocol, installed-artifact, live-contract, and
real-scheduler reviews were completed independently within the primary QA pass.

The requested `ProjectViventium/Viventium-Health` GitHub repository could not be created because the
active authenticated account lacks organization repository-creation permission. No alternate-owner
repository was created and nothing was pushed. The local independent repository and public-safety
review are ready for the organization owner to create the empty destination.

## Remaining gates

1. Create or select the owner-controlled WHOOP developer app and exact redirect URI.
2. Run owner consent, initial backfill, a later overlapping pull, a real correction/late sync, refresh
   across process restart, revoke, and full MCP read without publishing private evidence.
3. Integrate the proven stdio MCP into the parent Viventium installer/config boundary, then test a real
   model tool call and final answer without automatically injecting health data into prompt or memory.
4. Run the cognitive A/B required by `VH-015`; preserve evidence citations and forbid diagnosis.

Until those gates run, the accurate claim is: the connector component is implemented and validated;
real WHOOP owner and end-to-end Viventium cognitive acceptance remain blocked by explicit access and
parent-integration boundaries.
