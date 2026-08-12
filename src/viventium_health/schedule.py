"""Explicit macOS LaunchAgent management for the daily WHOOP pull."""

from __future__ import annotations

import os
import platform
import plistlib
import secrets
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .auth import CredentialStore

LABEL = "com.projectviventium.health.whoop"


class ScheduleError(RuntimeError):
    """Safe scheduler setup/status failure."""


class HealthScheduler:
    def __init__(
        self,
        *,
        root: str | os.PathLike[str],
        executable: str = sys.executable,
        launch_agents_dir: str | os.PathLike[str] | None = None,
        runner: Callable[..., Any] = subprocess.run,
        platform_name: str | None = None,
        uid: int | None = None,
    ) -> None:
        self.root = Path(root)
        self.executable = executable
        self.launch_agents_dir = (
            Path(launch_agents_dir) if launch_agents_dir is not None else Path.home() / "Library" / "LaunchAgents"
        )
        self.runner = runner
        self.platform_name = platform_name or platform.system()
        self.uid = os.getuid() if uid is None else uid
        self.path = self.launch_agents_dir / f"{LABEL}.plist"

    @staticmethod
    def _validate(provider: str, hour: int, minute: int, lookback_days: int) -> None:
        if provider != "whoop":
            raise ValueError("only the WHOOP schedule is implemented")
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("schedule hour/minute is invalid")
        if not 1 <= lookback_days <= 365:
            raise ValueError("lookback_days must be between 1 and 365")

    def render(self, *, provider: str, hour: int, minute: int, lookback_days: int) -> bytes:
        self._validate(provider, hour, minute, lookback_days)
        logs = self.root / "logs"
        job = {
            "Label": LABEL,
            "ProgramArguments": [
                self.executable,
                "-m",
                "viventium_health",
                "--root",
                str(self.root),
                "pull",
                provider,
                "--lookback-days",
                str(lookback_days),
            ],
            "RunAtLoad": True,
            "StartCalendarInterval": {"Hour": hour, "Minute": minute},
            "ProcessType": "Background",
            "Nice": 10,
            "StandardOutPath": str(logs / f"{provider}-schedule.stdout.log"),
            "StandardErrorPath": str(logs / f"{provider}-schedule.stderr.log"),
        }
        return plistlib.dumps(job, fmt=plistlib.FMT_XML, sort_keys=False)

    def _run(self, arguments: list[str]) -> Any:
        return self.runner(arguments, capture_output=True, text=True, check=False)

    def _write(self, body: bytes) -> None:
        self.launch_agents_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.launch_agents_dir / f".{self.path.name}.tmp-{secrets.token_hex(8)}"
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

    def install(self, *, provider: str, hour: int, minute: int, lookback_days: int) -> Path:
        if self.platform_name != "Darwin":
            raise ScheduleError("native schedule installation currently requires macOS")
        credentials = CredentialStore(self.root)
        credentials.load_client()
        credentials.load_token()
        body = self.render(provider=provider, hour=hour, minute=minute, lookback_days=lookback_days)
        (self.root / "logs").mkdir(mode=0o700, parents=True, exist_ok=True)
        (self.root / "logs").chmod(0o700)
        if self.path.exists():
            self._run(["launchctl", "bootout", f"gui/{self.uid}/{LABEL}"])
        self._write(body)
        result = self._run(["launchctl", "bootstrap", f"gui/{self.uid}", str(self.path)])
        if result.returncode != 0:
            raise ScheduleError("launchd rejected the Viventium-Health schedule")
        return self.path

    def _configured_for_root(self) -> bool:
        try:
            job = plistlib.loads(self.path.read_bytes())
            arguments = job["ProgramArguments"]
            root_index = arguments.index("--root") + 1
            configured_root = Path(arguments[root_index])
            return configured_root.resolve(strict=False) == self.root.resolve(strict=False)
        except (
            FileNotFoundError,
            OSError,
            KeyError,
            TypeError,
            ValueError,
            IndexError,
            RuntimeError,
            plistlib.InvalidFileException,
        ):
            return False

    def status(self) -> dict[str, Any]:
        configured = self._configured_for_root()
        if self.platform_name != "Darwin":
            return {"configured": configured, "loaded": False, "platform_supported": False}
        if not configured:
            return {"configured": False, "loaded": False, "platform_supported": True}
        result = self._run(["launchctl", "print", f"gui/{self.uid}/{LABEL}"])
        return {"configured": configured, "loaded": result.returncode == 0, "platform_supported": True}

    def uninstall(self) -> bool:
        if self.platform_name == "Darwin":
            self._run(["launchctl", "bootout", f"gui/{self.uid}/{LABEL}"])
        existed = self.path.exists()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        return existed
