from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from viventium_health.archive import RawArchive
from viventium_health.auth import CredentialStore
from viventium_health.whoop import WhoopClient


NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)


class FakeWhoopHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []
    response_mode = "normal"
    retry_count = 0

    page_one = b'{"records":[{"unknown":"kept"}],"next_token":"private-page-2"}'
    page_two = b'{"records":[{"future_vendor_field":42}]}'

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode())
        type(self).requests.append({"method": "POST", "path": self.path, "form": form})
        if self.path != "/oauth/oauth2/token":
            self.send_json(404, b'{"error":"not_found"}')
            return
        if form.get("grant_type") == ["authorization_code"]:
            self.send_json(
                200,
                b'{"access_token":"access-one","refresh_token":"refresh-one","expires_in":3600,'
                b'"token_type":"bearer","scope":"read:cycles offline","vendor_extension":{"kept":true}}',
            )
        elif form.get("grant_type") == ["refresh_token"] and form.get("refresh_token") == ["refresh-one"]:
            self.send_json(
                200,
                b'{"access_token":"access-two","refresh_token":"refresh-two","expires_in":7200,'
                b'"token_type":"bearer","scope":"read:cycles offline"}',
            )
        else:
            self.send_json(400, b'{"error":"invalid_grant"}')

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        type(self).requests.append(
            {
                "method": "GET",
                "path": parsed.path,
                "query": query,
                "authorization": self.headers.get("Authorization"),
            }
        )
        if self.response_mode == "unauthorized_once" and self.headers.get("Authorization") != "Bearer access-two":
            self.send_json(401, b'{"error":"expired"}')
            return
        if self.response_mode == "invalid_control" and parsed.path.endswith("/cycle"):
            self.send_json(200, b'{"records":')
            return
        if self.response_mode == "retry_partial" and parsed.path.endswith("/recovery"):
            type(self).retry_count += 1
            if self.retry_count == 1:
                self.send_json(429, b'{"error":"slow"}', {"Retry-After": "0"})
                return
            if self.retry_count == 2:
                self.send_json(503, b'{"error":"temporary"}')
                return
            self.send_json(200, b'{"records":[]}')
            return
        if self.response_mode == "retry_partial" and parsed.path.endswith("/activity/sleep"):
            self.send_json(403, b'{"error":"missing_scope"}')
            return
        if parsed.path.endswith("/cycle"):
            if query.get("nextToken") == ["private-page-2"]:
                self.send_json(200, self.page_two, {"ETag": '"page-two"'})
            else:
                self.send_json(200, self.page_one, {"ETag": '"page-one"'})
            return
        if parsed.path.endswith("/user/profile/basic"):
            self.send_json(200, b'{"arbitrary_profile_field":"preserved"}')
            return
        if parsed.path.endswith("/user/measurement/body"):
            self.send_json(200, b'{"arbitrary_body_field":"preserved"}')
            return
        self.send_json(404, b'{"error":"not_found"}')


class FakeWhoopServer:
    def __enter__(self):
        FakeWhoopHandler.requests = []
        FakeWhoopHandler.response_mode = "normal"
        FakeWhoopHandler.retry_count = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeWhoopHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class WhoopConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "health"
        self.archive = RawArchive(self.root)
        self.credentials = CredentialStore(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_client(self, server: FakeWhoopServer, **kwargs) -> WhoopClient:
        return WhoopClient(
            archive=self.archive,
            credentials=self.credentials,
            authorization_url=f"{server.base}/oauth/oauth2/auth",
            token_url=f"{server.base}/oauth/oauth2/token",
            api_base=server.base,
            clock=lambda: NOW,
            **kwargs,
        )

    def test_authorization_exchange_and_rotating_refresh_are_private_and_atomic(self) -> None:
        with FakeWhoopServer() as server:
            self.credentials.save_client(
                client_id="public-client-id",
                client_secret="private-client-secret",
                redirect_uri="https://example.com/whoop/callback",
                scopes=["read:cycles", "offline"],
            )
            client = self.make_client(server)

            authorization_url = client.begin_authorization()
            query = parse_qs(urlparse(authorization_url).query)
            self.assertEqual(query["response_type"], ["code"])
            self.assertEqual(query["scope"], ["read:cycles offline"])
            self.assertEqual(len(query["state"][0]), 8)

            token = client.complete_authorization(
                f"https://example.com/whoop/callback?code=synthetic-code&state={query['state'][0]}"
            )
            self.assertEqual(token["access_token"], "access-one")
            self.assertTrue(token["vendor_extension"]["kept"])
            token_path = self.root / "secrets" / "whoop.token.json"
            self.assertEqual(stat.S_IMODE(token_path.stat().st_mode), 0o600)

            refreshed = client.refresh_access_token()
            self.assertEqual(refreshed["access_token"], "access-two")
            self.assertEqual(refreshed["refresh_token"], "refresh-two")
            persisted = json.loads(token_path.read_text())
            self.assertEqual(persisted["refresh_token"], "refresh-two")
            self.assertNotIn("refresh-one", token_path.read_text())

            forms = [request["form"] for request in FakeWhoopHandler.requests if request["method"] == "POST"]
            self.assertEqual(forms[0]["grant_type"], ["authorization_code"])
            self.assertEqual(forms[1]["grant_type"], ["refresh_token"])
            self.assertEqual(forms[1]["scope"], ["offline"])

    def test_two_page_collection_is_archived_before_control_parsing(self) -> None:
        with FakeWhoopServer() as server:
            self.credentials.save_client(
                client_id="client",
                client_secret="secret",
                redirect_uri="https://example.com/callback",
                scopes=["read:cycles", "offline"],
            )
            self.credentials.save_token(
                {
                    "access_token": "current-access",
                    "refresh_token": "refresh-one",
                    "expires_in": 3600,
                    "scope": "read:cycles offline",
                    "token_type": "bearer",
                },
                obtained_at=NOW,
            )
            client = self.make_client(server)

            result = client.pull(start=NOW - timedelta(days=3), end=NOW)

            self.assertEqual(result.status, "complete")
            self.assertEqual(result.resource_results, {"cycles": "complete"})
            records = self.archive.list_records(provider="whoop", run_id=result.run_id, limit=10)
            self.assertEqual(len(records), 2)
            bodies = {
                self.archive.read_record(record["record_id"], max_bytes=10_000)["data"].encode()
                for record in records
            }
            self.assertEqual(bodies, {FakeWhoopHandler.page_one, FakeWhoopHandler.page_two})
            raw_metadata = "\n".join(
                path.read_text()
                for path in self.root.rglob("*.meta.json")
            )
            self.assertNotIn("private-page-2", raw_metadata)

            gets = [request for request in FakeWhoopHandler.requests if request["method"] == "GET"]
            self.assertEqual(gets[0]["authorization"], "Bearer current-access")
            self.assertEqual(gets[1]["query"]["nextToken"], ["private-page-2"])

    def test_retry_responses_and_partial_scope_failure_remain_visible(self) -> None:
        sleeps: list[float] = []
        with FakeWhoopServer() as server:
            FakeWhoopHandler.response_mode = "retry_partial"
            self.credentials.save_client(
                client_id="client",
                client_secret="secret",
                redirect_uri="https://example.com/callback",
                scopes=["read:recovery", "read:sleep", "offline"],
            )
            self.credentials.save_token(
                {
                    "access_token": "current-access",
                    "refresh_token": "refresh-one",
                    "expires_in": 3600,
                    "scope": "read:recovery read:sleep offline",
                },
                obtained_at=NOW,
            )
            client = self.make_client(server, sleep=sleeps.append, max_attempts=3)

            result = client.pull(start=NOW - timedelta(days=3), end=NOW)

            self.assertEqual(result.status, "partial")
            self.assertEqual(result.resource_results["recovery"], "complete")
            self.assertEqual(result.resource_results["sleep"], "http_403")
            records = self.archive.list_records(provider="whoop", run_id=result.run_id, limit=20)
            self.assertEqual(sorted(record["status"] for record in records), [200, 403, 429, 503])
            self.assertEqual(sleeps, [0.0, 2.0])

    def test_unauthorized_response_is_archived_then_refreshes_once(self) -> None:
        with FakeWhoopServer() as server:
            FakeWhoopHandler.response_mode = "unauthorized_once"
            self.credentials.save_client(
                client_id="client",
                client_secret="secret",
                redirect_uri="https://example.com/callback",
                scopes=["read:cycles", "offline"],
            )
            self.credentials.save_token(
                {
                    "access_token": "expired-at-provider",
                    "refresh_token": "refresh-one",
                    "expires_in": 3600,
                    "scope": "read:cycles offline",
                },
                obtained_at=NOW,
            )
            result = self.make_client(server).pull(start=NOW - timedelta(days=3), end=NOW)

            self.assertEqual(result.status, "complete")
            statuses = [
                record["status"]
                for record in self.archive.list_records(provider="whoop", run_id=result.run_id, limit=20)
            ]
            self.assertEqual(statuses.count(401), 1)
            self.assertEqual(statuses.count(200), 2)
            self.assertEqual(self.credentials.load_token()["refresh_token"], "refresh-two")

    def test_invalid_pagination_control_and_network_failure_are_not_empty_data(self) -> None:
        with FakeWhoopServer() as server:
            FakeWhoopHandler.response_mode = "invalid_control"
            self.credentials.save_client(
                client_id="client",
                client_secret="secret",
                redirect_uri="https://example.com/callback",
                scopes=["read:cycles", "offline"],
            )
            self.credentials.save_token(
                {
                    "access_token": "current-access",
                    "refresh_token": "refresh-one",
                    "expires_in": 3600,
                    "scope": "read:cycles offline",
                },
                obtained_at=NOW,
            )
            invalid = self.make_client(server).pull(start=NOW - timedelta(days=3), end=NOW)
            self.assertEqual(invalid.status, "failed")
            self.assertEqual(invalid.resource_results["cycles"], "invalid_json_control")
            invalid_record = self.archive.list_records(provider="whoop", run_id=invalid.run_id, limit=10)[0]
            self.assertEqual(
                self.archive.read_record(invalid_record["record_id"], max_bytes=100)["data"],
                '{"records":',
            )

        sleeps: list[float] = []
        network = WhoopClient(
            archive=self.archive,
            credentials=self.credentials,
            api_base="http://127.0.0.1:1",
            clock=lambda: NOW,
            sleep=sleeps.append,
            max_attempts=2,
        ).pull(start=NOW - timedelta(days=3), end=NOW)
        self.assertEqual(network.status, "failed")
        self.assertTrue(network.resource_results["cycles"].startswith("network_"))
        errors = self.archive.list_records(provider="whoop", run_id=network.run_id, limit=10)
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(record["status"] is None for record in errors))
        self.assertEqual(sleeps, [1.0])

    def test_profile_and_body_are_only_selected_when_their_scopes_are_granted(self) -> None:
        with FakeWhoopServer() as server:
            self.credentials.save_client(
                client_id="client",
                client_secret="secret",
                redirect_uri="https://example.com/callback",
                scopes=["read:profile", "read:body_measurement"],
            )
            self.credentials.save_token(
                {
                    "access_token": "current-access",
                    "expires_in": 3600,
                    "scope": "read:profile read:body_measurement",
                },
                obtained_at=NOW,
            )
            result = self.make_client(server).pull(start=NOW - timedelta(days=3), end=NOW)
            self.assertEqual(
                result.resource_results,
                {"profile": "complete", "body_measurement": "complete"},
            )
            records = self.archive.list_records(provider="whoop", run_id=result.run_id, limit=10)
            self.assertEqual({record["resource"] for record in records}, {"profile", "body_measurement"})


if __name__ == "__main__":
    unittest.main()
