"""Owner-only storage for WHOOP OAuth client and rotating tokens."""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .archive import format_timestamp, utc_now

WHOOP_SCOPES = {
    "offline",
    "read:body_measurement",
    "read:cycles",
    "read:profile",
    "read:recovery",
    "read:sleep",
    "read:workout",
}
DEFAULT_WHOOP_SCOPES = ["read:cycles", "read:recovery", "read:sleep", "read:workout", "offline"]


class CredentialError(RuntimeError):
    """Safe operator-facing credential/configuration failure."""


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class CredentialStore:
    """Persist mutable secrets atomically outside the source checkout."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.secrets_root = self.root / "secrets"
        self.secrets_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.secrets_root.chmod(0o700)
        self.client_path = self.secrets_root / "whoop.client.json"
        self.token_path = self.secrets_root / "whoop.token.json"
        self.pending_path = self.secrets_root / "whoop.pending.json"

    def _atomic_replace(self, path: Path, value: Mapping[str, Any]) -> None:
        body = (json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        temporary = path.parent / f".{path.name}.tmp-{secrets.token_hex(8)}"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            try:
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                pass
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _read(path: Path, label: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise CredentialError(f"WHOOP {label} is not configured") from None
        except (OSError, json.JSONDecodeError):
            raise CredentialError(f"WHOOP {label} file is unreadable") from None
        if not isinstance(value, dict):
            raise CredentialError(f"WHOOP {label} file is invalid")
        return value

    def save_client(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> dict[str, Any]:
        if not client_id.strip() or not client_secret.strip():
            raise CredentialError("WHOOP client ID and secret are required")
        parsed_redirect = urlparse(redirect_uri)
        if not parsed_redirect.scheme:
            raise CredentialError("WHOOP redirect URI must be an absolute registered URI")
        if not scopes or any(scope not in WHOOP_SCOPES for scope in scopes):
            raise CredentialError("WHOOP scopes must be selected from the official read/offline set")
        if len(scopes) != len(set(scopes)):
            raise CredentialError("WHOOP scopes must not contain duplicates")
        value = {
            "schema_version": 1,
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "redirect_uri": redirect_uri,
            "scopes": list(scopes),
        }
        self._atomic_replace(self.client_path, value)
        return value

    def load_client(self) -> dict[str, Any]:
        value = self._read(self.client_path, "OAuth client")
        for key in ("client_id", "client_secret", "redirect_uri", "scopes"):
            if key not in value:
                raise CredentialError("WHOOP OAuth client file is incomplete")
        return value

    def save_token(self, token: Mapping[str, Any], *, obtained_at: datetime | None = None) -> dict[str, Any]:
        if not isinstance(token.get("access_token"), str) or not token["access_token"]:
            raise CredentialError("WHOOP token response omitted access_token")
        value = dict(token)
        timestamp = obtained_at or utc_now()
        expires_in = value.get("expires_in")
        try:
            seconds = float(expires_in)
        except (TypeError, ValueError):
            raise CredentialError("WHOOP token response omitted a valid expires_in") from None
        value["obtained_at"] = format_timestamp(timestamp)
        value["expires_at"] = format_timestamp(timestamp + timedelta(seconds=seconds))
        self._atomic_replace(self.token_path, value)
        return value

    def load_token(self) -> dict[str, Any]:
        return self._read(self.token_path, "OAuth token")

    def access_token_if_fresh(self, *, now: datetime | None = None, margin_seconds: int = 60) -> str | None:
        token = self.load_token()
        access_token = token.get("access_token")
        expires_at = token.get("expires_at")
        if not isinstance(access_token, str) or not isinstance(expires_at, str):
            raise CredentialError("WHOOP OAuth token file is incomplete")
        try:
            expiry = _parse_timestamp(expires_at)
        except ValueError:
            raise CredentialError("WHOOP OAuth token expiry is invalid") from None
        reference = now or utc_now()
        if expiry <= reference + timedelta(seconds=margin_seconds):
            return None
        return access_token

    def save_pending_state(self, state: str, *, created_at: datetime | None = None) -> None:
        if len(state) != 8:
            raise CredentialError("WHOOP OAuth state must be exactly eight characters")
        self._atomic_replace(
            self.pending_path,
            {"state": state, "created_at": format_timestamp(created_at or utc_now())},
        )

    def load_pending_state(self) -> str:
        value = self._read(self.pending_path, "pending authorization")
        state = value.get("state")
        if not isinstance(state, str) or len(state) != 8:
            raise CredentialError("WHOOP pending authorization is invalid")
        return state

    def clear_pending_state(self) -> None:
        try:
            self.pending_path.unlink()
        except FileNotFoundError:
            pass

    def clear_token(self) -> None:
        try:
            self.token_path.unlink()
        except FileNotFoundError:
            pass
