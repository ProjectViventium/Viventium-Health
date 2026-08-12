from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from viventium_health.auth import DEFAULT_WHOOP_SCOPES
from viventium_health.cli import build_parser, run
from viventium_health.lock import LockBusyError, PullLock
from viventium_health.schedule import ScheduleError


class CliSubprocessTests(unittest.TestCase):
    def run_cli(self, root: Path, *arguments: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        return subprocess.run(
            [sys.executable, "-m", "viventium_health", "--root", str(root), *arguments],
            input=stdin,
            text=True,
            capture_output=True,
            env=environment,
            timeout=10,
            check=False,
        )

    def test_configure_begin_connect_and_empty_inventory_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "health"
            parser = build_parser()
            configure_args = parser.parse_args(
                [
                    "--root",
                    str(root),
                    "whoop",
                    "configure",
                    "--client-id",
                    "public-client",
                    "--redirect-uri",
                    "https://example.com/callback",
                    "--scope",
                    "read:cycles",
                    "--scope",
                    "offline",
                ]
            )
            configured_stdout = StringIO()
            configured_stderr = StringIO()
            with patch("viventium_health.cli.getpass.getpass", return_value="private-secret"):
                self.assertEqual(
                    run(configure_args, stdout=configured_stdout, stderr=configured_stderr),
                    0,
                )
            self.assertNotIn("private-secret", configured_stdout.getvalue() + configured_stderr.getvalue())
            self.assertIn("read:cycles offline", configured_stdout.getvalue())
            with patch("sys.stderr", new=StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "--root",
                        str(root),
                        "whoop",
                        "configure",
                        "--client-secret",
                        "would-leak-in-process-list",
                    ]
                )

            connect = self.run_cli(root, "whoop", "connect")
            self.assertEqual(connect.returncode, 0, connect.stderr)
            self.assertIn("https://api.prod.whoop.com/oauth/oauth2/auth?", connect.stdout)
            self.assertNotIn("private-secret", connect.stdout + connect.stderr)

            runs = self.run_cli(root, "runs", "--provider", "whoop")
            self.assertEqual(runs.returncode, 0, runs.stderr)
            self.assertEqual(json.loads(runs.stdout), {"runs": []})

            missing_pull = self.run_cli(root, "pull", "whoop", "--lookback-days", "3")
            self.assertNotEqual(missing_pull.returncode, 0)
            self.assertIn("OAuth token is not configured", missing_pull.stderr)
            self.assertNotIn("private-secret", missing_pull.stdout + missing_pull.stderr)


class CliPullWindowTests(unittest.TestCase):
    def test_all_history_uses_an_open_start_window(self) -> None:
        now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
        parser = build_parser()
        args = parser.parse_args(["--root", "/tmp/health", "pull", "whoop", "--all-history"])
        stdout = StringIO()

        with (
            patch("viventium_health.cli.utc_now", return_value=now),
            patch("viventium_health.cli.WhoopClient") as client_class,
        ):
            client_class.return_value.pull.return_value = SimpleNamespace(
                run_id="synthetic-run",
                status="complete",
                resource_results={"cycles": "complete"},
                record_count=1,
                resource_item_counts={"cycles": 4},
                item_count=4,
            )

            self.assertEqual(run(args, stdout=stdout, stderr=StringIO()), 0)

        client_class.return_value.pull.assert_called_once_with(start=None, end=now)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "complete")
        self.assertEqual(json.loads(stdout.getvalue())["item_count"], 4)

    def test_all_history_and_lookback_are_mutually_exclusive(self) -> None:
        parser = build_parser()

        with patch("sys.stderr", new=StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(
                ["--root", "/tmp/health", "pull", "whoop", "--all-history", "--lookback-days", "30"]
            )


class CliPrivateInputTests(unittest.TestCase):
    def test_concurrent_onboarding_fails_closed_without_overwriting_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "health"
            args = build_parser().parse_args(
                ["--root", str(root), "whoop", "onboard", "--callback-stdin"]
            )
            lock_path = root / "state" / "whoop.onboarding.lock"

            with PullLock(lock_path), self.assertRaises(LockBusyError):
                run(
                    args,
                    stdout=StringIO(),
                    stderr=StringIO(),
                    stdin=StringIO("viventium://oauth/whoop?code=x&state=12345678\n"),
                )

            self.assertFalse((root / "state" / "whoop.onboarding.json").exists())

    def test_json_stdin_configures_all_official_read_scopes_without_echoing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "health"
            parser = build_parser()
            args = parser.parse_args(
                ["--root", str(root), "whoop", "configure", "--json-stdin"]
            )
            stdout = StringIO()
            stderr = StringIO()
            secret = "private-whoop-client-secret"

            self.assertEqual(
                run(
                    args,
                    stdout=stdout,
                    stderr=stderr,
                    stdin=StringIO(
                        json.dumps(
                            {
                                "client_id": "public-client",
                                "client_secret": secret,
                                "redirect_uri": "viventium://oauth/whoop",
                            }
                        )
                    ),
                ),
                0,
            )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "configured")
            self.assertEqual(payload["requested_scopes"], DEFAULT_WHOOP_SCOPES)
            self.assertNotIn(secret, stdout.getvalue() + stderr.getvalue())
            stored = json.loads((root / "secrets" / "whoop.client.json").read_text())
            self.assertEqual(stored["scopes"], DEFAULT_WHOOP_SCOPES)

    def test_status_command_is_machine_readable_before_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parser = build_parser()
            args = parser.parse_args(["--root", temp, "whoop", "status"])
            stdout = StringIO()

            self.assertEqual(run(args, stdout=stdout, stderr=StringIO()), 0)

            self.assertEqual(json.loads(stdout.getvalue())["state"], "setup_required")

    def test_connect_json_starts_a_browser_flow_without_exposing_client_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "health"
            parser = build_parser()
            configure = parser.parse_args(
                ["--root", str(root), "whoop", "configure", "--json-stdin"]
            )
            run(
                configure,
                stdout=StringIO(),
                stderr=StringIO(),
                stdin=StringIO(
                    json.dumps(
                        {
                            "client_id": "public-client",
                            "client_secret": "private-secret",
                            "redirect_uri": "viventium://oauth/whoop",
                        }
                    )
                ),
            )
            connect = parser.parse_args(["--root", str(root), "whoop", "connect", "--json"])
            stdout = StringIO()

            self.assertEqual(run(connect, stdout=stdout, stderr=StringIO()), 0)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "authorization_pending")
            self.assertTrue(payload["authorization_url"].startswith("https://api.prod.whoop.com/"))
            self.assertNotIn("private-secret", stdout.getvalue())

    def test_onboard_reads_callback_only_from_stdin_then_backfills_and_installs_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "health"
            parser = build_parser()
            args = parser.parse_args(
                ["--root", str(root), "whoop", "onboard", "--callback-stdin"]
            )
            callback = "viventium://oauth/whoop?code=private-code&state=Abc123Xy"
            stdout = StringIO()
            pull_result = SimpleNamespace(
                run_id="synthetic-run",
                status="complete",
                resource_results={"cycles": "complete"},
                record_count=1,
                resource_item_counts={"cycles": 5},
                item_count=5,
            )

            with (
                patch("viventium_health.cli.utc_now", return_value=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)),
                patch("viventium_health.cli.WhoopClient") as client_class,
                patch("viventium_health.cli.HealthScheduler") as scheduler_class,
            ):
                events: list[str] = []
                client_class.return_value.complete_authorization.side_effect = lambda _url: events.append(
                    "authorized"
                )
                client_class.return_value.pull.side_effect = lambda **_kwargs: (
                    events.append("history"),
                    pull_result,
                )[1]
                scheduler_class.return_value.install.side_effect = lambda **_kwargs: (
                    events.append("schedule"),
                    Path("/private/schedule"),
                )[1]

                self.assertEqual(
                    run(
                        args,
                        stdout=stdout,
                        stderr=StringIO(),
                        stdin=StringIO(callback + "\n"),
                    ),
                    0,
                )

            self.assertEqual(events, ["authorized", "history", "schedule"])

            client_class.return_value.complete_authorization.assert_called_once_with(callback)
            client_class.return_value.pull.assert_called_once_with(
                start=None,
                end=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
            )
            scheduler_class.return_value.install.assert_called_once_with(
                provider="whoop",
                hour=6,
                minute=0,
                lookback_days=3,
            )
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "complete")
            self.assertEqual(payload["item_count"], 5)
            self.assertNotIn(callback, stdout.getvalue())
            receipt = json.loads((root / "state" / "whoop.onboarding.json").read_text())
            self.assertEqual(receipt["phase"], "ready")
            self.assertEqual(receipt["status"], "completed")

    def test_onboard_keeps_daily_recovery_when_initial_history_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "health"
            args = build_parser().parse_args(
                ["--root", str(root), "whoop", "onboard", "--callback-stdin"]
            )
            pull_result = SimpleNamespace(
                run_id="synthetic-run",
                status="partial",
                resource_results={"cycles": "complete", "recovery": "http_503"},
                record_count=2,
                resource_item_counts={"cycles": 5, "recovery": 0},
                item_count=5,
            )

            with (
                patch("viventium_health.cli.WhoopClient") as client_class,
                patch("viventium_health.cli.HealthScheduler") as scheduler_class,
            ):
                client_class.return_value.pull.return_value = pull_result
                exit_code = run(
                    args,
                    stdout=StringIO(),
                    stderr=StringIO(),
                    stdin=StringIO("viventium://oauth/whoop?code=x&state=12345678\n"),
                )

            self.assertEqual(exit_code, 1)
            scheduler_class.return_value.install.assert_called_once()
            receipt = json.loads((root / "state" / "whoop.onboarding.json").read_text())
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["error_code"], "history_partial")

    def test_onboard_still_backfills_when_native_schedule_installation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "health"
            args = build_parser().parse_args(
                ["--root", str(root), "whoop", "onboard", "--callback-stdin"]
            )
            pull_result = SimpleNamespace(
                run_id="synthetic-run",
                status="complete",
                resource_results={"cycles": "complete"},
                record_count=1,
                resource_item_counts={"cycles": 5},
                item_count=5,
            )
            stdout = StringIO()

            with (
                patch("viventium_health.cli.WhoopClient") as client_class,
                patch("viventium_health.cli.HealthScheduler") as scheduler_class,
            ):
                client_class.return_value.pull.return_value = pull_result
                scheduler_class.return_value.install.side_effect = ScheduleError("synthetic")
                exit_code = run(
                    args,
                    stdout=stdout,
                    stderr=StringIO(),
                    stdin=StringIO("viventium://oauth/whoop?code=x&state=12345678\n"),
                )

            self.assertEqual(exit_code, 1)
            client_class.return_value.pull.assert_called_once()
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "complete")
            self.assertFalse(payload["daily_correction"]["installed"])
            receipt = json.loads((root / "state" / "whoop.onboarding.json").read_text())
            self.assertEqual(receipt["error_code"], "schedule_install_failed")


if __name__ == "__main__":
    unittest.main()
