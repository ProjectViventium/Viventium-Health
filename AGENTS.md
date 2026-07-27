# Viventium-Health

Repository-specific rules for humans and agents working on this component.

## Outcome

Preserve complete health-source evidence for later LLM use with the least possible machinery.
Quality means faithful bytes, truthful timestamps and failures, private storage, and dependable
retrieval. Performance means bounded network work, paging, retries, and simple local files.

## Non-negotiable rules

- Read `docs/requirements_and_learnings/01_Viventium_Health.md` and `docs/SPEC.md` before changing
  behavior.
- A connector is a courier. It must not interpret, normalize, score, diagnose, or recommend.
- Store exact response bodies. Metadata may describe capture facts but must not reshape the body.
- Raw health data, OAuth credentials, tokens, logs, and owner-specific evidence never enter git.
- Never log authorization headers, client secrets, access tokens, refresh tokens, or response bodies.
- Archives are append-only. Corrections are captured by another pull, never by overwriting history.
- The LLM boundary is read-only and paged. Pulling, authorization, revocation, and deletion remain
  explicit operator actions.
- Provider-specific knowledge belongs in provider adapters. The archive and reader remain provider
  neutral.
- Do not add a database, ORM, message queue, web UI, mobile app, webhook server, analytics layer,
  normalized health schema, or interpretation engine unless a later accepted requirement proves it
  is necessary.
- Use only official provider APIs for continuous connectors. Manual official exports may be imported;
  scraping and reverse-engineered private APIs are not production paths.

## Commands

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
python3 -m build
```

## QA

Keep durable cases in `qa/cases.md` and dated, public-safe evidence in `qa/reports/`. A real owner
OAuth/data run is `BLOCKED`, not `PASS`, until an owner explicitly grants access and the device sync,
refresh, correction, restart, revoke, and archive-read paths are exercised.
