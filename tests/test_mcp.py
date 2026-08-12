from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import base64
from datetime import datetime, timezone
from pathlib import Path

from viventium_health.archive import RawArchive
from viventium_health.evidence import WhoopEvidenceImporter


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class McpSubprocessTests(unittest.TestCase):
    def test_read_only_tools_work_over_clean_stdio_json_rpc(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "health"
            archive = RawArchive(root)
            now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
            run = archive.start_run(
                provider="whoop",
                requested_start="2026-07-25T00:00:00Z",
                requested_end="2026-07-26T00:00:00Z",
                resources=["cycles"],
                started_at=now,
            )
            record = archive.record_response(
                run,
                resource="cycles",
                body=b'{"records":[{"opaque":true}]}',
                status=200,
                content_type="application/json",
                request_path="/developer/v2/cycle",
                fetched_at=now,
            )
            archive.finish_run(
                run,
                status="complete",
                resource_results={"cycles": "complete"},
                finished_at=now,
            )
            evidence = WhoopEvidenceImporter(archive=archive, clock=lambda: now).import_image(
                PNG_1X1,
                media_type="image/png",
            )
            evidence_record = archive.list_records(run_id=evidence.run_id)[0]
            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "qa", "version": "1"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "health_list_records", "arguments": {"provider": "whoop"}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "health_read_record",
                        "arguments": {"record_id": record["record_id"], "offset": 0, "max_bytes": 8},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "health_read_record", "arguments": {"record_id": "../../private"}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "health_read_image",
                        "arguments": {"record_id": evidence_record["record_id"]},
                    },
                },
                {"jsonrpc": "2.0", "method": "tools/list", "params": {}},
            ]
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            process = subprocess.run(
                [sys.executable, "-m", "viventium_health", "--root", str(root), "mcp"],
                input="".join(json.dumps(message) + "\n" for message in messages),
                text=True,
                capture_output=True,
                env=environment,
                timeout=10,
                check=False,
            )

            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stderr, "")
            responses = [json.loads(line) for line in process.stdout.splitlines()]
            self.assertEqual([response["id"] for response in responses], [1, 2, 3, 4, 5, 6])
            self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
            tools = responses[1]["result"]["tools"]
            self.assertEqual(
                {tool["name"] for tool in tools},
                {"health_list_runs", "health_list_records", "health_read_record", "health_read_image"},
            )
            self.assertNotIn("path", json.dumps(responses[2]))
            self.assertEqual(responses[3]["result"]["structuredContent"]["data"], '{"record')
            self.assertTrue(responses[4]["result"]["isError"])
            self.assertNotIn("/private", json.dumps(responses[4]))
            image_result = responses[5]["result"]
            self.assertEqual(image_result["content"][0]["type"], "image")
            self.assertEqual(image_result["content"][0]["mimeType"], "image/png")
            self.assertEqual(base64.b64decode(image_result["content"][0]["data"]), PNG_1X1)
            self.assertNotIn("data", image_result["structuredContent"])


if __name__ == "__main__":
    unittest.main()
