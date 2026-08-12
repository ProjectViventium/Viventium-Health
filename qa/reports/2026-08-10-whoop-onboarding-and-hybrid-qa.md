# WHOOP onboarding and hybrid evidence QA — 2026-08-10

## Result

PASS for installed owner onboarding, complete documented API-family acquisition, readable private
status, scheduled corrections, read-only MCP access, refresh persistence, and cross-role isolation.
The export and manual-image lanes are product-complete and regression-covered, but their real-file
acceptance is PARTIAL because no official export ZIP was supplied and the original image attachments
were no longer available at import time.

## Coverage boundary

- The official developer API captures every response field for body, cycle, profile, recovery,
  sleep, and workout across the provider's available history.
- The official export lane preserves the exact bounded ZIP and every safe entry, including Journal
  material that the API may not provide.
- The manual evidence lane preserves exact PNG/JPEG bytes for app-only views such as Stress Monitor
  and exposes them as unstructured MCP image content. It does not invent structured measurements.
- Managed local installations present one Connect action followed by provider consent. Self-managed
  installations combine credential save and connection in one form and disclose provider approval
  limits instead of embedding a public client secret.

## User-level evidence actually run

- Installed owner Settings showed connected state, all six data families, readable per-family totals,
  daily correction status, export/image lanes, and explicit historical-retention behavior.
- A direct setup link opened the WHOOP connection surface. Closing and reopening Settings plus a
  full refresh preserved the connected status and totals.
- A fresh first-message owner chat used the private WHOOP tool and returned the same aggregate total
  and family coverage as direct MCP/status reads.
- A fresh ordinary account showed no WHOOP card and received no private WHOOP capability. Server
  evidence confirmed that the owner-only health MCP process did not start for that account.
- The synthetic ordinary account and its test conversations were deleted through the product UI;
  persistence inspection confirmed removal.
- The live owner grant was intentionally left connected because ongoing acquisition is the accepted
  end state.

## Automated and build evidence

- Component suite: 52 passed; two opt-in live-provider contract checks skipped.
- Focused LibreChat backend suites: 117 passed.
- WHOOP package suite: 7 passed.
- Connected-account client suites: 8 passed.
- Parent compiler/runtime/onboarding selection: 23 passed; 166 unrelated cases deselected.
- API and production client builds completed successfully.

## Not run and exact prerequisites

- A real official export upload was not run because no WHOOP export ZIP was supplied.
- A real Stress Monitor image upload was not run because the original attachments had expired.
  Reattach the images to complete this acceptance step.
- Live disconnect/revoke was not run because it would break the requested ongoing connection;
  revocation and retained-history behavior remain regression-covered.
- A new external fresh-clone install was not repeated in this pass. The isolated component install,
  pinned runtime, installed executable, and live runtime artifact were verified.

## Public-safety review

This report contains no health bodies, credentials, account identifiers, conversation identifiers,
screenshots, usernames, emails, hostnames, or local absolute paths.
