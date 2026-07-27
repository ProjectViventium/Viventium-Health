"""Operator CLI for WHOOP acquisition and read-only archive access."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Sequence, TextIO

from . import __version__
from .archive import ArchiveError, RawArchive, default_root, utc_now
from .auth import DEFAULT_WHOOP_SCOPES, CredentialError, CredentialStore
from .lock import LockBusyError
from .mcp import serve
from .schedule import HealthScheduler, ScheduleError
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
    configure.add_argument("--client-secret")
    configure.add_argument("--redirect-uri")
    configure.add_argument("--scope", action="append", dest="scopes")
    connect = whoop_commands.add_parser("connect", help="Begin or complete WHOOP owner authorization")
    connect.add_argument("--callback-url", help="Final registered redirect URL containing code and state")

    pull = commands.add_parser("pull", help="Append a provider correction-window pull")
    pull.add_argument("provider", choices=["whoop"])
    pull.add_argument("--lookback-days", type=int, default=3)

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


def _configure(args: argparse.Namespace, store: CredentialStore, stdout: TextIO) -> int:
    client_id = args.client_id or input("WHOOP client ID: ").strip()
    client_secret = args.client_secret or getpass.getpass("WHOOP client secret: ").strip()
    redirect_uri = args.redirect_uri or input("WHOOP registered redirect URI: ").strip()
    scopes = args.scopes or list(DEFAULT_WHOOP_SCOPES)
    store.save_client(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes,
    )
    stdout.write(f"WHOOP OAuth client saved privately. Requested scopes: {' '.join(scopes)}\n")
    return 0


def run(args: argparse.Namespace, *, stdout: TextIO, stderr: TextIO) -> int:
    archive = RawArchive(args.root)
    store = CredentialStore(args.root)
    if args.command == "whoop":
        if args.whoop_command == "configure":
            return _configure(args, store, stdout)
        client = WhoopClient(archive=archive, credentials=store)
        if args.callback_url:
            client.complete_authorization(args.callback_url)
            stdout.write("WHOOP authorization completed; rotating token stored privately.\n")
        else:
            url = client.begin_authorization()
            stdout.write("Open this WHOOP authorization URL, then rerun with --callback-url using the final redirect URL:\n")
            stdout.write(url + "\n")
        return 0
    if args.command == "pull":
        if not 1 <= args.lookback_days <= 365:
            raise WhoopError("lookback days must be between 1 and 365")
        end = utc_now()
        client = WhoopClient(archive=archive, credentials=store)
        result = client.pull(start=end - timedelta(days=args.lookback_days), end=end)
        _json(
            {
                "run_id": result.run_id,
                "status": result.status,
                "resource_results": result.resource_results,
                "record_count": result.record_count,
            },
            stdout,
        )
        return 0 if result.status == "complete" else 1
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
    except (ArchiveError, CredentialError, LockBusyError, ScheduleError, WhoopError, ValueError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 2
