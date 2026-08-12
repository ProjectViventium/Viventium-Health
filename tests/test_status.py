from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from viventium_health.archive import RawArchive
from viventium_health.auth import DEFAULT_WHOOP_SCOPES, CredentialStore
from viventium_health.status import WhoopOnboardingStore, build_whoop_status


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


class FakeScheduler:
    def __init__(self, status: dict[str, object] | None = None) -> None:
        self._status = status or {
            "configured": False,
            "loaded": False,
            "platform_supported": True,
        }

    def status(self) -> dict[str, object]:
        return dict(self._status)


class WhoopStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "health"
        self.archive = RawArchive(self.root)
        self.credentials = CredentialStore(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_first_run_status_is_actionable_and_lists_every_supported_lane(self) -> None:
        status = build_whoop_status(
            archive=self.archive,
            credentials=self.credentials,
            scheduler=FakeScheduler(),
            clock=lambda: NOW,
        )

        self.assertEqual(status["schema_version"], 1)
        self.assertEqual(status["provider"], "whoop")
        self.assertEqual(status["state"], "setup_required")
        self.assertFalse(status["client_configured"])
        self.assertFalse(status["authorized"])
        self.assertEqual(
            set(status["coverage"]["api"]),
            {"cycles", "recovery", "sleep", "workout", "profile", "body_measurement"},
        )
        self.assertEqual(status["coverage"]["export"]["journal_entries"]["status"], "available_by_import")
        self.assertEqual(status["limitations"]["stress_monitor"], "manual_evidence_only")

    def test_connected_status_reports_provider_items_not_archive_pages_and_never_secrets(self) -> None:
        self.credentials.save_client(
            client_id="client-id-must-not-leak",
            client_secret="client-secret-must-not-leak",
            redirect_uri="viventium://oauth/whoop",
            scopes=list(DEFAULT_WHOOP_SCOPES),
        )
        self.credentials.save_token(
            {
                "access_token": "access-token-must-not-leak",
                "refresh_token": "refresh-token-must-not-leak",
                "expires_in": 3600,
                "scope": " ".join(DEFAULT_WHOOP_SCOPES),
            },
            obtained_at=NOW,
        )
        run = self.archive.start_run(
            provider="whoop",
            requested_start=None,
            requested_end="2026-08-10T12:00:00.000000Z",
            resources=["cycles", "recovery"],
            started_at=NOW,
        )
        self.archive.finish_run(
            run,
            status="complete",
            resource_results={"cycles": "complete", "recovery": "complete"},
            resource_item_counts={"cycles": 4, "recovery": 3},
            item_count=7,
            finished_at=NOW,
        )

        status = build_whoop_status(
            archive=self.archive,
            credentials=self.credentials,
            scheduler=FakeScheduler(
                {"configured": True, "loaded": True, "platform_supported": True}
            ),
            clock=lambda: NOW,
        )

        self.assertEqual(status["state"], "connected")
        self.assertTrue(status["authorized"])
        self.assertEqual(status["latest_api_run"]["item_count"], 7)
        self.assertEqual(status["latest_api_run"]["resource_item_counts"]["cycles"], 4)
        self.assertEqual(status["coverage"]["api"]["cycles"]["items"], 4)
        self.assertEqual(status["schedule"]["state"], "active")
        serialized = json.dumps(status)
        for forbidden in (
            "client-id-must-not-leak",
            "client-secret-must-not-leak",
            "access-token-must-not-leak",
            "refresh-token-must-not-leak",
            str(self.root),
        ):
            self.assertNotIn(forbidden, serialized)

    def test_pending_and_failed_onboarding_states_are_persistent_and_safe(self) -> None:
        self.credentials.save_client(
            client_id="client",
            client_secret="secret",
            redirect_uri="viventium://oauth/whoop",
            scopes=list(DEFAULT_WHOOP_SCOPES),
        )
        self.credentials.save_pending_state("Abc123Xy", created_at=NOW)

        pending = build_whoop_status(
            archive=self.archive,
            credentials=self.credentials,
            scheduler=FakeScheduler(),
            clock=lambda: NOW,
        )
        self.assertEqual(pending["state"], "authorization_pending")

        receipts = WhoopOnboardingStore(self.root)
        receipts.update(phase="history_import", status="failed", error_code="provider_unavailable", now=NOW)
        failed = build_whoop_status(
            archive=self.archive,
            credentials=self.credentials,
            scheduler=FakeScheduler(),
            clock=lambda: NOW,
        )
        self.assertEqual(failed["state"], "degraded")
        self.assertEqual(failed["onboarding"]["error_code"], "provider_unavailable")
        self.assertNotIn("path", json.dumps(failed))

    def test_expired_pending_authorization_returns_to_ready_without_stale_polling(self) -> None:
        self.credentials.save_client(
            client_id="client",
            client_secret="secret",
            redirect_uri="viventium://oauth/whoop",
            scopes=list(DEFAULT_WHOOP_SCOPES),
        )
        self.credentials.save_pending_state("Abc123Xy", created_at=NOW - timedelta(minutes=11))

        status = build_whoop_status(
            archive=self.archive,
            credentials=self.credentials,
            scheduler=FakeScheduler(),
            clock=lambda: NOW,
        )

        self.assertEqual(status["state"], "ready_to_authorize")
        self.assertFalse(self.credentials.pending_path.exists())

    def test_status_counts_manual_evidence_without_treating_it_as_api_data(self) -> None:
        run = self.archive.start_run(
            provider="whoop",
            requested_start=None,
            requested_end="2026-08-10T12:00:00.000000Z",
            resources=["manual_evidence"],
            started_at=NOW,
        )
        self.archive.finish_run(
            run,
            status="complete",
            resource_results={"manual_evidence": "complete"},
            resource_item_counts={"manual_evidence": 1},
            item_count=1,
            finished_at=NOW,
        )

        status = build_whoop_status(
            archive=self.archive,
            credentials=self.credentials,
            scheduler=FakeScheduler(),
            clock=lambda: NOW,
        )

        self.assertEqual(status["manual_evidence"]["item_count"], 1)
        self.assertEqual(status["manual_evidence"]["latest_at"], "2026-08-10T12:00:00.000000Z")
        self.assertIsNone(status["latest_api_run"])

    def test_status_declares_authorization_recovery_for_both_refresh_failure_lanes(self) -> None:
        self.credentials.save_client(
            client_id="client",
            client_secret="secret",
            redirect_uri="viventium://oauth/whoop",
            scopes=list(DEFAULT_WHOOP_SCOPES),
        )
        self.credentials.save_token(
            {
                "access_token": "expired-access",
                "refresh_token": "rejected-refresh",
                "expires_in": 3600,
                "scope": " ".join(DEFAULT_WHOOP_SCOPES),
            },
            obtained_at=NOW - timedelta(days=1),
        )

        for failure in ("authorization_failed", "authorization_refresh_failed"):
            with self.subTest(failure=failure):
                run = self.archive.start_run(
                    provider="whoop",
                    requested_start=None,
                    requested_end="2026-08-10T12:00:00.000000Z",
                    resources=["cycles"],
                    started_at=NOW,
                )
                self.archive.finish_run(
                    run,
                    status="failed",
                    resource_results={"cycles": failure},
                    resource_item_counts={"cycles": 0},
                    item_count=0,
                    finished_at=NOW,
                )

                status = build_whoop_status(
                    archive=self.archive,
                    credentials=self.credentials,
                    scheduler=FakeScheduler(),
                    clock=lambda: NOW,
                )

                self.assertEqual(status["state"], "degraded")
                self.assertTrue(status["authorization_recovery_required"])


if __name__ == "__main__":
    unittest.main()
