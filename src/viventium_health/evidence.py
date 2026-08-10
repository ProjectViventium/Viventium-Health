"""Exact, bounded import of owner-supplied WHOOP image evidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .archive import RawArchive, format_timestamp, utc_now
from .image import ImageValidationError, validate_image_bytes


MAX_EVIDENCE_BYTES = 10 * 1024 * 1024


class WhoopEvidenceError(ValueError):
    """Raised when manual WHOOP evidence is not a safe supported image."""


@dataclass(frozen=True)
class EvidenceImportResult:
    run_id: str
    status: str
    record_count: int
    item_count: int


class WhoopEvidenceImporter:
    """Preserve a PNG/JPEG exactly and label it as unstructured manual evidence."""

    def __init__(
        self,
        *,
        archive: RawArchive,
        max_image_bytes: int = MAX_EVIDENCE_BYTES,
        clock: Callable = utc_now,
    ) -> None:
        self.archive = archive
        self.max_image_bytes = max_image_bytes
        self.clock = clock

    def import_image(self, body: bytes, *, media_type: str) -> EvidenceImportResult:
        if not isinstance(body, bytes) or not body:
            raise WhoopEvidenceError("WHOOP evidence image is empty")
        if len(body) > self.max_image_bytes:
            raise WhoopEvidenceError("WHOOP evidence image exceeds the upload size limit")
        try:
            detected = validate_image_bytes(body)
        except ImageValidationError:
            raise WhoopEvidenceError("WHOOP evidence must be a valid PNG or JPEG image") from None
        if media_type.strip().lower() != detected:
            raise WhoopEvidenceError("WHOOP evidence must be a valid PNG or JPEG image")

        imported_at = self.clock()
        run = self.archive.start_run(
            provider="whoop",
            requested_start=None,
            requested_end=format_timestamp(imported_at),
            resources=["manual_evidence"],
            started_at=imported_at,
        )
        self.archive.record_response(
            run,
            resource="manual_evidence",
            body=body,
            status=200,
            content_type=detected,
            request_method="IMPORT",
            request_path="/manual-evidence/image",
            fetched_at=imported_at,
        )
        self.archive.finish_run(
            run,
            status="complete",
            resource_results={"manual_evidence": "complete"},
            resource_item_counts={"manual_evidence": 1},
            item_count=1,
            finished_at=self.clock(),
        )
        return EvidenceImportResult(
            run_id=run.run_id,
            status="complete",
            record_count=self.archive.count_run_records(run),
            item_count=1,
        )
