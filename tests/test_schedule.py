from __future__ import annotations

import plistlib
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from viventium_health.archive import RawArchive
from viventium_health.auth import CredentialStore
from viventium_health.schedule import HealthScheduler


class FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ScheduleTests(unittest.TestCase):
    def test_install_is_explicit_private_and_contains_no_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "health"
            RawArchive(root)
            credentials = CredentialStore(root)
            credentials.save_client(
                client_id="public-id",
                client_secret="never-in-plist",
                redirect_uri="https://example.com/callback",
                scopes=["read:cycles", "offline"],
            )
            credentials.save_token(
                {
                    "access_token": "never-in-plist-access",
                    "refresh_token": "never-in-plist-refresh",
                    "expires_in": 3600,
                },
                obtained_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            )
            calls: list[list[str]] = []

            def runner(arguments, **kwargs):
                calls.append(list(arguments))
                return FakeCompleted()

            scheduler = HealthScheduler(
                root=root,
                executable="/path/to/python3",
                launch_agents_dir=base / "LaunchAgents",
                runner=runner,
                platform_name="Darwin",
                uid=501,
            )
            path = scheduler.install(provider="whoop", hour=6, minute=15, lookback_days=3)

            raw = path.read_bytes()
            self.assertNotIn(b"never-in-plist", raw)
            job = plistlib.loads(raw)
            self.assertEqual(job["StartCalendarInterval"], {"Hour": 6, "Minute": 15})
            self.assertTrue(job["RunAtLoad"])
            self.assertEqual(
                job["ProgramArguments"],
                [
                    "/path/to/python3",
                    "-m",
                    "viventium_health",
                    "--root",
                    str(root),
                    "pull",
                    "whoop",
                    "--lookback-days",
                    "3",
                ],
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertTrue(any(call[:3] == ["launchctl", "bootstrap", "gui/501"] for call in calls))

            status = scheduler.status()
            self.assertTrue(status["configured"])
            self.assertTrue(status["loaded"])
            scheduler.uninstall()
            self.assertFalse(path.exists())

    def test_render_rejects_invalid_schedule_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            scheduler = HealthScheduler(
                root=Path(temp) / "health",
                executable="python3",
                launch_agents_dir=Path(temp) / "agents",
                runner=lambda *args, **kwargs: FakeCompleted(),
                platform_name="Darwin",
                uid=501,
            )
            with self.assertRaises(ValueError):
                scheduler.render(provider="whoop", hour=24, minute=0, lookback_days=3)
            with self.assertRaises(ValueError):
                scheduler.render(provider="other", hour=6, minute=0, lookback_days=3)


if __name__ == "__main__":
    unittest.main()
