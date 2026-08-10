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

- Vision and contract: implemented
- WHOOP connector: implemented and validated against synthetic localhost HTTP, the live official
  contract, and an owner-authorized WHOOP account
- Real owner path: six authorized resource families captured in complete manual and scheduled runs;
  rotating refresh and complete read-only MCP replay validated without publishing health values
- Oura and other devices: documented expansion path; not implemented yet
- Parent Viventium integration: live main-agent activation, post-restart MCP use, and a controlled
  cognitive-value A/B passed without publishing private health content
- Remaining acceptance: observe a real late vendor correction and test explicit revocation

## Install

Python 3.10 or newer is the only runtime prerequisite. There are no runtime package dependencies.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/viventium-health --version
```

Private state defaults to `~/Library/Application Support/Viventium/health`. Override it with the
global `--root` option or `VIVENTIUM_HEALTH_HOME`; never point it into a git checkout.

## Connect WHOOP

Create an app in the [WHOOP Developer Dashboard](https://developer-dashboard.whoop.com/), register
an exact HTTPS or custom-scheme redirect URI, then configure locally. The interactive form keeps the
client secret out of command history and process listings:

```bash
viventium-health whoop configure
viventium-health whoop connect
```

Open the printed official WHOOP URL. After granting access, copy the final redirect URL and complete
the saved eight-character state/code exchange:

```bash
viventium-health whoop connect --callback-url '<exact-final-redirect-url>'
viventium-health pull whoop --all-history
```

`--all-history` retrieves all available history exposed by WHOOP's six official v2 read resources.
It leaves the collection start filter open and follows pagination through a fixed current capture
time. A 1,000-page safety cap applies per resource; reaching it fails the run explicitly instead of
claiming completion. Use this command once after connection. Daily operation stays on the small
correction window:

```bash
viventium-health pull whoop --lookback-days 3
```

The full-history pull can run for several minutes because it honors WHOOP's published request
limits. Do not start it while the daily LaunchAgent is pulling; a concurrent scheduled pull fails
fast and can catch up on its next run.

The default consent is the four continuous time-series resources plus `offline` for reliable daily
refresh. Profile and body measurement are optional; request them explicitly during `configure` only
if wanted. Every field and every page from each granted endpoint is retained exactly as returned.

To disable the grant without deleting historical captures:

```bash
viventium-health schedule uninstall
viventium-health whoop disconnect
```

## Daily pool

On macOS, install the tested owner-level LaunchAgent explicitly:

```bash
viventium-health schedule install --provider whoop --hour 6 --minute 0 --lookback-days 3
viventium-health schedule status
```

It runs once after load for catch-up and daily at the selected local time. The job contains a fixed
executable and arguments, not OAuth values. On Linux or Windows, schedule the same idempotent `pull`
command with the native scheduler.

## Read and give an LLM access

The operator CLI and MCP expose only bounded read operations:

```bash
viventium-health runs --provider whoop --limit 10
viventium-health records --provider whoop --limit 50
viventium-health read <opaque-record-id> --offset 0 --max-bytes 65536
viventium-health mcp
```

A local MCP host can use:

```yaml
mcpServers:
  viventium-health:
    type: stdio
    command: viventium-health
    args:
      - mcp
    timeout: 120000
    chatMenu: true
```

The host process must be able to resolve `viventium-health` and run under the same local user that
owns the archive. Its three tools are `health_list_runs`, `health_list_records`, and
`health_read_record`. There is intentionally no model-facing authorization, network pull, delete,
path, URL-fetch, or shell capability. Raw payload text is untrusted evidence, not instructions.

This repository proves the MCP itself and records public-safe owner acceptance in `qa/reports/`.
Product-wide Viventium installation/configuration activation stays in the parent repository so this
component remains independently testable and does not mutate an owner's live agent configuration
during installation.

## Verify

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
VIVENTIUM_HEALTH_LIVE_CONTRACT=1 PYTHONPATH=src \
  python3 -m unittest tests.test_whoop_live_contract -v
python3 -m compileall -q src tests
python3 -m build
```

## Read first

- [Viventium-Health requirements and learnings](docs/requirements_and_learnings/01_Viventium_Health.md)
- [Implementation specification](docs/SPEC.md)
- [Raw append-only archive decision](docs/decisions/ADR-001-raw-append-only-file-archive.md)
- [QA cases](qa/cases.md)
- [Privacy policy](PRIVACY.md)

See `qa/reports/` for dated, public-safe evidence of what was and was not actually exercised.
