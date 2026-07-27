# Viventium-Health

Viventium-Health is the local-first evidence bridge between Viventium and health sources: wearables,
rings, watches, apps, exports, sensors, and future devices. WHOOP is the first live connector. Oura
Ring is the next intended direct adapter.

The component does one thing: it captures complete source responses as timestamped, append-only files
and makes those files safely readable by an LLM. It does not invent a universal health schema, put
health data in saved memory, interpret scores, or diagnose anything.

```text
device -> vendor app -> official vendor cloud API
       -> Viventium-Health daily pull
       -> exact response bytes + capture metadata
       -> read-only CLI / MCP paging
       -> Viventium decides when and how to reason about the evidence
```

## Status

- Vision and contract: accepted
- WHOOP connector: implementation target for this repository
- Oura and other devices: documented expansion path; not implemented yet
- Real owner OAuth/data validation: requires an owner-created WHOOP developer app and explicit OAuth
  consent, so it cannot be claimed by synthetic tests

## Read first

- [Viventium-Health requirements and learnings](docs/requirements_and_learnings/01_Viventium_Health.md)
- [Implementation specification](docs/SPEC.md)
- [Raw append-only archive decision](docs/decisions/ADR-001-raw-append-only-file-archive.md)
- [QA cases](qa/cases.md)

The executable quick start will be added only after the test-first implementation satisfies the
written contract.
