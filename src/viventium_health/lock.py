"""Single-process pull lock with conservative stale-process recovery."""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LockBusyError(RuntimeError):
    """Raised when another live process owns the pull lock."""


def _process_is_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class PullLock:
    """Owner-checked lock file suitable for serializing rotating OAuth tokens."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.nonce = secrets.token_hex(16)
        self.acquired = False

    def _try_recover_stale(self) -> bool:
        try:
            existing = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if _process_is_alive(existing.get("pid")):
            return False
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        return True

    def acquire(self) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        payload = (
            json.dumps(
                {
                    "pid": os.getpid(),
                    "nonce": self.nonce,
                    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        for attempt in range(2):
            try:
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if attempt == 0 and self._try_recover_stale():
                    continue
                raise LockBusyError("another Viventium-Health pull is active") from None
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(self.path, 0o600)
            self.acquired = True
            return
        raise LockBusyError("another Viventium-Health pull is active")

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        if current.get("nonce") == self.nonce and current.get("pid") == os.getpid():
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.acquired = False

    def __enter__(self) -> "PullLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()
