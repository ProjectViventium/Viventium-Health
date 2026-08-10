"""Operator CLI for WHOOP acquisition and read-only archive access."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, TextIO

from . import __version__
from .archive import ArchiveError, RawArchive, default_root, utc_now
from .auth import DEFAULT_WHOOP_SCOPES, CredentialError, CredentialStore
from .evidence import WhoopEvidenceError, WhoopEvidenceImporter
from .importer import WhoopExportError, WhoopExportImporter
from .lock import LockBusyError, PullLock
from .mcp import serve
from .schedule import HealthScheduler, ScheduleError
from .status import WhoopOnboardingStore, build_whoop_status
from .whoop import WhoopClient, WhoopError


def _json(value: Any, stream: TextIO) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viventium-health", description="Raw health-source evidence bridge")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root", type=Path, default=default_root(), help="Private Viventium-Health state root")
    commands = parser.add_subparsers(dest="command", required=True)

    whoop = commands.add_parser("whoop", help="Configure WHOOP OAuth")
    whoop_commands = whoop.add_subparsers(dest="whoop_command", required=True)
    configure = whoop_commands.add_parser("configure", help="Save an owner-only WHOOP OAuth client")
    configure.add_argument("--client-id")
    configure.add_argument("--redirect-uri")
    configure.add_argument("--scope", action="append", dest="scopes")
    configure.add_argument("--json-stdin", action="store_true", help="Read client configuration as JSON from stdin")
    connect = whoop_commands.add_parser("connect", help="Begin or complete WHOOP owner authorization")
    callback_source = connect.add_mutually_exclusive_group()
    callback_source.add_argument("--callback-url", help="Final registered redirect URL containing code and state")
    callback_source.add_argument("--callback-stdin", action="store_true", help="Read the final redirect URL from stdin")
    connect.add_argument("--json", action="store_true", help="Return a machine-readable authorization result")
    onboard = whoop_commands.add_parser(
        "onboard",
        help="Complete authorization, import all history, and install daily correction pulls",
    )
    onboard.add_argument("--callback-stdin", action="store_true", required=True)
    onboard.add_argument("--hour", type=int, default=6)
    onboard.add_argument("--minute", type=int, default=0)
    onboard.add_argument("--lookback-days", type=int, default=3)
    whoop_commands.add_parser("disconnect", help="Revoke WHOOP access and clear the local OAuth token")
    whoop_commands.add_parser("status", help="Show secret-free WHOOP connection and coverage status")

    imports = commands.add_parser("import", help="Append an owner-provided health export")
    import_commands = imports.add_subparsers(dest="import_command", required=True)
    whoop_export = import_commands.add_parser("whoop-export", help="Import an official WHOOP data-export ZIP")
    import_source = whoop_export.add_mutually_exclusive_group(required=True)
    import_source.add_argument("--stdin", action="store_true", help="Read the ZIP bytes from stdin")
    import_source.add_argument("--input", type=Path, help="Read the ZIP from this explicit local path")
    whoop_evidence = import_commands.add_parser(
        "whoop-evidence",
        help="Import one PNG/JPEG WHOOP screenshot as manual image evidence",
    )
    whoop_evidence.add_argument("--stdin", action="store_true", required=True)
    whoop_evidence.add_argument("--media-type", choices=["image/png", "image/jpeg"], required=True)

    pull = commands.add_parser("pull", help="Append a provider pull")
    pull.add_argument("provider", choices=["whoop"])
    pull_window = pull.add_mutually_exclusive_group()
    pull_window.add_argument("--lookback-days", type=int, default=3)
    pull_window.add_argument(
        "--all-history",
        action="store_true",
        help="Pull every available collection page through the current time",
    )

    runs = commands.add_parser("runs", help="List capture runs")
    runs.add_argument("--provider")
    runs.add_argument("--limit", type=int, default=20)
    records = commands.add_parser("records", help="List raw response records")
    records.add_argument("--provider")
    records.add_argument("--run-id")
    records.add_argument("--limit", type=int, default=50)
    read = commands.add_parser("read", help="Read a bounded raw record chunk")
    read.add_argument("record_id")
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--max-bytes", type=int, default=65_536)

    commands.add_parser("mcp", help="Serve read-only health tools over stdio")

    schedule = commands.add_parser("schedule", help="Manage the daily macOS WHOOP pull")
    schedule_commands = schedule.add_subparsers(dest="schedule_command", required=True)
    install = schedule_commands.add_parser("install")
    install.add_argument("--provider", choices=["whoop"], default="whoop")
    install.add_argument("--hour", type=int, default=6)
    install.add_argument("--minute", type=int, default=0)
    install.add_argument("--lookback-days", type=int, default=3)
    schedule_commands.add_parser("status")
    schedule_commands.add_parser("uninstall")
    return parser


def _configure(
    args: argparse.Namespace,
    store: CredentialStore,
    stdout: TextIO,
    stdin: TextIO,
) -> int:
    if args.json_stdin:
        try:
            payload = json.loads(stdin.read())
        except json.JSONDecodeError:
            raise CredentialError("WHOOP client configuration stdin is invalid JSON") from None
        if not isinstance(payload, dict):
            raise CredentialError("WHOOP client configuration stdin must be an object")
        allowed = {"client_id", "client_secret", "redirect_uri", "scopes"}
        if set(payload) - allowed:
            raise CredentialError("WHOOP client configuration contains unsupported fields")
        client_id = str(payload.get("client_id") or "").strip()
        client_secret = str(payload.get("client_secret") or "").strip()
        redirect_uri = str(payload.get("redirect_uri") or "").strip()
        scopes_value = payload.get("scopes")
        if scopes_value is not None and (
            not isinstance(scopes_value, list) or not all(isinstance(item, str) for item in scopes_value)
        ):
            raise CredentialError("WHOOP client scopes must be a JSON string array")
        scopes = list(scopes_value) if scopes_value is not None else list(DEFAULT_WHOOP_SCOPES)
    else:
        client_id = args.client_id or input("WHOOP client ID: ").strip()
        client_secret = getpass.getpass("WHOOP client secret: ").strip()
        redirect_uri = args.redirect_uri or input("WHOOP registered redirect URI: ").strip()
        scopes = args.scopes or list(DEFAULT_WHOOP_SCOPES)
    store.save_client(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes,
    )
    if args.json_stdin:
        _json({"status": "configured", "requested_scopes": scopes}, stdout)
    else:
        stdout.write(f"WHOOP OAuth client saved privately. Requested scopes: {' '.join(scopes)}\n")
    return 0


def _private_line(stdin: TextIO, *, label: str, max_chars: int = 16_384) -> str:
    value = stdin.readline(max_chars + 2)
    if len(value) > max_chars + 1 or (len(value) == max_chars + 1 and not value.endswith("\n")):
        raise CredentialError(f"{label} exceeds the safe input limit")
    value = value.strip()
    if not value:
        raise CredentialError(f"{label} is required")
    return value


def _onboard(
    args: argparse.Namespace,
    *,
    archive: RawArchive,
    store: CredentialStore,
    stdout: TextIO,
    stdin: TextIO,
) -> int:
    with PullLock(args.root / "state" / "whoop.onboarding.lock"):
        return _onboard_locked(
            args,
            archive=archive,
            store=store,
            stdout=stdout,
            stdin=stdin,
        )


def _onboard_locked(
    args: argparse.Namespace,
    *,
    archive: RawArchive,
    store: CredentialStore,
    stdout: TextIO,
    stdin: TextIO,
) -> int:
    receipts = WhoopOnboardingStore(args.root)
    client = WhoopClient(archive=archive, credentials=store)
    callback_url = _private_line(stdin, label="WHOOP callback URL")
    receipts.update(phase="authorization", status="running")
    try:
        client.complete_authorization(callback_url)
    except CredentialError:
        receipts.update(phase="authorization", status="failed", error_code="authorization_failed")
        raise
    receipts.update(phase="history_import", status="running")
    pull_error: CredentialError | LockBusyError | WhoopError | None = None
    try:
        result = client.pull(start=None, end=utc_now())
    except (CredentialError, LockBusyError, WhoopError) as error:
        pull_error = error

    # Install the RunAtLoad schedule only after the initial pull releases its lock. Installing it
    # first can race the backfill and make either process fail as a concurrent pull.
    scheduler = HealthScheduler(root=args.root)
    schedule_installed = True
    try:
        scheduler.install(
            provider="whoop",
            hour=args.hour,
            minute=args.minute,
            lookback_days=args.lookback_days,
        )
    except (ScheduleError, ValueError):
        schedule_installed = False

    if pull_error is not None:
        receipts.update(phase="history_import", status="failed", error_code="history_import_failed")
        raise pull_error

    output = {
        "status": result.status,
        "resource_results": result.resource_results,
        "record_count": result.record_count,
        "resource_item_counts": result.resource_item_counts,
        "item_count": result.item_count,
        "daily_correction": {
            "installed": schedule_installed,
            "hour": args.hour,
            "minute": args.minute,
            "lookback_days": args.lookback_days,
        },
    }
    if result.status == "complete" and schedule_installed:
        receipts.update(phase="ready", status="completed")
        _json(output, stdout)
        return 0
    if result.status == "complete":
        receipts.update(phase="schedule", status="failed", error_code="schedule_install_failed")
        _json(output, stdout)
        return 1
    error_code = "history_partial" if result.status == "partial" else "history_failed"
    receipts.update(phase="history_import", status="failed", error_code=error_code)
    _json(output, stdout)
    return 1


def run(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO, stdin: TextIO = sys.stdin) -> int:
    archive = RawArchive(args.root)
    store = CredentialStore(args.root)
    if args.command == "whoop":
        if args.whoop_command == "configure":
            return _configure(args, store, stdout, stdin)
        if args.whoop_command == "status":
            _json(
                build_whoop_status(
                    archive=archive,
                    credentials=store,
                    scheduler=HealthScheduler(root=args.root),
                ),
                stdout,
            )
            return 0
        client = WhoopClient(archive=archive, credentials=store)
        if args.whoop_command == "disconnect":
            client.revoke_access()
            stdout.write("WHOOP access revoked and local OAuth token removed. Historical archives were retained.\n")
            return 0
        if args.whoop_command == "onboard":
            return _onboard(
                args,
                archive=archive,
                store=store,
                stdout=stdout,
                stdin=stdin,
            )
        callback_url = (
            _private_line(stdin, label="WHOOP callback URL") if args.callback_stdin else args.callback_url
        )
        if callback_url:
            client.complete_authorization(callback_url)
            if args.json:
                _json({"status": "authorized"}, stdout)
            else:
                stdout.write("WHOOP authorization completed; rotating token stored privately.\n")
        else:
            url = client.begin_authorization()
            if args.json:
                _json({"status": "authorization_pending", "authorization_url": url}, stdout)
            else:
                stdout.write("Open this WHOOP authorization URL, then rerun with --callback-url using the final redirect URL:\n")
                stdout.write(url + "\n")
        return 0
    if args.command == "pull":
        if not args.all_history and not 1 <= args.lookback_days <= 365:
            raise WhoopError("lookback days must be between 1 and 365")
        end = utc_now()
        start = None if args.all_history else end - timedelta(days=args.lookback_days)
        client = WhoopClient(archive=archive, credentials=store)
        result = client.pull(start=start, end=end)
        _json(
            {
                "run_id": result.run_id,
                "status": result.status,
                "resource_results": result.resource_results,
                "record_count": result.record_count,
                "resource_item_counts": result.resource_item_counts,
                "item_count": result.item_count,
            },
            stdout,
        )
        return 0 if result.status == "complete" else 1
    if args.command == "import":
        source = getattr(stdin, "buffer", stdin)
        if args.stdin:
            body = source.read()
            if isinstance(body, str):
                body = body.encode("utf-8")
        else:
            body = args.input.read_bytes()
        if args.import_command == "whoop-export":
            result = WhoopExportImporter(archive=archive).import_bundle(body)
            _json(
                {
                    "run_id": result.run_id,
                    "status": result.status,
                    "record_count": result.record_count,
                    "file_count": result.file_count,
                    "resource_file_counts": result.resource_file_counts,
                },
                stdout,
            )
        elif args.import_command == "whoop-evidence":
            result = WhoopEvidenceImporter(archive=archive).import_image(
                body,
                media_type=args.media_type,
            )
            _json(
                {
                    "run_id": result.run_id,
                    "status": result.status,
                    "record_count": result.record_count,
                    "item_count": result.item_count,
                },
                stdout,
            )
        else:
            raise RuntimeError("unreachable import command")
        return 0
    if args.command == "runs":
        _json({"runs": archive.list_runs(provider=args.provider, limit=args.limit)}, stdout)
        return 0
    if args.command == "records":
        _json(
            {
                "records": archive.list_records(
                    provider=args.provider,
                    run_id=args.run_id,
                    limit=args.limit,
                )
            },
            stdout,
        )
        return 0
    if args.command == "read":
        _json(archive.read_record(args.record_id, offset=args.offset, max_bytes=args.max_bytes), stdout)
        return 0
    if args.command == "mcp":
        return serve(archive, stdin=sys.stdin, stdout=stdout)
    if args.command == "schedule":
        scheduler = HealthScheduler(root=args.root)
        if args.schedule_command == "install":
            path = scheduler.install(
                provider=args.provider,
                hour=args.hour,
                minute=args.minute,
                lookback_days=args.lookback_days,
            )
            stdout.write(f"Daily WHOOP pull installed: {path}\n")
            return 0
        if args.schedule_command == "status":
            _json(scheduler.status(), stdout)
            return 0
        removed = scheduler.uninstall()
        stdout.write("Daily WHOOP pull removed.\n" if removed else "No daily WHOOP pull was installed.\n")
        return 0
    raise RuntimeError("unreachable command")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args, stdout=sys.stdout, stderr=sys.stderr)
    except (
        ArchiveError,
        CredentialError,
        LockBusyError,
        ScheduleError,
        WhoopError,
        WhoopExportError,
        WhoopEvidenceError,
        OSError,
        ValueError,
    ) as error:
        sys.stderr.write(f"error: {error}\n")
        return 2
