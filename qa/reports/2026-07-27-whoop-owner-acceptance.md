# WHOOP owner acceptance — 2026-07-27

## Verdict

The owner-authorized WHOOP path is `PASS` for OAuth, full selected-resource capture, repeated pull,
rotating refresh across processes, real macOS daily scheduling, private raw-file integrity, and full
read-only MCP replay. `VH-014` remains `PARTIAL` because no actual late WHOOP correction was observed
and the active grant was not intentionally revoked. `VH-015` is now `PASS` after live parent
Viventium activation, restart persistence, and a controlled cognitive answer-quality A/B.

No health payload, measurement, profile value, account identity, device ID, OAuth value, archive ID,
or owner-specific path is included in this public report.

## Actual execution

| Gate | Actual public-safe evidence | Result |
| --- | --- | --- |
| Developer app and consent | Owner-created development app; all six official read scopes plus offline refresh granted | PASS |
| First live pull | Profile, body measurement, cycles, recovery, sleep, and workout each archived; run complete | PASS — 6 records |
| Overlapping repeat | A later three-day-overlap pull completed and appended another six records | PASS — 6 records |
| Refresh rotation/restart | Live refresh changed both access and refresh values, persisted atomically, and a later process pulled successfully | PASS |
| Daily scheduler | Owner LaunchAgent loaded with RunAtLoad and a 06:00 local calendar interval; catch-up run completed | PASS — 6 records |
| Raw fidelity | Every selected body length and SHA-256 matched its immutable metadata sidecar | PASS |
| Private storage | Runtime directories were owner-only and secret/archive files were owner read/write only | PASS |
| MCP protocol | Protocol `2025-06-18`; exactly three read-only tools listed | PASS |
| Full MCP replay | All six records from a complete run were read to completion and matched their archive hashes | PASS |
| MCP authority | No authorization, pull, network, path, write, delete, memory, or command tool exists | PASS |
| Late correction | No real vendor correction occurred during the acceptance window | OPEN |
| Revoke | Not run because it would intentionally break the active daily data pool | OPEN |
| Parent cognitive A/B | Live main-agent binding used bounded record reads; its evidence-enabled answer added useful planning guidance with provenance and uncertainty while the no-tool control made no unsupported claim | PASS |

## Requirement trace

- Full raw, datetimestamped, schema-free dump: `PASS`; provider bodies remain exact and metadata is
  separate.
- No database or cross-vendor normalization: `PASS`; only append-only files and run receipts exist.
- Reliable daily pool without additional services or fees: `PASS` on the owner macOS LaunchAgent.
- Android/iOS owner parity: `PASS` for the connector boundary; the wristband syncs through WHOOP's
  mobile app and this host reads the authorized cloud API.
- Bounded LLM consumption: `PASS` at both the component MCP boundary and the parent-agent usefulness
  boundary.

## Remaining acceptance

1. After a naturally late-synced or vendor-corrected record appears, prove that a later pull appends
   the changed response without rewriting prior evidence.
2. When interrupting the active feed is acceptable, revoke the grant, prove the next pull fails as
   auth rather than empty data, reconnect, and prove historical archives remain readable.
