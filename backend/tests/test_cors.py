from fastapi.testclient import TestClient

from app.main import app


def test_local_frontend_origin_is_allowed() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/v1/incidents/example/briefing",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Topo-Tenant-ID",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers[
            "access-control-allow-origin"
        ]
        == "http://127.0.0.1:3000"
    )
    assert "x-topo-tenant-id" in response.headers[
        "access-control-allow-headers"
    ].lower()


def test_unknown_frontend_origin_is_not_allowed() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/v1/incidents/example/briefing",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert (
        "access-control-allow-origin"
        not in response.headers
    )
