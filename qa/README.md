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

Automated localhost tests support acceptance. The real owner WHOOP authorization, complete manual
and scheduled pulls, rotating refresh across processes, archive integrity, and full MCP reads passed
on 2026-07-27. Late correction, explicit revocation, and parent-agent cognitive A/B remain open.

Latest run: [2026-07-27 owner WHOOP acceptance](reports/2026-07-27-whoop-owner-acceptance.md).
