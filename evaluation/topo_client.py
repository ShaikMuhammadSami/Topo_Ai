from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class HttpObservation:
    status: int
    body: Any


class TopoClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 15.0,
        bearer_token: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._bearer_token = bearer_token

    def set_bearer_token(self, bearer_token: str) -> None:
        self._bearer_token = bearer_token

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> HttpObservation:
        payload = None
        headers = {"Accept": "application/json"}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return HttpObservation(response.status, json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                parsed: Any = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            return HttpObservation(exc.code, parsed)
        except urllib.error.URLError as exc:
            return HttpObservation(0, {"transport_error": str(exc.reason)})

    def get(self, path: str, **query: Any) -> HttpObservation:
        encoded = urllib.parse.urlencode(
            {key: value for key, value in query.items() if value is not None}
        )
        return self.request("GET", path + ("?" + encoded if encoded else ""))

    def post(self, path: str, body: dict[str, Any]) -> HttpObservation:
        return self.request("POST", path, body)


def bounded_wait(
    operation: Callable[[], Any],
    predicate: Callable[[Any], bool],
    *,
    timeout_seconds: float,
    interval_seconds: float = 2.0,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> Any:
    deadline = clock() + timeout_seconds
    last = None
    while clock() <= deadline:
        last = operation()
        if predicate(last):
            return last
        sleeper(interval_seconds)
    raise TimeoutError(
        f"Condition not met within {timeout_seconds:.1f}s; last value={last!r}"
    )
