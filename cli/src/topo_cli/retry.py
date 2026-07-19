from __future__ import annotations

import time
from collections.abc import Callable

import httpx


RETRYABLE_STATUS_CODES = {
    429,
    502,
    503,
    504,
}


def _retry_delay(
    response: httpx.Response | None,
    *,
    attempt: int,
    backoff: float,
) -> float:
    if response is not None:
        retry_after = (
            response.headers.get(
                "Retry-After"
            )
        )

        if retry_after:
            try:
                return max(
                    float(retry_after),
                    0.0,
                )

            except ValueError:
                pass

    return backoff * (
        2 ** attempt
    )


def execute_request(
    operation:
        Callable[[], httpx.Response],
    *,
    max_retries: int,
    backoff: float,
) -> httpx.Response:
    """
    Retry connection failures, timeouts,
    rate limiting and temporary gateway/service
    errors.

    Each attempt recreates the request through
    the supplied callable.
    """

    for attempt in range(
        max_retries + 1
    ):
        response: (
            httpx.Response | None
        ) = None

        try:
            response = operation()

        except (
            httpx.TimeoutException,
            httpx.ConnectError,
        ):
            if attempt >= max_retries:
                raise

            time.sleep(
                _retry_delay(
                    None,
                    attempt=attempt,
                    backoff=backoff,
                )
            )

            continue

        if (
            response.status_code
            not in RETRYABLE_STATUS_CODES
            or attempt >= max_retries
        ):
            return response

        delay = _retry_delay(
            response,
            attempt=attempt,
            backoff=backoff,
        )

        response.close()

        time.sleep(delay)

    raise RuntimeError(
        "Retry loop exited without "
        "returning a response."
    )