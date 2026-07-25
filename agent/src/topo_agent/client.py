from __future__ import annotations

import time
from typing import Any

import httpx


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
        self.backend_url = (
            backend_url.rstrip("/")
        )

        self.token = token

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
            follow_redirects=True,
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

            if response.status_code >= 400:
                try:
                    value = response.json()
                    detail = value.get(
                        "detail"
                    )

                except ValueError:
                    detail = (
                        response.text
                    )

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
            "Unable to reach the Topo "
            f"backend: {last_error}"
        )

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