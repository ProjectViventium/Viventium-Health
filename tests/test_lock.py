from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from viventium_health.lock import LockBusyError, PullLock


class PullLockTests(unittest.TestCase):
    def test_live_lock_fails_fast_and_release_is_owner_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "locks" / "pull.lock"
            with PullLock(path):
                with self.assertRaises(LockBusyError):
                    with PullLock(path):
                        self.fail("a second live lock must not be acquired")
            self.assertFalse(path.exists())

    def test_dead_process_lock_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "locks" / "pull.lock"
            path.parent.mkdir(mode=0o700)
            path.write_text(json.dumps({"pid": 99_999_999, "nonce": "stale"}))
            os.chmod(path, 0o600)
            with PullLock(path):
                current = json.loads(path.read_text())
                self.assertEqual(current["pid"], os.getpid())
                self.assertNotEqual(current["nonce"], "stale")
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
