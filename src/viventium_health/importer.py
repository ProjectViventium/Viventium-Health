"""Bounded importer for exact official WHOOP data-export bundles."""

from __future__ import annotations

import io
import hashlib
import re
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Callable

from .archive import RawArchive, format_timestamp, utc_now


class WhoopExportError(RuntimeError):
    """Safe failure while validating an owner-provided WHOOP export."""


@dataclass(frozen=True)
class ImportResult:
    run_id: str
    status: str
    record_count: int
    file_count: int
    resource_file_counts: dict[str, int]


_OFFICIAL_EXPORT_RESOURCES = {
    "physiologicalcycles": "physiological_cycles",
    "sleeps": "sleeps",
    "workouts": "workouts",
    "journalentries": "journal_entries",
}


def _resource_for_name(name: str) -> str:
    stem = PurePosixPath(name).name.rsplit(".", 1)[0]
    normalized = re.sub(r"[^a-z0-9]", "", stem.casefold())
    return _OFFICIAL_EXPORT_RESOURCES.get(normalized, "export_file")


class WhoopExportImporter:
    """Preserve a WHOOP export ZIP and every contained regular file without normalization."""

    def __init__(
        self,
        *,
        archive: RawArchive,
        clock: Callable[[], datetime] = utc_now,
        max_bundle_bytes: int = 100 * 1024 * 1024,
        max_entries: int = 128,
        max_entry_bytes: int = 128 * 1024 * 1024,
        max_expanded_bytes: int = 256 * 1024 * 1024,
    ) -> None:
        self.archive = archive
        self.clock = clock
        self.max_bundle_bytes = max_bundle_bytes
        self.max_entries = max_entries
        self.max_entry_bytes = max_entry_bytes
        self.max_expanded_bytes = max_expanded_bytes

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or "\x00" in name or "\\" in name:
            raise WhoopExportError("WHOOP export contains an unsafe entry name")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise WhoopExportError("WHOOP export contains an unsafe entry path")

    @staticmethod
    def _is_regular_file(info: zipfile.ZipInfo) -> bool:
        if info.is_dir():
            return False
        if info.create_system != 3:
            return True
        mode = info.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        return file_type in {0, stat.S_IFREG}

    def _validated_files(self, bundle: bytes) -> list[zipfile.ZipInfo]:
        if not isinstance(bundle, bytes) or not bundle:
            raise WhoopExportError("WHOOP export ZIP is empty")
        if len(bundle) > self.max_bundle_bytes:
            raise WhoopExportError("WHOOP export ZIP exceeds the upload size limit")
        if not zipfile.is_zipfile(io.BytesIO(bundle)):
            raise WhoopExportError("WHOOP export must be the official ZIP bundle")
        try:
            with zipfile.ZipFile(io.BytesIO(bundle)) as zipped:
                entries = zipped.infolist()
        except (OSError, zipfile.BadZipFile):
            raise WhoopExportError("WHOOP export ZIP is unreadable") from None
        if len(entries) > self.max_entries:
            raise WhoopExportError("WHOOP export ZIP contains too many entries")
        total = 0
        files: list[zipfile.ZipInfo] = []
        for info in entries:
            self._validate_name(info.filename)
            if info.flag_bits & 0x1:
                raise WhoopExportError("encrypted WHOOP export entries are unsupported")
            if info.is_dir():
                continue
            if not self._is_regular_file(info):
                raise WhoopExportError("WHOOP export may contain regular files only")
            if info.file_size < 0 or info.file_size > self.max_entry_bytes:
                raise WhoopExportError("WHOOP export entry exceeds the expanded size limit")
            total += info.file_size
            if total > self.max_expanded_bytes:
                raise WhoopExportError("WHOOP export exceeds the expanded size limit")
            files.append(info)
        if not files:
            raise WhoopExportError("WHOOP export ZIP contains no files")
        return files

    def import_bundle(self, bundle: bytes) -> ImportResult:
        files = self._validated_files(bundle)
        existing = self.archive.find_record_by_sha256(
            provider="whoop",
            resource="export_bundle",
            sha256=hashlib.sha256(bundle).hexdigest(),
        )
        if existing and isinstance(existing.get("run_id"), str):
            records = self.archive.list_records(
                provider="whoop",
                run_id=existing["run_id"],
                limit=1000,
            )
            resource_counts: dict[str, int] = {}
            for record in records:
                resource = record.get("resource")
                if isinstance(resource, str) and resource != "export_bundle":
                    resource_counts[resource] = resource_counts.get(resource, 0) + 1
            return ImportResult(
                run_id=existing["run_id"],
                status="already_imported",
                record_count=len(records),
                file_count=sum(resource_counts.values()),
                resource_file_counts=resource_counts,
            )
        imported_at = self.clock()
        resources = sorted({"export_bundle", *(_resource_for_name(info.filename) for info in files)})
        run = self.archive.start_run(
            provider="whoop",
            requested_start=None,
            requested_end=format_timestamp(imported_at),
            resources=resources,
            started_at=imported_at,
        )
        self.archive.record_response(
            run,
            resource="export_bundle",
            body=bundle,
            status=200,
            content_type="application/zip",
            request_method="IMPORT",
            request_path="/official-export/bundle",
            fetched_at=imported_at,
        )
        resource_counts: dict[str, int] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(bundle)) as zipped:
                for page, info in enumerate(files, start=1):
                    body = zipped.read(info)
                    if len(body) != info.file_size:
                        raise WhoopExportError("WHOOP export entry size did not match its manifest")
                    resource = _resource_for_name(info.filename)
                    resource_counts[resource] = resource_counts.get(resource, 0) + 1
                    media_type = "text/csv" if info.filename.casefold().endswith(".csv") else "application/octet-stream"
                    self.archive.record_response(
                        run,
                        resource=resource,
                        body=body,
                        status=200,
                        content_type=media_type,
                        request_method="IMPORT",
                        request_path=f"/official-export/{resource}",
                        page=page,
                        fetched_at=imported_at,
                    )
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            self.archive.finish_run(
                run,
                status="failed",
                resource_results={resource: "import_failed" for resource in resources},
                finished_at=self.clock(),
            )
            if isinstance(error, WhoopExportError):
                raise
            raise WhoopExportError("WHOOP export ZIP could not be read safely") from None
        self.archive.finish_run(
            run,
            status="complete",
            resource_results={resource: "complete" for resource in resources},
            finished_at=self.clock(),
        )
        return ImportResult(
            run_id=run.run_id,
            status="complete",
            record_count=self.archive.count_run_records(run),
            file_count=len(files),
            resource_file_counts=resource_counts,
        )
