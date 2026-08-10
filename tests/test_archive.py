from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from viventium_health.archive import ArchiveError, RawArchive, RunHandle

NOW = datetime(2026, 7, 26, 12, 34, 56, 123456, tzinfo=timezone.utc)


class RawArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "health"
        self.archive = RawArchive(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def start_run(self):
        return self.archive.start_run(
            provider="whoop",
            requested_start="2026-07-23T00:00:00Z",
            requested_end="2026-07-26T12:34:56Z",
            resources=["cycles", "recovery"],
            started_at=NOW,
        )

    def test_exact_response_bytes_are_immutable_and_metadata_is_separate(self) -> None:
        run = self.start_run()
        body = b'{"opaque": [1, 2], "vendor_future_field": {"x": true}}\n'

        metadata = self.archive.record_response(
            run,
            resource="cycles",
            body=body,
            status=200,
            content_type="application/json; charset=utf-8",
            response_headers={"ETag": '"abc"', "Authorization": "must-not-survive"},
            request_path="/developer/v2/cycle",
            request_query={"start": "2026-07-23", "nextToken": "private-page-token"},
            attempt=1,
            page=1,
            fetched_at=NOW,
        )

        body_path = next(run.path.glob(f"{metadata['record_id']}.body.*"))
        meta_path = run.path / f"{metadata['record_id']}.meta.json"
        self.assertEqual(body_path.read_bytes(), body)
        self.assertEqual(metadata["response"]["sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(metadata["response"]["byte_length"], len(body))
        self.assertEqual(metadata["fetched_at"], "2026-07-26T12:34:56.123456Z")
        self.assertEqual(metadata["response"]["headers"], {"etag": '"abc"'})
        self.assertNotIn("private-page-token", meta_path.read_text())
        self.assertEqual(
            metadata["request"]["query"]["nextToken"],
            {
                "redacted": True,
                "length": len("private-page-token"),
                "sha256": hashlib.sha256(b"private-page-token").hexdigest(),
            },
        )

        for path in (self.root, run.path.parent, run.path):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        for path in (body_path, meta_path, run.path / "run.started.json"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

        with self.assertRaises(FileExistsError):
            self.archive._write_new(body_path, b"replacement")
        self.assertEqual(body_path.read_bytes(), body)

    def test_repeated_capture_appends_and_read_pages_by_opaque_id(self) -> None:
        first_run = self.start_run()
        first = self.archive.record_response(
            first_run,
            resource="recovery",
            body="snowman=☃;future=kept".encode(),
            status=200,
            content_type="text/plain",
            request_path="/developer/v2/recovery",
            fetched_at=NOW,
        )
        self.archive.finish_run(
            first_run,
            status="complete",
            resource_results={"recovery": "complete"},
            finished_at=NOW,
        )
        first_bytes = {
            path.name: path.read_bytes()
            for path in first_run.path.iterdir()
        }

        second_run = self.archive.start_run(
            provider="whoop",
            requested_start="2026-07-23T00:00:00Z",
            requested_end="2026-07-26T12:34:56Z",
            resources=["recovery"],
            started_at=NOW,
        )
        second = self.archive.record_response(
            second_run,
            resource="recovery",
            body=b"corrected-vendor-bytes",
            status=200,
            content_type="application/octet-stream",
            request_path="/developer/v2/recovery",
            fetched_at=NOW,
        )

        self.assertNotEqual(first["record_id"], second["record_id"])
        self.assertEqual(
            {path.name: path.read_bytes() for path in first_run.path.iterdir()},
            first_bytes,
        )

        records = self.archive.list_records(provider="whoop", limit=10)
        self.assertEqual({record["record_id"] for record in records}, {first["record_id"], second["record_id"]})
        self.assertTrue(all("path" not in record for record in records))

        page = self.archive.read_record(first["record_id"], offset=0, max_bytes=8)
        self.assertEqual(page["data"], "snowman=")
        self.assertEqual(page["encoding"], "utf-8")
        self.assertEqual(page["next_offset"], 8)
        self.assertFalse(page["complete"])

        rest = self.archive.read_record(first["record_id"], offset=8, max_bytes=1024)
        self.assertTrue(rest["complete"])
        self.assertEqual(page["data"].encode() + rest["data"].encode(), "snowman=☃;future=kept".encode())
        self.assertTrue(rest["integrity_matches"])

        with self.assertRaises(ArchiveError):
            self.archive.read_record("../../etc/passwd", offset=0, max_bytes=10)
        with self.assertRaises(ArchiveError):
            self.archive.read_record(first["record_id"], offset=-1, max_bytes=10)
        with self.assertRaises(ArchiveError):
            self.archive.read_record(first["record_id"], offset=0, max_bytes=1_048_577)

    def test_run_receipts_and_network_error_are_honest(self) -> None:
        run = self.start_run()
        error = self.archive.record_network_error(
            run,
            resource="cycles",
            request_path="/developer/v2/cycle",
            request_query={"start": "2026-07-23"},
            error=TimeoutError("synthetic timeout detail"),
            attempt=2,
            page=1,
            fetched_at=NOW,
        )
        self.assertEqual(error["error"]["class"], "TimeoutError")
        self.assertNotIn("synthetic timeout detail", json.dumps(error))
        self.assertFalse(list(run.path.glob(f"{error['record_id']}.body.*")))

        receipt = self.archive.finish_run(
            run,
            status="partial",
            resource_results={"cycles": "network_error", "recovery": "complete"},
            resource_item_counts={"cycles": 0, "recovery": 2},
            item_count=2,
            finished_at=NOW,
        )
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["item_count"], 2)
        runs = self.archive.list_runs(provider="whoop", limit=10)
        self.assertEqual(runs[0]["run_id"], run.run_id)
        self.assertEqual(runs[0]["status"], "partial")
        self.assertEqual(runs[0]["resource_item_counts"], {"cycles": 0, "recovery": 2})
        self.assertNotIn("path", runs[0])

        with self.assertRaises(FileExistsError):
            self.archive.finish_run(
                run,
                status="complete",
                resource_results={},
                finished_at=NOW,
            )

    def test_exact_run_record_count_is_scoped_and_rejects_external_paths(self) -> None:
        first = self.start_run()
        self.archive.record_response(
            first,
            resource="cycles",
            body=b'{"records":[]}',
            status=200,
            content_type="application/json",
            request_path="/developer/v2/cycle",
            fetched_at=NOW,
        )
        self.archive.record_network_error(
            first,
            resource="recovery",
            request_path="/developer/v2/recovery",
            request_query={},
            error=TimeoutError("synthetic"),
            attempt=1,
            page=1,
            fetched_at=NOW,
        )
        second = self.start_run()
        self.archive.record_response(
            second,
            resource="cycles",
            body=b'{"records":[1]}',
            status=200,
            content_type="application/json",
            request_path="/developer/v2/cycle",
            fetched_at=NOW,
        )

        self.assertEqual(self.archive.count_run_records(first), 2)
        self.assertEqual(self.archive.count_run_records(second), 1)
        with self.assertRaises(ArchiveError):
            self.archive.count_run_records(
                RunHandle(run_id="external", provider="whoop", path=Path(self.temp.name))
            )


if __name__ == "__main__":
    unittest.main()
