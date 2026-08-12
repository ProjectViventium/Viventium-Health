from __future__ import annotations

import io
import stat
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from viventium_health.archive import RawArchive
from viventium_health.importer import WhoopExportError, WhoopExportImporter


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def make_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return output.getvalue()


class WhoopExportImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "health"
        self.archive = RawArchive(self.root)
        self.importer = WhoopExportImporter(archive=self.archive, clock=lambda: NOW)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_official_export_bundle_is_preserved_and_each_csv_is_model_readable(self) -> None:
        files = {
            "Physiological Cycles.csv": b"Cycle start time,Recovery score\n2026-08-09,78\n",
            "Sleeps.csv": b"Cycle start time,Sleep performance %\n2026-08-09,91\n",
            "Workouts.csv": b"Cycle start time,Activity name\n2026-08-09,Running\n",
            "Journal Entries.csv": b"Cycle start time,Question text,Answered yes\n2026-08-09,Caffeine?,true\n",
            "Future WHOOP Data.csv": b"new_field\nkept exactly\n",
        }
        bundle = make_zip(files)

        result = self.importer.import_bundle(bundle)

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.file_count, 5)
        self.assertEqual(result.record_count, 6)
        self.assertEqual(result.resource_file_counts["journal_entries"], 1)
        records = self.archive.list_records(provider="whoop", run_id=result.run_id, limit=20)
        self.assertEqual(
            {record["resource"] for record in records},
            {
                "export_bundle",
                "physiological_cycles",
                "sleeps",
                "workouts",
                "journal_entries",
                "export_file",
            },
        )
        bundle_record = next(record for record in records if record["resource"] == "export_bundle")
        self.assertEqual(
            self.archive.read_record(bundle_record["record_id"], max_bytes=len(bundle))["data"],
            __import__("base64").b64encode(bundle).decode("ascii"),
        )
        journal = next(record for record in records if record["resource"] == "journal_entries")
        journal_body = self.archive.read_record(journal["record_id"], max_bytes=10_000)
        self.assertEqual(journal_body["encoding"], "utf-8")
        self.assertEqual(journal_body["data"].encode(), files["Journal Entries.csv"])
        self.assertTrue(journal_body["integrity_matches"])

    def test_path_traversal_and_links_are_rejected_before_any_archive_run(self) -> None:
        traversal = make_zip({"../Sleeps.csv": b"private"})
        with self.assertRaisesRegex(WhoopExportError, "unsafe entry"):
            self.importer.import_bundle(traversal)
        self.assertEqual(self.archive.list_runs(provider="whoop", limit=10), [])

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            link = zipfile.ZipInfo("Sleeps.csv")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, b"/private/target")
        with self.assertRaisesRegex(WhoopExportError, "regular files"):
            self.importer.import_bundle(output.getvalue())
        self.assertEqual(self.archive.list_runs(provider="whoop", limit=10), [])

    def test_non_zip_and_oversized_expansion_fail_closed(self) -> None:
        with self.assertRaisesRegex(WhoopExportError, "ZIP"):
            self.importer.import_bundle(b"not-a-zip")

        constrained = WhoopExportImporter(
            archive=self.archive,
            clock=lambda: NOW,
            max_expanded_bytes=10,
        )
        with self.assertRaisesRegex(WhoopExportError, "expanded size"):
            constrained.import_bundle(make_zip({"Sleeps.csv": b"x" * 11}))
        self.assertEqual(self.archive.list_runs(provider="whoop", limit=10), [])

    def test_exact_duplicate_bundle_reuses_the_existing_archive_run(self) -> None:
        bundle = make_zip({"Sleeps.csv": b"start,sleep\n2026-08-09,91\n"})
        first = self.importer.import_bundle(bundle)

        second = self.importer.import_bundle(bundle)

        self.assertEqual(second.status, "already_imported")
        self.assertEqual(second.run_id, first.run_id)
        self.assertEqual(second.record_count, first.record_count)
        self.assertEqual(len(self.archive.list_runs(provider="whoop", limit=10)), 1)


if __name__ == "__main__":
    unittest.main()
