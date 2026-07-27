from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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
            configured = self.run_cli(
                root,
                "whoop",
                "configure",
                "--client-id",
                "public-client",
                "--client-secret",
                "private-secret",
                "--redirect-uri",
                "https://example.com/callback",
                "--scope",
                "read:cycles",
                "--scope",
                "offline",
            )
            self.assertEqual(configured.returncode, 0, configured.stderr)
            self.assertNotIn("private-secret", configured.stdout + configured.stderr)
            self.assertIn("read:cycles offline", configured.stdout)

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


if __name__ == "__main__":
    unittest.main()
