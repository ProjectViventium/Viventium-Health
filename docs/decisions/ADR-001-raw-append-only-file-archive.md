# ADR-001: Preserve provider responses in a raw append-only file archive

## Status

Accepted — 2026-07-26

## Context

Viventium needs health-device evidence for LLM reasoning. Wearable vendors expose different and
changing concepts, identifiers, payloads, score states, units, time models, corrections, and missing
data. Designing a universal health database before multiple real connectors exist would discard
meaning, create migrations, and spend effort on structure the LLM does not require.

The user explicitly requires raw, full, timestamped dumps and asked us not to fit health data into a
database or assume what any current or future gadget includes.

## Decision

Use an append-only local file archive:

- exact provider response bytes are the canonical evidence;
- a separate small JSON sidecar records transport provenance and integrity facts;
- every page, retry response, correction-window pull, and failure response is retained;
- no record is updated or normalized;
- readers enumerate opaque record IDs and page raw bytes without accepting filesystem paths;
- provider adapters own only authentication, endpoint requests, and pagination controls.

## Alternatives considered

### Relational or document database

Rejected for v1. It requires a schema, migration policy, field interpretation, and another runtime
service without improving exact evidence preservation or LLM readability.

### Cross-vendor normalized observations

Rejected for v1. “Sleep,” “recovery,” “readiness,” HRV methods, cycles, and vendor scores are not
interchangeable. Normalization would encode assumptions before the evidence base earns them.

### Vendor export only

Useful for a no-token value test and future generic import, but not dependable for a daily pool.

### Web scraping or private APIs

Rejected for continuous use. Session handling, UI drift, unsupported endpoints, terms exposure, and
weak correction semantics make them less reliable than official OAuth APIs.

### Commercial aggregator

Rejected for the first connector. It adds recurring cost, another health-data processor, and its own
normalization before direct official APIs have been proven insufficient.

### Webhook-first ingestion

Deferred. WHOOP webhooks do not cover every resource and require a publicly reachable signed event
receiver plus reconciliation. One daily overlapping poll is simpler and sufficient for the stated
need.

## Consequences

Positive:

- complete source truth survives provider schema changes;
- storage is inspectable, portable, dependency-free, and inexpensive;
- new sources do not require a common health model;
- repeated pulls naturally preserve corrections and audit history;
- LLM retrieval can be bounded independently from storage completeness.

Costs:

- repeated correction-window pulls duplicate bytes;
- cross-source analytics are model/retrieval work, not precomputed database queries;
- retention and deletion operate on files/runs rather than rows;
- transport-control fields such as pagination tokens still require small provider-specific parsing.

These costs are accepted because fidelity and simplicity are the primary product requirements.
