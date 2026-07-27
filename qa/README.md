# Viventium-Health QA

This folder owns public-safe acceptance for the raw health evidence bridge.

## Quality bar

- exact source bytes and complete pagination;
- append-only correction history;
- honest operational failure classes;
- owner-only credentials and archive state;
- bounded, read-only LLM access;
- no health interpretation in connector code;
- no secrets, personal health data, local paths, account IDs, or raw runtime dumps in reports.

Automated localhost tests support acceptance. A real owner WHOOP path remains `BLOCKED` until an
owner explicitly creates an app, grants OAuth access, syncs a real device, and exercises refresh,
correction, restart, revoke, and read paths.

Latest run: [2026-07-26 WHOOP-first implementation QA](reports/2026-07-26-whoop-first-implementation-qa.md).
