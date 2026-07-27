"""Official WHOOP OAuth and API v2 transport adapter."""

from __future__ import annotations

import hmac
import json
import secrets
import string
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from . import __version__
from .archive import RawArchive, format_timestamp, utc_now
from .auth import CredentialError, CredentialStore
from .lock import PullLock


WHOOP_AUTHORIZATION_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com"
USER_AGENT = f"Viventium-Health/{__version__} (+https://github.com/ProjectViventium/Viventium-Health)"


class WhoopError(RuntimeError):
    """Safe WHOOP transport or protocol failure."""


@dataclass(frozen=True)
class WhoopResource:
    name: str
    path: str
    scope: str
    collection: bool


WHOOP_RESOURCES = (
    WhoopResource("cycles", "/developer/v2/cycle", "read:cycles", True),
    WhoopResource("recovery", "/developer/v2/recovery", "read:recovery", True),
    WhoopResource("sleep", "/developer/v2/activity/sleep", "read:sleep", True),
    WhoopResource("workout", "/developer/v2/activity/workout", "read:workout", True),
    WhoopResource("profile", "/developer/v2/user/profile/basic", "read:profile", False),
    WhoopResource("body_measurement", "/developer/v2/user/measurement/body", "read:body_measurement", False),
)


@dataclass(frozen=True)
class PullResult:
    run_id: str
    status: str
    resource_results: dict[str, str]
    record_count: int


@dataclass(frozen=True)
class _HttpResult:
    status: int
    body: bytes
    headers: dict[str, str]


class WhoopClient:
    """Thin WHOOP courier: auth, paging, retry, and exact-byte archival only."""

    def __init__(
        self,
        *,
        archive: RawArchive,
        credentials: CredentialStore,
        authorization_url: str = WHOOP_AUTHORIZATION_URL,
        token_url: str = WHOOP_TOKEN_URL,
        api_base: str = WHOOP_API_BASE,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = utc_now,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1 or max_attempts > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        self.archive = archive
        self.credentials = credentials
        self.authorization_endpoint = authorization_url
        self.token_endpoint = token_url
        self.api_base = api_base.rstrip("/")
        self.opener = opener
        self.sleep = sleep
        self.clock = clock
        self.max_attempts = max_attempts

    def begin_authorization(self) -> str:
        client = self.credentials.load_client()
        alphabet = string.ascii_letters + string.digits
        state = "".join(secrets.choice(alphabet) for _ in range(8))
        self.credentials.save_pending_state(state, created_at=self.clock())
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client["client_id"],
                "redirect_uri": client["redirect_uri"],
                "scope": " ".join(client["scopes"]),
                "state": state,
            }
        )
        return f"{self.authorization_endpoint}?{query}"

    def complete_authorization(self, callback_url: str) -> dict[str, Any]:
        client = self.credentials.load_client()
        callback = urlparse(callback_url)
        registered = urlparse(client["redirect_uri"])
        if (callback.scheme, callback.netloc, callback.path) != (
            registered.scheme,
            registered.netloc,
            registered.path,
        ):
            raise CredentialError("WHOOP callback URL does not match the registered redirect URI")
        query = parse_qs(callback.query)
        if "error" in query:
            raise CredentialError("WHOOP authorization was rejected")
        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        if not isinstance(code, str) or not code:
            raise CredentialError("WHOOP callback omitted the authorization code")
        expected_state = self.credentials.load_pending_state()
        if not isinstance(state, str) or not hmac.compare_digest(state, expected_state):
            raise CredentialError("WHOOP callback state did not match the pending authorization")
        token = self._post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "redirect_uri": client["redirect_uri"],
            }
        )
        persisted = self.credentials.save_token(token, obtained_at=self.clock())
        self.credentials.clear_pending_state()
        return persisted

    def _post_token(self, form: Mapping[str, str]) -> dict[str, Any]:
        request = Request(
            self.token_endpoint,
            data=urlencode(form).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with self.opener(request, timeout=30) as response:
                status = int(response.status)
                body = response.read()
        except HTTPError as error:
            try:
                status = int(error.code)
                body = error.read()
            finally:
                error.close()
        except (URLError, TimeoutError, OSError) as error:
            raise CredentialError(f"WHOOP token endpoint is unavailable ({type(error).__name__})") from None
        if status != 200:
            raise CredentialError(f"WHOOP token endpoint returned HTTP {status}")
        try:
            token = json.loads(body)
        except json.JSONDecodeError:
            raise CredentialError("WHOOP token endpoint returned invalid JSON") from None
        if not isinstance(token, dict):
            raise CredentialError("WHOOP token endpoint returned an invalid object")
        return token

    def refresh_access_token(self) -> dict[str, Any]:
        client = self.credentials.load_client()
        existing = self.credentials.load_token()
        refresh_token = existing.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise CredentialError("WHOOP refresh token is unavailable; reconnect with offline scope")
        token = self._post_token(
            {
                "grant_type": "refresh_token",
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "scope": "offline",
                "refresh_token": refresh_token,
            }
        )
        if not isinstance(token.get("refresh_token"), str) or not token["refresh_token"]:
            raise CredentialError("WHOOP refresh response omitted the rotated refresh token")
        return self.credentials.save_token(token, obtained_at=self.clock())

    def revoke_access(self) -> None:
        """Revoke the current grant upstream, then clear only the local token."""

        access_token = self._access_token()
        request = Request(
            f"{self.api_base}/developer/v2/user/access",
            method="DELETE",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with self.opener(request, timeout=30) as response:
                status = int(response.status)
                response.read()
        except HTTPError as error:
            try:
                status = int(error.code)
                error.read()
            finally:
                error.close()
        except (URLError, TimeoutError, OSError) as error:
            raise CredentialError(f"WHOOP revoke endpoint is unavailable ({type(error).__name__})") from None
        if status != 204:
            raise CredentialError(f"WHOOP revoke endpoint returned HTTP {status}; local token was retained")
        self.credentials.clear_token()

    def _access_token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh:
            fresh = self.credentials.access_token_if_fresh(now=self.clock())
            if fresh:
                return fresh
        refreshed = self.refresh_access_token()
        return str(refreshed["access_token"])

    def _get(self, path: str, query: Mapping[str, Any], access_token: str) -> _HttpResult:
        request = Request(
            f"{self.api_base}{path}?{urlencode(query)}" if query else f"{self.api_base}{path}",
            method="GET",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with self.opener(request, timeout=30) as response:
                return _HttpResult(
                    status=int(response.status),
                    body=response.read(),
                    headers={str(key): str(value) for key, value in response.headers.items()},
                )
        except HTTPError as error:
            try:
                return _HttpResult(
                    status=int(error.code),
                    body=error.read(),
                    headers={str(key): str(value) for key, value in error.headers.items()},
                )
            finally:
                error.close()

    @staticmethod
    def _content_type(headers: Mapping[str, str]) -> str:
        for key, value in headers.items():
            if key.lower() == "content-type":
                return value
        return ""

    def _retry_delay(self, response: _HttpResult, attempt: int) -> float:
        normalized = {key.lower(): value for key, value in response.headers.items()}
        retry_after = normalized.get("retry-after")
        if retry_after is not None:
            try:
                return min(60.0, max(0.0, float(retry_after)))
            except ValueError:
                pass
        reset = normalized.get("x-ratelimit-reset")
        if reset is not None:
            try:
                return min(60.0, max(0.0, float(reset) - self.clock().timestamp()))
            except ValueError:
                pass
        return min(30.0, float(2 ** (attempt - 1)))

    def _pull_resource(self, run: Any, resource: WhoopResource, start: datetime, end: datetime) -> str:
        page = 1
        next_token: str | None = None
        seen_tokens: set[str] = set()
        access_token = self._access_token()
        refreshed_after_401 = False
        while True:
            query: dict[str, Any] = {}
            if resource.collection:
                query = {
                    "start": format_timestamp(start),
                    "end": format_timestamp(end),
                    "limit": 25,
                }
                if next_token is not None:
                    query["nextToken"] = next_token
            response: _HttpResult | None = None
            for attempt in range(1, self.max_attempts + 1):
                try:
                    response = self._get(resource.path, query, access_token)
                except (URLError, TimeoutError, OSError) as error:
                    self.archive.record_network_error(
                        run,
                        resource=resource.name,
                        request_path=resource.path,
                        request_query=query,
                        error=error,
                        attempt=attempt,
                        page=page,
                        fetched_at=self.clock(),
                    )
                    if attempt < self.max_attempts:
                        self.sleep(min(30.0, float(2 ** (attempt - 1))))
                        continue
                    return f"network_{type(error).__name__}"
                self.archive.record_response(
                    run,
                    resource=resource.name,
                    body=response.body,
                    status=response.status,
                    content_type=self._content_type(response.headers),
                    response_headers=response.headers,
                    request_path=resource.path,
                    request_query=query,
                    attempt=attempt,
                    page=page,
                    fetched_at=self.clock(),
                )
                if response.status == 200:
                    break
                if response.status == 401 and not refreshed_after_401 and attempt < self.max_attempts:
                    try:
                        access_token = self._access_token(force_refresh=True)
                    except CredentialError:
                        return "authorization_refresh_failed"
                    refreshed_after_401 = True
                    continue
                if (response.status == 429 or 500 <= response.status <= 599) and attempt < self.max_attempts:
                    self.sleep(self._retry_delay(response, attempt))
                    continue
                return f"http_{response.status}"
            if response is None or response.status != 200:
                return "incomplete"
            if not resource.collection:
                return "complete"
            try:
                control = json.loads(response.body)
            except json.JSONDecodeError:
                return "invalid_json_control"
            if not isinstance(control, dict):
                return "invalid_json_control"
            candidate = control.get("next_token")
            if candidate is None:
                return "complete"
            if not isinstance(candidate, str) or not candidate:
                return "invalid_next_token"
            if candidate in seen_tokens:
                return "repeated_next_token"
            seen_tokens.add(candidate)
            next_token = candidate
            page += 1
            if page > 1000:
                return "pagination_limit"

    def _selected_resources(self) -> list[WhoopResource]:
        client = self.credentials.load_client()
        token = self.credentials.load_token()
        granted_value = token.get("scope")
        if isinstance(granted_value, str):
            granted = set(granted_value.split())
        else:
            granted = set(client["scopes"])
        return [resource for resource in WHOOP_RESOURCES if resource.scope in granted]

    def pull(self, *, start: datetime, end: datetime) -> PullResult:
        if start.tzinfo is None or end.tzinfo is None:
            raise WhoopError("pull timestamps must be timezone-aware")
        if start >= end:
            raise WhoopError("pull start must be before end")
        resources = self._selected_resources()
        if not resources:
            raise CredentialError("WHOOP grant has no supported read scopes")
        with PullLock(self.archive.locks_root / "whoop.pull.lock"):
            run = self.archive.start_run(
                provider="whoop",
                requested_start=format_timestamp(start),
                requested_end=format_timestamp(end),
                resources=[resource.name for resource in resources],
                started_at=self.clock(),
            )
            results: dict[str, str] = {}
            for resource in resources:
                try:
                    results[resource.name] = self._pull_resource(run, resource, start, end)
                except CredentialError:
                    results[resource.name] = "authorization_failed"
            complete_count = sum(value == "complete" for value in results.values())
            if complete_count == len(results):
                status = "complete"
            elif complete_count == 0:
                status = "failed"
            else:
                status = "partial"
            self.archive.finish_run(
                run,
                status=status,
                resource_results=results,
                finished_at=self.clock(),
            )
            records = self.archive.list_records(provider="whoop", run_id=run.run_id, limit=1000)
            return PullResult(
                run_id=run.run_id,
                status=status,
                resource_results=results,
                record_count=len(records),
            )
