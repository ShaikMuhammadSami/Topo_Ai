from __future__ import annotations

import time
import re
from typing import Any

import httpx
from urllib.parse import urlsplit


class AgentClientError(Exception):
    pass


class AgentApiClient:
    def __init__(
        self,
        *,
        backend_url: str,
        token: str | None,
        timeout_seconds: int,
        verify_tls: bool,
        max_retries: int,
        retry_backoff_seconds: float,
    ) -> None:
        self.backend_url = _validate_backend_url(backend_url)

        headers = {
            "Accept": "application/json",
            "User-Agent":
                "topo-ai-agent/0.3.0",
        }

        if token:
            headers["Authorization"] = (
                f"Bearer {token}"
            )

        self.client = httpx.Client(
            base_url=self.backend_url,
            headers=headers,
            timeout=httpx.Timeout(
                timeout_seconds
            ),
            verify=verify_tls,
            follow_redirects=False,
        )

        self.max_retries = max(
            max_retries,
            0,
        )

        self.retry_backoff_seconds = max(
            retry_backoff_seconds,
            0.0,
        )

    def close(self) -> None:
        self.client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body:
            dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(
            self.max_retries + 1
        ):
            try:
                response = (
                    self.client.request(
                        method=method,
                        url=path,
                        json=json_body,
                    )
                )

            except (
                httpx.TimeoutException,
                httpx.ConnectError,
            ) as exc:
                last_error = exc

                if (
                    attempt
                    >= self.max_retries
                ):
                    break

                time.sleep(
                    self.retry_backoff_seconds
                    * (2 ** attempt)
                )

                continue

            if (
                response.status_code
                in {
                    429,
                    502,
                    503,
                    504,
                }
                and attempt
                < self.max_retries
            ):
                time.sleep(
                    self.retry_backoff_seconds
                    * (2 ** attempt)
                )
                continue

            if 300 <= response.status_code < 400:
                raise AgentClientError(
                    "Backend redirect was not accepted."
                )

            if response.status_code >= 400:
                try:
                    value = response.json()
                    detail = value.get(
                        "detail"
                    )

                except ValueError:
                    detail = None

                if (
                    not isinstance(detail, str)
                    or re.fullmatch(r"[A-Z][A-Z0-9_. -]{0,200}", detail) is None
                ):
                    detail = "Request failed."

                raise AgentClientError(
                    f"API returned "
                    f"{response.status_code}: "
                    f"{detail}"
                )

            try:
                value = response.json()

            except ValueError as exc:
                raise AgentClientError(
                    "Backend returned a "
                    "non-JSON response."
                ) from exc

            if not isinstance(
                value,
                dict,
            ):
                raise AgentClientError(
                    "Backend returned an "
                    "invalid response."
                )

            return value

        raise AgentClientError(
            "Unable to reach the Topo backend."
        )

    def __repr__(self) -> str:
        return f"AgentApiClient(backend_url={self.backend_url!r}, token=<redacted>)"

    def health(
        self,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/health",
        )

    def enroll(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/agents/enroll",
            json_body=request,
        )

    def runtime_config(
        self,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/agent/config",
        )

    def heartbeat(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/agent/heartbeat",
            json_body=request,
        )

    def submit_snapshot(
        self,
        submission: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/agent/snapshots",
            json_body=submission,
        )

    def sensor_heartbeat(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            (
                "/api/v1/agent/"
                "runtime/heartbeat"
            ),
            json_body=request,
        )


    def submit_runtime_batch(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            (
                "/api/v1/agent/"
                "runtime/batches"
            ),
            json_body=request,
        )

    def submit_change_events(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        value = self._request(
            "POST",
            "/api/v1/agent/change-events",
            json_body={
                "events": events,
            },
        )

        if not isinstance(
            value,
            dict,
        ):
            raise RuntimeError(
                "Invalid change-event "
                "batch response."
            )

        return value

    def submit_failure_signals(
        self,
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/agent/signals",
            json_body={
                "signals": signals,
            },
        )


def _validate_backend_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError()
        parsed.port
    except (TypeError, ValueError):
        raise ValueError(
            "Backend URL must be http(s) without userinfo, query, or fragment."
        ) from None
    return value.rstrip("/")
