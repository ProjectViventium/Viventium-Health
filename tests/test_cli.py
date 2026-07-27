from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from viventium_health.cli import build_parser, run


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


if __name__ == "__main__":
    unittest.main()
