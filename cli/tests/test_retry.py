import httpx

from topo_cli.retry import (
    execute_request,
)


def _response(
    status_code: int,
) -> httpx.Response:
    request = httpx.Request(
        "GET",
        "https://topo.example/health",
    )

    return httpx.Response(
        status_code=status_code,
        request=request,
    )


def test_retries_temporary_service_error(
    monkeypatch,
) -> None:
    calls = 0

    def operation(
    ) -> httpx.Response:
        nonlocal calls

        calls += 1

        if calls < 3:
            return _response(503)

        return _response(200)

    monkeypatch.setattr(
        "topo_cli.retry.time.sleep",
        lambda _: None,
    )

    response = execute_request(
        operation,
        max_retries=3,
        backoff=0.01,
    )

    assert response.status_code == 200
    assert calls == 3


def test_does_not_retry_client_error(
    monkeypatch,
) -> None:
    calls = 0

    def operation(
    ) -> httpx.Response:
        nonlocal calls

        calls += 1

        return _response(400)

    monkeypatch.setattr(
        "topo_cli.retry.time.sleep",
        lambda _: None,
    )

    response = execute_request(
        operation,
        max_retries=3,
        backoff=0.01,
    )

    assert response.status_code == 400
    assert calls == 1