# Viventium cognitive acceptance — 2026-07-27

## Verdict

`VH-015` is `PASS`. A real Viventium main-agent session used the installed Viventium-Health MCP
after a runtime restart. The evidence-enabled answer was materially more useful than a matched
no-health-tool control while remaining source-cited, uncertainty-aware, and non-diagnostic.

No health payload, measurement, account identity, archive identifier, OAuth value, conversation
identifier, private screenshot, or owner-specific path is included in this public report.

## Actual execution

| Gate | Actual public-safe evidence | Result |
| --- | --- | --- |
| Protected activation | Live-vs-source drift was reviewed; a dry run preceded a tools-only main-agent update; no tool was removed and other agent settings were untouched | PASS |
| Installed boundary | Generated runtime configuration contained the reviewed stdio server and exactly the expected read-only bindings | PASS |
| Restart | The local Viventium runtime restarted healthy before the browser sessions | PASS |
| Inventory request | The visible agent invoked list-runs and list-records and returned only run status, six resource names, capture time, and integrity presence as requested | PASS |
| Bounded relevant read | The evidence-enabled session invoked list-runs, list-records, and two bounded read-record calls | PASS |
| Cognitive quality | The answer added an actionable planning recommendation, cited WHOOP and capture time, called the vendor result an estimate rather than medical truth, stated uncertainty, and made no diagnosis | PASS |
| No-evidence control | A fresh session forbidden from tools, memory, and assumptions correctly said it could not assess current recovery from the prompt alone; it invoked no tools | PASS |
| Visible persistence | Tool states and final answers remained visible after navigation and refresh | PASS |

## Interpretation

The A/B difference came from retrieved evidence, not hidden assumptions: the control made no current
health claim, while the evidence-enabled path added grounded planning value. Retrieval remained
bounded and on demand; the connector did not automatically inject the archive or create a health
database or saved-memory copy. The selected chunks entered normal agent tool context and inherited
the host's conversation retention. Parent-runtime persistence details and its remaining degraded-path
gate are tracked by the parent repository rather than this component.

## Review gate

A separated five-axis review covered correctness, readability, architecture, security, and
performance. It removed the secret-bearing configure argument, clarified normal host conversation
retention, and confirmed the bounded reader remains the only model-facing authority. No blocking
finding remained after the changes and full rerun. The required Claude review-only second opinion
was attempted through both Desktop and CLI, but the provider's usage limit prevented a review; no
Claude verdict is claimed.
