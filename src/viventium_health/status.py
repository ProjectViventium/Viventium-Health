"""Secret-free WHOOP onboarding and coverage status."""

from __future__ import annotations

import json
import os
import re
import secrets
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .archive import RawArchive, format_timestamp, utc_now
from .auth import CredentialError, CredentialStore
from .whoop import WHOOP_RESOURCES


_SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
AUTHORIZATION_RECOVERY_STATUSES = frozenset(
    {"authorization_failed", "authorization_refresh_failed"}
)


class WhoopOnboardingStore:
    """Mutable, owner-only progress receipt; never stores callback URLs or credentials."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.state_root = self.root / "state"
        self.state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_root.chmod(0o700)
        self.path = self.state_root / "whoop.onboarding.json"

    def update(
        self,
        *,
        phase: str,
        status: str,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not _SAFE_CODE.fullmatch(phase):
            raise ValueError("WHOOP onboarding phase is invalid")
        if status not in {"running", "completed", "failed"}:
            raise ValueError("WHOOP onboarding status is invalid")
        if error_code is not None and not _SAFE_CODE.fullmatch(error_code):
            raise ValueError("WHOOP onboarding error code is invalid")
        payload: dict[str, Any] = {
            "schema_version": 1,
            "provider": "whoop",
            "phase": phase,
            "status": status,
            "updated_at": format_timestamp(now or utc_now()),
        }
        if error_code:
            payload["error_code"] = error_code
        body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        temporary = self.state_root / f".{self.path.name}.tmp-{secrets.token_hex(8)}"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return payload

    def load(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            return {"phase": "status", "status": "failed", "error_code": "receipt_unreadable"}
        if not isinstance(payload, dict):
            return {"phase": "status", "status": "failed", "error_code": "receipt_invalid"}
        return {
            key: payload[key]
            for key in ("phase", "status", "updated_at", "error_code")
            if key in payload
        }


def _load_client(credentials: CredentialStore) -> dict[str, Any] | None:
    try:
        return credentials.load_client()
    except CredentialError:
        return None


def _load_token(credentials: CredentialStore) -> dict[str, Any] | None:
    try:
        return credentials.load_token()
    except CredentialError:
        return None


def _schedule_status(scheduler: Any) -> dict[str, Any]:
    try:
        raw = scheduler.status()
    except Exception:
        return {"state": "unavailable", "configured": False, "loaded": False}
    configured = raw.get("configured") is True
    loaded = raw.get("loaded") is True
    supported = raw.get("platform_supported") is not False
    if loaded:
        state = "active"
    elif configured:
        state = "configured_inactive"
    elif not supported:
        state = "unsupported"
    else:
        state = "not_configured"
    return {"state": state, "configured": configured, "loaded": loaded}


def _public_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not run:
        return None
    return {
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "status": run.get("status"),
        "requested_start": run.get("requested_start"),
        "requested_end": run.get("requested_end"),
        "resources": list(run.get("resources") or []),
        "resource_results": dict(run.get("resource_results") or {}),
        "resource_item_counts": dict(run.get("resource_item_counts") or {}),
        "item_count": run.get("item_count"),
    }


def build_whoop_status(
    *,
    archive: RawArchive,
    credentials: CredentialStore,
    scheduler: Any,
    clock: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    now = clock()
    client = _load_client(credentials)
    token = _load_token(credentials)
    requested = list(client.get("scopes") or []) if client else []
    scope_value = token.get("scope") if token else None
    granted = scope_value.split() if isinstance(scope_value, str) else []
    runs = archive.list_runs(provider="whoop", limit=1000)
    api_resource_names = {resource.name for resource in WHOOP_RESOURCES}
    api_run = next(
        (run for run in runs if api_resource_names.intersection(run.get("resources") or [])),
        None,
    )
    export_run = next((run for run in runs if "export_bundle" in (run.get("resources") or [])), None)
    evidence_runs = [run for run in runs if "manual_evidence" in (run.get("resources") or [])]
    public_api_run = _public_run(api_run)
    public_export_run = _public_run(export_run)
    api_coverage: dict[str, Any] = {}
    for resource in WHOOP_RESOURCES:
        if not client:
            coverage_status = "setup_required"
        elif resource.scope not in granted:
            coverage_status = "not_granted"
        elif not api_run:
            coverage_status = "not_imported"
        else:
            coverage_status = (api_run.get("resource_results") or {}).get(resource.name, "not_imported")
        api_coverage[resource.name] = {
            "scope": resource.scope,
            "status": coverage_status,
            "items": (api_run.get("resource_item_counts") or {}).get(resource.name) if api_run else None,
        }
    export_coverage: dict[str, Any] = {}
    for resource in ("physiological_cycles", "sleeps", "workouts", "journal_entries"):
        status = "available_by_import"
        if export_run and resource in (export_run.get("resource_results") or {}):
            status = export_run["resource_results"][resource]
        export_coverage[resource] = {"status": status}
    onboarding = WhoopOnboardingStore(credentials.root).load()
    authorization_recovery_required = any(
        row.get("status") in AUTHORIZATION_RECOVERY_STATUSES
        for row in api_coverage.values()
    )
    pending_authorization = False
    if credentials.pending_path.exists() and not token:
        try:
            credentials.load_pending_state(now=now)
            pending_authorization = True
        except CredentialError:
            pending_authorization = False
    if not client:
        state = "setup_required"
    elif not token and onboarding and onboarding.get("status") == "failed":
        state = "degraded"
    elif pending_authorization:
        state = "authorization_pending"
    elif not token:
        state = "ready_to_authorize"
    elif onboarding and onboarding.get("status") == "running":
        state = "importing" if onboarding.get("phase") == "history_import" else "authorizing"
    elif api_run and api_run.get("status") == "complete":
        state = "connected"
    elif api_run:
        state = "degraded"
    else:
        state = "connected_no_data"
    return {
        "schema_version": 1,
        "provider": "whoop",
        "state": state,
        "client_configured": client is not None,
        "authorized": token is not None,
        "authorization_recovery_required": authorization_recovery_required,
        "requested_scopes": requested,
        "granted_scopes": granted,
        "coverage": {"api": api_coverage, "export": export_coverage},
        "latest_api_run": public_api_run,
        "latest_export_run": public_export_run,
        "manual_evidence": {
            "item_count": sum(
                (run.get("resource_item_counts") or {}).get("manual_evidence", 0)
                for run in evidence_runs
                if run.get("status") in {"complete", "partial"}
            ),
            "latest_at": (
                evidence_runs[0].get("finished_at") or evidence_runs[0].get("started_at")
                if evidence_runs
                else None
            ),
        },
        "schedule": _schedule_status(scheduler),
        "onboarding": onboarding,
        "limitations": {
            "stress_monitor": "manual_evidence_only",
            "api_export_boundary": "official_sources_only",
        },
    }
