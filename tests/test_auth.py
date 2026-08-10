from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from viventium_health.auth import CredentialError, CredentialStore


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


class CredentialStorePendingAuthorizationTests(unittest.TestCase):
    def test_fresh_pending_authorization_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = CredentialStore(temp)
            store.save_pending_state("Abc123Xy", created_at=NOW - timedelta(minutes=9))

            self.assertEqual(store.load_pending_state(now=NOW), "Abc123Xy")

    def test_expired_pending_authorization_is_rejected_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = CredentialStore(temp)
            store.save_pending_state("Abc123Xy", created_at=NOW - timedelta(minutes=11))

            with self.assertRaisesRegex(CredentialError, "expired"):
                store.load_pending_state(now=NOW)

            self.assertFalse(store.pending_path.exists())

    def test_invalid_pending_timestamp_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = CredentialStore(temp)
            store.save_pending_state("Abc123Xy", created_at=NOW)
            payload = store.pending_path.read_text(encoding="utf-8").replace(
                "2026-08-10T12:00:00.000000Z", "not-a-time"
            )
            store.pending_path.write_text(payload, encoding="utf-8")

            with self.assertRaisesRegex(CredentialError, "invalid"):
                store.load_pending_state(now=NOW)


if __name__ == "__main__":
    unittest.main()
