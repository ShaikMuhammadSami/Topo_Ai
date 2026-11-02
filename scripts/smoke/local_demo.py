"""Smoke-check the localhost Topo AI demo using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASELINE_ID = "snapshot:demo-cluster:local-demo-baseline-v1"
FAILURE_ID = "snapshot:demo-cluster:local-demo-failure-v1"


def get_json(url: str, headers: dict[str, str] | None = None):
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for(url: str, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            request = Request(url)
            with urlopen(request, timeout=3) as response:
                if 200 <= response.status < 300:
                    return
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(1)
    raise SystemExit(
        f"Timed out waiting for {url}: {last_error or 'no successful response'}"
    )


def require_nonempty_list(label: str, value) -> list:
    if not isinstance(value, list) or not value:
        raise SystemExit(f"The {label} API returned no demo records.")
    print(f"{label}: {len(value)}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the running local Topo AI demo."
    )
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://127.0.0.1:3000")
    args = parser.parse_args()

    backend = args.backend_url.rstrip("/")
    frontend = args.frontend_url.rstrip("/")

    wait_for(f"{backend}/ready")
    wait_for(f"{frontend}/app")

    health = get_json(f"{backend}/health")
    if health.get("status") != "available":
        raise SystemExit("The backend health endpoint returned an unexpected status.")

    tenants = get_json(f"{backend}/api/v1/tenants")
    demo = next(
        (
            tenant
            for tenant in tenants
            if tenant.get("display_name") == "Topo AI Local Demo"
        ),
        None,
    )
    if demo is None or not demo.get("tenant_id"):
        raise SystemExit(
            "The demo workspace is missing. Run docker compose exec backend "
            "python -m app.demo_seed first."
        )

    headers = {"X-Topo-Tenant-ID": demo["tenant_id"]}
    snapshots = require_nonempty_list(
        "snapshots",
        get_json(f"{backend}/api/v1/snapshots?limit=20", headers),
    )
    snapshot_ids = {item.get("snapshot_id") for item in snapshots}
    if not {BASELINE_ID, FAILURE_ID}.issubset(snapshot_ids):
        raise SystemExit("The baseline and failure snapshots were not both found.")

    require_nonempty_list(
        "changes",
        get_json(f"{backend}/api/v1/changes?limit=100", headers),
    )
    require_nonempty_list(
        "signals",
        get_json(f"{backend}/api/v1/signals?limit=100", headers),
    )
    require_nonempty_list(
        "incidents",
        get_json(f"{backend}/api/v1/incident-records?limit=100", headers),
    )

    print("Frontend route: available")
    print("Local demo smoke check passed.")


if __name__ == "__main__":
    main()
