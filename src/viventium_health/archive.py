"""Append-only, exact-byte archive for provider responses."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_READ_BYTES = 1024 * 1024
_OPAQUE_ID = re.compile(r"^[0-9a-f]{32}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SENSITIVE_QUERY_FRAGMENTS = ("token", "secret", "code", "state", "authorization")
_SAFE_RESPONSE_HEADERS = {
    "content-type",
    "date",
    "etag",
    "last-modified",
    "retry-after",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
}


class ArchiveError(ValueError):
    """Raised when an archive operation is unsafe or invalid."""


@dataclass(frozen=True)
class RunHandle:
    """Internal handle for one immutable pull run."""

    run_id: str
    provider: str
    path: Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_root() -> Path:
    configured = os.environ.get("VIVENTIUM_HEALTH_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Library" / "Application Support" / "Viventium" / "health"


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ArchiveError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validate_slug(value: str, label: str) -> str:
    if not _SLUG.fullmatch(value):
        raise ArchiveError(f"invalid {label}: expected a lowercase opaque slug")
    return value


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _fingerprint(value: Any) -> dict[str, Any]:
    raw = str(value).encode("utf-8")
    return {
        "redacted": True,
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _safe_query(query: Mapping[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (query or {}).items():
        if any(fragment in key.lower() for fragment in _SENSITIVE_QUERY_FRAGMENTS):
            safe[key] = _fingerprint(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, tuple)):
            safe[key] = [item if isinstance(item, (str, int, float, bool)) or item is None else str(item) for item in value]
        else:
            safe[key] = str(value)
    return safe


def _safe_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    normalized = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    return {key: normalized[key] for key in sorted(_SAFE_RESPONSE_HEADERS) if key in normalized}


class RawArchive:
    """Preserve response bytes and immutable provenance without a database."""

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()
        self.archive_root = self.root / "archive"
        self.secrets_root = self.root / "secrets"
        self.logs_root = self.root / "logs"
        self.locks_root = self.root / "locks"
        for path in (self.root, self.archive_root, self.secrets_root, self.logs_root, self.locks_root):
            self._ensure_private_dir(path)

    @staticmethod
    def _ensure_private_dir(path: Path) -> None:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            descriptor = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    def _write_new(self, path: Path, body: bytes) -> None:
        """Atomically publish a new owner-only file without overwrite."""

        self._ensure_private_dir(path.parent)
        temporary = path.parent / f".{path.name}.tmp-{secrets.token_hex(8)}"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.link(temporary, path)
            self._fsync_directory(path.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def start_run(
        self,
        *,
        provider: str,
        requested_start: str,
        requested_end: str,
        resources: list[str],
        started_at: datetime | None = None,
    ) -> RunHandle:
        provider = _validate_slug(provider, "provider")
        for resource in resources:
            _validate_slug(resource, "resource")
        timestamp = started_at or utc_now()
        date_path = timestamp.astimezone(timezone.utc)
        run_id = f"{date_path.strftime('%Y%m%dT%H%M%S.%fZ')}-{secrets.token_hex(6)}"
        run_path = self.archive_root
        for component in (
            provider,
            date_path.strftime("%Y"),
            date_path.strftime("%m"),
            date_path.strftime("%d"),
            run_id,
        ):
            run_path /= component
            self._ensure_private_dir(run_path)
        receipt = {
            "schema_version": 1,
            "run_id": run_id,
            "provider": provider,
            "started_at": format_timestamp(timestamp),
            "requested_start": requested_start,
            "requested_end": requested_end,
            "resources": list(resources),
        }
        self._write_new(run_path / "run.started.json", _json_bytes(receipt))
        return RunHandle(run_id=run_id, provider=provider, path=run_path)

    def record_response(
        self,
        run: RunHandle,
        *,
        resource: str,
        body: bytes,
        status: int,
        content_type: str,
        response_headers: Mapping[str, str] | None = None,
        request_method: str = "GET",
        request_path: str,
        request_query: Mapping[str, Any] | None = None,
        attempt: int = 1,
        page: int = 1,
        fetched_at: datetime | None = None,
    ) -> dict[str, Any]:
        _validate_slug(resource, "resource")
        if not isinstance(body, bytes):
            raise ArchiveError("response body must be bytes")
        if attempt < 1 or page < 1:
            raise ArchiveError("attempt and page must be positive")
        record_id = secrets.token_hex(16)
        media_type = content_type.split(";", 1)[0].strip().lower()
        extension = "json" if media_type == "application/json" or media_type.endswith("+json") else "bin"
        body_path = run.path / f"{record_id}.body.{extension}"
        self._write_new(body_path, body)
        metadata: dict[str, Any] = {
            "schema_version": 1,
            "record_id": record_id,
            "run_id": run.run_id,
            "provider": run.provider,
            "resource": resource,
            "fetched_at": format_timestamp(fetched_at or utc_now()),
            "request": {
                "method": request_method.upper(),
                "path": request_path,
                "query": _safe_query(request_query),
            },
            "response": {
                "status": int(status),
                "content_type": content_type,
                "headers": _safe_headers(response_headers),
                "byte_length": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            },
            "attempt": attempt,
            "page": page,
        }
        self._write_new(run.path / f"{record_id}.meta.json", _json_bytes(metadata))
        return metadata

    def record_network_error(
        self,
        run: RunHandle,
        *,
        resource: str,
        request_path: str,
        request_query: Mapping[str, Any] | None,
        error: BaseException,
        attempt: int,
        page: int,
        fetched_at: datetime | None = None,
    ) -> dict[str, Any]:
        _validate_slug(resource, "resource")
        record_id = secrets.token_hex(16)
        metadata: dict[str, Any] = {
            "schema_version": 1,
            "record_id": record_id,
            "run_id": run.run_id,
            "provider": run.provider,
            "resource": resource,
            "fetched_at": format_timestamp(fetched_at or utc_now()),
            "request": {"method": "GET", "path": request_path, "query": _safe_query(request_query)},
            "error": {"class": type(error).__name__},
            "attempt": attempt,
            "page": page,
        }
        self._write_new(run.path / f"{record_id}.error.json", _json_bytes(metadata))
        return metadata

    def finish_run(
        self,
        run: RunHandle,
        *,
        status: str,
        resource_results: Mapping[str, str],
        finished_at: datetime | None = None,
    ) -> dict[str, Any]:
        if status not in {"complete", "partial", "failed"}:
            raise ArchiveError("run status must be complete, partial, or failed")
        receipt: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run.run_id,
            "provider": run.provider,
            "finished_at": format_timestamp(finished_at or utc_now()),
            "status": status,
            "resource_results": dict(resource_results),
        }
        self._write_new(run.path / "run.finished.json", _json_bytes(receipt))
        return receipt

    def list_runs(self, *, provider: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if provider is not None:
            _validate_slug(provider, "provider")
        if not 1 <= limit <= 1000:
            raise ArchiveError("limit must be between 1 and 1000")
        search_root = self.archive_root / provider if provider else self.archive_root
        if not search_root.exists():
            return []
        results: list[dict[str, Any]] = []
        for started_path in search_root.rglob("run.started.json"):
            try:
                started = json.loads(started_path.read_bytes())
                finished_path = started_path.with_name("run.finished.json")
                finished = json.loads(finished_path.read_bytes()) if finished_path.exists() else {}
            except (OSError, json.JSONDecodeError):
                continue
            results.append(
                {
                    "run_id": started.get("run_id"),
                    "provider": started.get("provider"),
                    "started_at": started.get("started_at"),
                    "finished_at": finished.get("finished_at"),
                    "status": finished.get("status", "incomplete"),
                    "requested_start": started.get("requested_start"),
                    "requested_end": started.get("requested_end"),
                    "resources": started.get("resources", []),
                    "resource_results": finished.get("resource_results", {}),
                }
            )
        results.sort(key=lambda item: (item.get("started_at") or "", item.get("run_id") or ""), reverse=True)
        return results[:limit]

    def list_records(
        self,
        *,
        provider: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if provider is not None:
            _validate_slug(provider, "provider")
        if run_id is not None and ("/" in run_id or "\\" in run_id or not run_id):
            raise ArchiveError("invalid run id")
        if not 1 <= limit <= 1000:
            raise ArchiveError("limit must be between 1 and 1000")
        search_root = self.archive_root / provider if provider else self.archive_root
        if not search_root.exists():
            return []
        results: list[dict[str, Any]] = []
        paths = list(search_root.rglob("*.meta.json")) + list(search_root.rglob("*.error.json"))
        for metadata_path in paths:
            try:
                metadata = json.loads(metadata_path.read_bytes())
            except (OSError, json.JSONDecodeError):
                continue
            if run_id is not None and metadata.get("run_id") != run_id:
                continue
            response = metadata.get("response", {})
            error = metadata.get("error")
            summary = {
                "record_id": metadata.get("record_id"),
                "run_id": metadata.get("run_id"),
                "provider": metadata.get("provider"),
                "resource": metadata.get("resource"),
                "fetched_at": metadata.get("fetched_at"),
                "status": response.get("status"),
                "byte_length": response.get("byte_length", 0),
                "sha256": response.get("sha256"),
                "attempt": metadata.get("attempt"),
                "page": metadata.get("page"),
            }
            if error:
                summary["error"] = error
            results.append(summary)
        results.sort(key=lambda item: (item.get("fetched_at") or "", item.get("record_id") or ""), reverse=True)
        return results[:limit]

    def _find_record_files(self, record_id: str) -> tuple[Path, Path]:
        if not _OPAQUE_ID.fullmatch(record_id):
            raise ArchiveError("invalid record id")
        metadata_paths = list(self.archive_root.rglob(f"{record_id}.meta.json"))
        if len(metadata_paths) != 1:
            raise ArchiveError("record not found")
        metadata_path = metadata_paths[0]
        body_paths = list(metadata_path.parent.glob(f"{record_id}.body.*"))
        if len(body_paths) != 1:
            raise ArchiveError("record body is missing or ambiguous")
        return metadata_path, body_paths[0]

    def read_record(self, record_id: str, *, offset: int = 0, max_bytes: int = 65_536) -> dict[str, Any]:
        if offset < 0:
            raise ArchiveError("offset must be non-negative")
        if not 1 <= max_bytes <= MAX_READ_BYTES:
            raise ArchiveError(f"max_bytes must be between 1 and {MAX_READ_BYTES}")
        metadata_path, body_path = self._find_record_files(record_id)
        metadata = json.loads(metadata_path.read_bytes())
        body = body_path.read_bytes()
        if offset > len(body):
            raise ArchiveError("offset exceeds record length")
        expected_hash = metadata["response"]["sha256"]
        integrity_matches = hashlib.sha256(body).hexdigest() == expected_hash
        end = min(len(body), offset + max_bytes)
        try:
            body.decode("utf-8")
            while end > offset:
                try:
                    data = body[offset:end].decode("utf-8")
                    break
                except UnicodeDecodeError:
                    end -= 1
            else:
                if offset != len(body):
                    raise ArchiveError("offset does not begin on a UTF-8 boundary")
                data = ""
            encoding = "utf-8"
        except UnicodeDecodeError:
            data = base64.b64encode(body[offset:end]).decode("ascii")
            encoding = "base64"
        return {
            "record_id": record_id,
            "provider": metadata.get("provider"),
            "resource": metadata.get("resource"),
            "fetched_at": metadata.get("fetched_at"),
            "status": metadata.get("response", {}).get("status"),
            "offset": offset,
            "next_offset": end,
            "total_bytes": len(body),
            "complete": end == len(body),
            "encoding": encoding,
            "data": data,
            "sha256": expected_hash,
            "integrity_matches": integrity_matches,
        }
