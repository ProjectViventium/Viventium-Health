from __future__ import annotations

import base64
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from viventium_health.archive import ArchiveError, RawArchive
from viventium_health.evidence import WhoopEvidenceError, WhoopEvidenceImporter


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class WhoopEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "health"
        self.archive = RawArchive(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_preserves_a_bounded_stress_screenshot_and_makes_it_image_readable(self) -> None:
        result = WhoopEvidenceImporter(archive=self.archive, clock=lambda: NOW).import_image(
            PNG_1X1,
            media_type="image/png",
        )

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.item_count, 1)
        records = self.archive.list_records(provider="whoop")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["resource"], "manual_evidence")
        self.assertEqual(records[0]["content_type"], "image/png")
        image = self.archive.read_image_record(records[0]["record_id"])
        self.assertEqual(base64.b64decode(image["data"]), PNG_1X1)
        self.assertEqual(image["mimeType"], "image/png")
        self.assertTrue(image["integrity_matches"])

    def test_rejects_spoofed_or_oversized_evidence(self) -> None:
        importer = WhoopEvidenceImporter(archive=self.archive, max_image_bytes=len(PNG_1X1))

        with self.assertRaises(WhoopEvidenceError):
            importer.import_image(b"not-an-image", media_type="image/png")
        with self.assertRaises(WhoopEvidenceError):
            importer.import_image(PNG_1X1 + b"x", media_type="image/png")
        with self.assertRaises(WhoopEvidenceError):
            importer.import_image(PNG_1X1, media_type="image/svg+xml")
        oversized_dimensions = bytearray(PNG_1X1)
        oversized_dimensions[16:20] = (100_000).to_bytes(4, "big")
        with self.assertRaises(WhoopEvidenceError):
            WhoopEvidenceImporter(archive=self.archive).import_image(
                bytes(oversized_dimensions),
                media_type="image/png",
            )

    def test_generic_record_reader_cannot_relabel_non_images_as_images(self) -> None:
        run = self.archive.start_run(
            provider="whoop",
            requested_start=None,
            requested_end="2026-08-10T12:00:00.000000Z",
            resources=["export_file"],
            started_at=NOW,
        )
        record = self.archive.record_response(
            run,
            resource="export_file",
            body=b"private,csv\n",
            status=200,
            content_type="text/csv",
            request_method="IMPORT",
            request_path="/official-export/export_file",
            fetched_at=NOW,
        )

        with self.assertRaises(ArchiveError):
            self.archive.read_image_record(record["record_id"])


if __name__ == "__main__":
    unittest.main()
