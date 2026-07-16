from __future__ import annotations
from urllib.parse import quote
from typing import Any

import httpx

from topo_cli.errors import (
    ApiFailure,
    AuthenticationFailure,
    ConnectionFailure,
    ResourceNotFound,
)


JsonValue = (
    dict[str, Any]
    | list[Any]
    | str
    | int
    | float
    | bool
    | None
)


class TopoClient:
    def __init__(
        self,
        *,
        api_url: str,
        token: str | None,
        timeout: float,
        verify_tls: bool,
        snapshot_capture_path: str,
    ) -> None:
        self.api_url = api_url.rstrip("/")

        self.snapshot_capture_path = (
            snapshot_capture_path
        )

        headers = {
            "Accept": "application/json",
            "User-Agent":
                "topo-ai-cli/0.1.0",
        }

        if token:
            headers["Authorization"] = (
                f"Bearer {token}"
            )

        self._client = httpx.Client(
            base_url=self.api_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
            verify=verify_tls,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: (
            dict[str, Any] | None
        ) = None,
        json_body: (
            dict[str, Any] | None
        ) = None,
    ) -> JsonValue:
        try:
            response = self._client.request(
                method=method,
                url=path,
                params=params,
                json=json_body,
            )

        except httpx.TimeoutException as exc:
            raise ConnectionFailure(
                "The Topo AI API request "
                f"timed out: {exc}"
            ) from exc

        except httpx.ConnectError as exc:
            raise ConnectionFailure(
                "Unable to connect to Topo AI "
                f"at {self.api_url}: {exc}"
            ) from exc

        except httpx.HTTPError as exc:
            raise ConnectionFailure(
                "Topo AI API request failed: "
                f"{exc}"
            ) from exc

        if response.status_code in {
            401,
            403,
        }:
            raise AuthenticationFailure(
                self._error_message(
                    response
                )
            )

        if response.status_code == 404:
            raise ResourceNotFound(
                self._error_message(
                    response
                )
            )

        if response.status_code >= 400:
            raise ApiFailure(
                self._error_message(
                    response
                ),
                status_code=(
                    response.status_code
                ),
            )

        if not response.content:
            return None

        try:
            return response.json()

        except ValueError:
            return response.text

    @staticmethod
    def _error_message(
        response: httpx.Response,
    ) -> str:
        try:
            value = response.json()

            if isinstance(value, dict):
                detail = (
                    value.get("detail")
                    or value.get("message")
                    or value.get("error")
                )

                if detail:
                    return (
                        f"API returned "
                        f"{response.status_code}: "
                        f"{detail}"
                    )

        except ValueError:
            pass

        content = response.text.strip()

        return (
            f"API returned "
            f"{response.status_code}"
            + (
                f": {content[:1000]}"
                if content
                else ""
            )
        )

    @staticmethod
    def _collection(
        value: JsonValue,
        *,
        keys: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [
                item
                for item in value
                if isinstance(item, dict)
            ]

        if isinstance(value, dict):
            for key in keys:
                items = value.get(key)

                if isinstance(items, list):
                    return [
                        item
                        for item in items
                        if isinstance(
                            item,
                            dict,
                        )
                    ]

        return []

    def health(self) -> dict[str, Any]:
        value = self._request(
            "GET",
            "/openapi.json",
        )
        
        if not isinstance(value, dict):
            raise ApiFailure(
                "Topo AI returned an invalid "
                "OpenAPI response."
            )

        info = value.get("info", {})

        return {
            "status": "available",
            "api_url": self.api_url,
            "title": (
                info.get("title")
                if isinstance(info, dict)
                else None
            ),
            "version": (
                info.get("version")
                if isinstance(info, dict)
                else None
            ),
            "endpoint_count": len(
                value.get("paths", {})
            ),
        }

    def list_incidents(
        self,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            "/api/v1/incident-records",
            params={
                "limit": limit,
            },
        )

        return self._collection(
            value,
            keys=(
                "items",
                "records",
                "incidents",
            ),
        )

    def get_incident(
        self,
        incident_id: str,
    ) -> dict[str, Any]:
        encoded = httpx.URL(
            "http://localhost"
        ).copy_with(
            path=f"/{incident_id}"
        ).path.lstrip("/")

        path = (
            "/api/v1/incident-records/"
            + self._encode_identifier(incident_id)
        )

        try:
            value = self._request(
                "GET",
                path,
            )

            if isinstance(value, dict):
                return value

        except ResourceNotFound:
            pass

        incidents = self.list_incidents(
            limit=1000
        )

        for incident in incidents:
            if (
                incident.get("incident_id")
                == incident_id
            ):
                return incident

        raise ResourceNotFound(
            f"Incident not found: "
            f"{incident_id}"
        )

    def blast_radius(
        self,
        incident_id: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            +"/blast-radius"
        )

        value = self._request(
            "GET",
            path,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Blast-radius endpoint "
                "returned an invalid response."
            )

        return value

    def generate_explanation(
        self,
        *,
        incident_id: str,
        provider: str,
        force_regenerate: bool,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            +self._encode_identifier(incident_id)
            +"/explanations"
        )

        value = self._request(
            "POST",
            path,
            json_body={
                "provider": provider,
                "force_regenerate":
                    force_regenerate,
            },
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Explanation endpoint returned "
                "an invalid response."
            )

        return value

    def latest_explanation(
        self,
        incident_id: str,
    ) -> dict[str, Any] | None:
        path = (
            "/api/v1/incidents/"
            +self._encode_identifier(incident_id)
            +"/explanations/latest"
        )

        value = self._request(
            "GET",
            path,
        )

        if value is None:
            return None

        if not isinstance(value, dict):
            raise ApiFailure(
                "Latest explanation endpoint "
                "returned an invalid response."
            )

        return value

    def explanation_history(
        self,
        *,
        incident_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        path = (
            "/api/v1/incidents/"
            +self._encode_identifier(incident_id)
            +"/explanations"
        )

        value = self._request(
            "GET",
            path,
            params={
                "limit": limit,
            },
        )

        return self._collection(
            value,
            keys=(
                "items",
                "explanations",
                "records",
            ),
        )

    def list_snapshots(
        self,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            "/api/v1/snapshots",
            params={
                "limit": limit,
            },
        )

        return self._collection(
            value,
            keys=(
                "items",
                "snapshots",
                "records",
            ),
        )

    def get_snapshot(
        self,
        snapshot_id: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/snapshots/"
            + self._encode_identifier(snapshot_id)
        )

        value = self._request(
            "GET",
            path,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Snapshot endpoint returned "
                "an invalid response."
            )

        return value

    def capture_snapshot(
        self,
        payload: dict[str, Any],
        *,
        endpoint_override: str | None,
    ) -> dict[str, Any]:
        path = (
            endpoint_override
            or self.snapshot_capture_path
        )

        # value = self._request(
        #     "POST",
        #     path,
        #     json_body=payload,
        # )

        # if not isinstance(value, dict):
        #     raise ApiFailure(
        #         "Snapshot capture endpoint "
        #         "returned an invalid response."
        #     )

        # return value
        params: dict[str, Any] | None = None
        json_body: dict[str, Any] | None = payload

     # The current Topo backend expects namespace
     # as a query parameter, not in the JSON body.
        if (
         path.rstrip("/")
         == "/api/v1/snapshots/capture"
        ):
            scope = payload.get("scope", {})

            namespace = (
               scope.get("namespace")
               if isinstance(scope, dict)
               else None
            )

            params = (
               {"namespace": namespace}
               if namespace
               else None
            )

            json_body = None

        value = self._request(
            "POST",
            path,
            params=params,
            json_body=json_body,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
             "Snapshot capture endpoint "
              "returned an invalid response."
            )

        return value
    
    @staticmethod
    def _encode_identifier(
        value: str,
    ) -> str:
        return quote(
            value,
            safe="",
        )