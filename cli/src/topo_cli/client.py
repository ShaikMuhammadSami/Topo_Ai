from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from topo_cli.errors import (
    ApiFailure,
    AuthenticationFailure,
    ConnectionFailure,
    ResourceNotFound,
)
from topo_cli.retry import (
    execute_request,
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
        max_retries: int = 3,
        retry_backoff: float = 0.75,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.snapshot_capture_path = snapshot_capture_path
        self.max_retries = max(max_retries,0,)
        self.retry_backoff = max(retry_backoff,0.0,)

        headers = {
            "Accept": "application/json",
            "User-Agent": "topo-ai-cli/0.3.0",
        }

        if token:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.Client(
            base_url=self.api_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
            verify=verify_tls,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TopoClient":
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()

    @staticmethod
    def _encode_identifier(value: str) -> str:
        return quote(value, safe="")

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
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
                        f"API returned {response.status_code}: "
                        f"{detail}"
                    )

        except ValueError:
            pass

        content = response.text.strip()

        return (
            f"API returned {response.status_code}"
            + (f": {content[:1000]}" if content else "")
        )

    def _raise_for_status(
        self,
        response: httpx.Response,
    ) -> None:
        if response.status_code in {401, 403}:
            raise AuthenticationFailure(
                self._error_message(response)
            )

        if response.status_code == 404:
            raise ResourceNotFound(
                self._error_message(response)
            )

        if response.status_code >= 400:
            raise ApiFailure(
                self._error_message(response),
                status_code=response.status_code,
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> JsonValue:
        clean_params = (
                {
                 key: value
                 for key, value
                 in params.items()
                 if value is not None
                }
                if params
                else None
        )
        try:
            response = execute_request(
                lambda: self._client.request(
                  method=method,
                  url=path,
                  params=clean_params,
                  json=json_body,
                ),
                max_retries=(
                    self.max_retries
                ), 
                backoff=(
                    self.retry_backoff
                ),
            )

        except httpx.TimeoutException as exc:
            raise ConnectionFailure(
                "The Topo AI API request timed out: "
                f"{exc}"
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

        self._raise_for_status(response)

        if not response.content:
            return None

        try:
            return response.json()

        except ValueError:
            return response.text

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
                        if isinstance(item, dict)
                    ]

        return []

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        value = self._request(
            "GET",
            "/health",
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Topo AI health endpoint "
                "returned an invalid response."
            )

        return {
            "status": value.get("status", "unknown"),
            "service": value.get("service", "Topo AI"),
            "version": value.get("version", "unknown"),
            "api_url": self.api_url,
        }

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------

    def list_incidents(
        self,
        *,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            "/api/v1/incident-records",
            params={"limit": limit,"offset": offset,},
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

        incidents = self.list_incidents(limit=1000)

        for incident in incidents:
            if incident.get("incident_id") == incident_id:
                return incident

        raise ResourceNotFound(
            f"Incident not found: {incident_id}"
        )

    def blast_radius(
        self,
        incident_id: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/blast-radius"
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

    def incident_operational_context(
        self,
        incident_id: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(
                incident_id
            )
            + "/operational-context"
        )

        value = self._request(
            "GET",
            path,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Operational-context endpoint "
                "returned an invalid response."
            )

        return value

    def incident_response_plan(
        self,
        incident_id: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(
                incident_id
            )
            + "/response-plan"
        )

        value = self._request(
            "GET",
            path,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Response-plan endpoint "
                "returned an invalid response."
            )

        return value

    # ------------------------------------------------------------------
    # Explanations
    # ------------------------------------------------------------------

    def generate_explanation(
        self,
        *,
        incident_id: str,
        provider: str,
        force_regenerate: bool,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/explanations"
        )

        value = self._request(
            "POST",
            path,
            json_body={
                "provider": provider,
                "force_regenerate": force_regenerate,
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
            + self._encode_identifier(incident_id)
            + "/explanations/latest"
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
            + self._encode_identifier(incident_id)
            + "/explanations"
        )

        value = self._request(
            "GET",
            path,
            params={"limit": limit},
        )

        return self._collection(
            value,
            keys=(
                "items",
                "explanations",
                "records",
            ),
        )

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def list_snapshots(
        self,
        *,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            "/api/v1/snapshots",
            params={"limit": limit},
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

        params: dict[str, Any] | None = None
        json_body: dict[str, Any] | None = payload

        # The current backend expects namespace as a query parameter
        # for POST /api/v1/snapshots/capture.
        if path.rstrip("/") == "/api/v1/snapshots/capture":
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
    
    # ------------------------------------------------------------------
    # Copilot
    # ------------------------------------------------------------------

    def create_copilot_session(
        self,
        *,
        incident_id: str,
        title: str | None,
        provider: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/copilot/sessions"
        )

        value = self._request(
            "POST",
            path,
            json_body={
                "title": title,
                "provider": provider,
            },
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Copilot session endpoint "
                "returned an invalid response."
            )

        return value

    def list_copilot_sessions(
        self,
        *,
        incident_id: str,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/copilot/sessions"
        )

        value = self._request(
            "GET",
            path,
            params={"limit": limit,"offset": offset,},
        )

        return self._collection(
            value,
            keys=(
                "items",
                "sessions",
                "records",
            ),
        )

    def get_copilot_session(
        self,
        *,
        incident_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/copilot/sessions/"
            + self._encode_identifier(session_id)
        )

        value = self._request(
            "GET",
            path,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Copilot session endpoint "
                "returned an invalid response."
            )

        return value

    def send_copilot_message(
        self,
        *,
        incident_id: str,
        session_id: str,
        question: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/copilot/sessions/"
            + self._encode_identifier(session_id)
            + "/messages"
        )

        value = self._request(
            "POST",
            path,
            json_body={"question": question},
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Copilot message endpoint "
                "returned an invalid response."
            )

        return value

    # ------------------------------------------------------------------
    # Investigation plans
    # ------------------------------------------------------------------

    def generate_investigation_plan(
        self,
        *,
        incident_id: str,
        provider: str,
        force_regenerate: bool,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/investigation-plans"
        )

        value = self._request(
            "POST",
            path,
            json_body={
                "provider": provider,
                "force_regenerate": force_regenerate,
            },
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Investigation-plan endpoint "
                "returned an invalid response."
            )

        return value

    def list_investigation_plans(
        self,
        *,
        incident_id: str,
        limit: int,
        offset: int = 0
    ) -> list[dict[str, Any]]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/investigation-plans"
        )

        value = self._request(
            "GET",
            path,
            params={"limit": limit,"offset": offset,},
        )

        return self._collection(
            value,
            keys=(
                "items",
                "plans",
                "records",
            ),
        )

    def get_investigation_plan(
        self,
        *,
        incident_id: str,
        plan_id: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/investigation-plans/"
            + self._encode_identifier(plan_id)
        )

        value = self._request(
            "GET",
            path,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Investigation-plan endpoint "
                "returned an invalid response."
            )

        return value

    def update_investigation_step(
        self,
        *,
        incident_id: str,
        plan_id: str,
        step_id: str,
        status: str | None,
        finding: str | None,
        responder_notes: str | None,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/investigation-plans/"
            + self._encode_identifier(plan_id)
            + "/steps/"
            + self._encode_identifier(step_id)
        )

        body: dict[str, Any] = {}

        if status is not None:
            body["status"] = status

        if finding is not None:
            body["finding"] = finding

        if responder_notes is not None:
            body["responder_notes"] = responder_notes

        value = self._request(
            "PATCH",
            path,
            json_body=body,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Investigation-step endpoint "
                "returned an invalid response."
            )

        return value

    # ------------------------------------------------------------------
    # Post-incident reports
    # ------------------------------------------------------------------

    def generate_post_incident_report(
        self,
        *,
        incident_id: str,
        provider: str,
        force_regenerate: bool,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/reports"
        )

        value = self._request(
            "POST",
            path,
            json_body={
                "provider": provider,
                "force_regenerate": force_regenerate,
            },
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Post-incident report endpoint "
                "returned an invalid response."
            )

        return value

    def list_post_incident_reports(
        self,
        *,
        incident_id: str,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/reports"
        )

        value = self._request(
            "GET",
            path,
            params={"limit": limit,"offset": offset,},
        )

        return self._collection(
            value,
            keys=(
                "items",
                "reports",
                "records",
            ),
        )

    def get_post_incident_report(
        self,
        *,
        incident_id: str,
        report_id: str,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/reports/"
            + self._encode_identifier(report_id)
        )

        value = self._request(
            "GET",
            path,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Post-incident report endpoint "
                "returned an invalid response."
            )

        return value

    def update_post_incident_report(
        self,
        *,
        incident_id: str,
        report_id: str,
        status: str | None,
        reviewer_name: str | None,
        review_notes: str | None,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/reports/"
            + self._encode_identifier(report_id)
        )

        body: dict[str, Any] = {}

        if status is not None:
            body["status"] = status

        if reviewer_name is not None:
            body["reviewer_name"] = reviewer_name

        if review_notes is not None:
            body["review_notes"] = review_notes

        value = self._request(
            "PATCH",
            path,
            json_body=body,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Post-incident report update "
                "returned an invalid response."
            )

        return value

    def update_report_action(
        self,
        *,
        incident_id: str,
        report_id: str,
        action_item_id: str,
        status: str | None,
        owner_team: str | None,
        owner_contact: str | None,
        due_date: str | None,
        notes: str | None,
    ) -> dict[str, Any]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/reports/"
            + self._encode_identifier(report_id)
            + "/actions/"
            + self._encode_identifier(action_item_id)
        )

        body: dict[str, Any] = {}

        if status is not None:
            body["status"] = status

        if owner_team is not None:
            body["owner_team"] = owner_team

        if owner_contact is not None:
            body["owner_contact"] = owner_contact

        if due_date is not None:
            body["due_date"] = due_date

        if notes is not None:
            body["notes"] = notes

        value = self._request(
            "PATCH",
            path,
            json_body=body,
        )

        if not isinstance(value, dict):
            raise ApiFailure(
                "Report action endpoint returned "
                "an invalid response."
            )

        return value

    def export_post_incident_report(
        self,
        *,
        incident_id: str,
        report_id: str,
        export_format: str,
    ) -> tuple[bytes, str]:
        path = (
            "/api/v1/incidents/"
            + self._encode_identifier(incident_id)
            + "/reports/"
            + self._encode_identifier(report_id)
            + "/export"
        )

        try:
            response = execute_request(
                lambda: self._client.request(
                   method="GET",
                   url=path,
                   params={"format": export_format},
                ),
                max_retries=(
                    self.max_retries
                ),
                backoff=(
                    self.retry_backoff
                ),   
            )

        except httpx.TimeoutException as exc:
            raise ConnectionFailure(
                "The report export request "
                f"timed out: {exc}"
            ) from exc

        except httpx.ConnectError as exc:
            raise ConnectionFailure(
                "Unable to connect to Topo AI "
                f"at {self.api_url}: {exc}"
            ) from exc

        except httpx.HTTPError as exc:
            raise ConnectionFailure(
                "Report export request failed: "
                f"{exc}"
            ) from exc

        self._raise_for_status(response)

        extension = (
            "json"
            if export_format == "json"
            else "md"
        )
        filename = f"topo-report.{extension}"

        content_disposition = response.headers.get(
            "Content-Disposition",
            "",
        )

        match = re.search(
            r'filename="?([^";]+)"?',
            content_disposition,
            flags=re.IGNORECASE,
        )

        if match:
            filename = match.group(1)

        return response.content, filename
    
    def whoami(
     self,
    ) -> dict[str, Any]:
        value = self._request(
             "GET",
             "/api/v1/system/whoami",
            )

        if not isinstance(value, dict):
               raise ApiFailure(
                 "Identity endpoint returned "
                 "an invalid response."
                )
        return value
    
    def create_agent_enrollment_token(
     self,
     *,
     label: str | None,
     expires_in_minutes: int,
     max_uses: int,
    ) -> dict[str, Any]:
        value = self._request(
          "POST",
           (
             "/api/v1/agents/"
             "enrollment-tokens"
            ),
            json_body={
             "label": label,
             "expires_in_minutes":
                 expires_in_minutes,
             "max_uses": max_uses,
            },
        )

        if not isinstance(value, dict):
          raise ApiFailure(
             "Agent enrollment-token "
             "endpoint returned an "
             "invalid response."
            )

        return value


    def list_agents(
     self,
     *,
     limit: int,
     offset: int = 0,
    ) -> list[dict[str, Any]]:
        value = self._request(
         "GET",
         "/api/v1/agents",
         params={
             "limit": limit,
             "offset": offset,
            },
        )

        return self._collection(
         value,
         keys=(
             "items",
             "agents",
             "records",
            ),
        )


    def get_agent(
     self,
     agent_id: str,
    ) -> dict[str, Any]:
        value = self._request(
          "GET",
          (
             "/api/v1/agents/"
             + self._encode_identifier(
                 agent_id
                )
           ),
        )

        if not isinstance(value, dict):
            raise ApiFailure(
             "Agent endpoint returned an "
             "invalid response."
            )

        return value


    def get_agent_health(
     self,
     agent_id: str,
    ) -> dict[str, Any]:
        value = self._request(
         "GET",
         (
             "/api/v1/agents/"
             + self._encode_identifier(
                 agent_id
                )
             + "/health"
            ),
        )

        if not isinstance(value, dict):
         raise ApiFailure(
             "Agent-health endpoint returned "
             "an invalid response."
            )

        return value


    def revoke_agent(
     self,
     agent_id: str,
    ) -> dict[str, Any]:
        value = self._request(
         "POST",
         (
             "/api/v1/agents/"
             + self._encode_identifier(
                 agent_id
                )
             + "/revoke"
            ),
        )

        if not isinstance(value, dict):
         raise ApiFailure(
             "Agent revoke endpoint returned "
             "an invalid response."
            )

        return value
    
    def get_agent_plugins(
     self,
     agent_id: str,
    ) -> dict[str, Any]:
        value = self._request(
         "GET",
         (
             "/api/v1/agents/"
             + self._encode_identifier(
                 agent_id
                )
             + "/plugins"
            ),
        )

        if not isinstance(value, dict):
          raise ApiFailure(
             "Agent plugin endpoint "
             "returned an invalid response."
            )

        return value

    def list_agent_sensors(
     self,
     agent_id: str,
    ) -> list[dict[str, Any]]:
        value = self._request(
         "GET",
           (
             "/api/v1/agents/"
             + self._encode_identifier(
                 agent_id
                )
             + "/sensors"
            ),
        )

        return self._collection(
         value,
         keys=(
             "items",
             "sensors",
             "records",
            ),
        )


    def list_agent_runtime_dependencies(
     self,
     *,
     agent_id: str,
     window_minutes: int,
     limit: int,
     offset: int = 0,
    ) -> list[dict[str, Any]]:
        value = self._request(
         "GET",
          (
             "/api/v1/agents/"
             + self._encode_identifier(
                 agent_id
                )
             + "/runtime-dependencies"
            ),
         params={
             "window_minutes":
                 window_minutes,
             "limit": limit,
             "offset": offset,
            },
        )

        return self._collection(
         value,
         keys=(
             "items",
             "dependencies",
             "records",
            ),
        )
    
    def list_cloud_accounts(
     self,
     *,
     provider: str | None = None,
    ) -> list[dict[str, Any]]:
        value = self._request(
         "GET",
         "/api/v1/clouds/accounts",
         params={
             "provider": provider,
            },
        )

        return self._collection(
           value,
           keys=(
             "items",
             "accounts",
             "records",
            ),
        )


    def list_cloud_resources(
     self,
     *,
     provider: str | None,
     account_id: str | None,
     region: str | None,
     resource_type: str | None,
     tag_key: str | None,
     tag_value: str | None,
     limit: int,
     offset: int = 0,
    ) -> list[dict[str, Any]]:
        value = self._request(
         "GET",
         "/api/v1/clouds/resources",
          params={
             "provider": provider,
             "account_id":
                 account_id,
             "region": region,
             "resource_type":
                 resource_type,
             "tag_key": tag_key,
             "tag_value": tag_value,
             "limit": limit,
             "offset": offset,
            },
        )

        return self._collection(
         value,
         keys=(
             "items",
             "resources",
             "records",
            ),
        )


    def get_cloud_topology(
     self,
     *,
     provider: str,
     account_id: str | None,
     region: str | None,
    ) -> dict[str, Any]:
        value = self._request(
         "GET",
         "/api/v1/clouds/topology",
         params={
             "provider": provider,
             "account_id":
                 account_id,
             "region": region,
            },
        )

        if not isinstance(value, dict):
         raise ApiFailure(
             "Cloud topology endpoint "
             "returned an invalid response."
            )

        return value


    def get_agent_cloud_status(
     self,
     agent_id: str,
    ) -> dict[str, Any]:
        value = self._request(
         "GET",
         (
             "/api/v1/agents/"
             + self._encode_identifier(
                 agent_id
                )
             + "/cloud-status"
            ),
        )

        if not isinstance(value, dict):
          raise ApiFailure(
             "Agent cloud-status endpoint "
             "returned an invalid response."
            )

        return value
     # ------------------------------------------------------------------
     # Snapshot-derived changes
     # ------------------------------------------------------------------

    def list_changes(
        self,
        *,
        cluster_name: str | None,
        namespace: str | None,
        category: str | None,
        importance: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            "/api/v1/changes",
            params={
                "cluster_name":
                    cluster_name,
                "namespace":
                    namespace,
                "category":
                    category,
                "importance":
                    importance,
                "limit":
                    limit,
            },
        )

        return self._collection(
            value,
            keys=(
                "items",
                "changes",
                "records",
            ),
        )


    def get_change(
        self,
        change_id: str,
    ) -> dict[str, Any]:
        value = self._request(
            "GET",
            (
                "/api/v1/changes/"
                + self._encode_identifier(
                    change_id
                )
            ),
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Change endpoint returned "
                "an invalid response."
            )

        return value


    def create_changes_from_diff(
        self,
        *,
        from_snapshot_id: str,
        to_snapshot_id: str,
    ) -> dict[str, Any]:
        value = self._request(
            "POST",
            "/api/v1/changes/from-diff",
            params={
                "from_snapshot_id":
                    from_snapshot_id,
                "to_snapshot_id":
                    to_snapshot_id,
            },
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Change diff endpoint "
                "returned an invalid "
                "response."
            )

        return value
 
    # ------------------------------------------------------------------
    # Unified change events
    # ------------------------------------------------------------------

    def list_change_events(
        self,
        *,
        source: str | None,
        kind: str | None,
        environment: str | None,
        cluster_name: str | None,
        namespace: str | None,
        minimum_risk_score: int,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            "/api/v1/change-events",
            params={
                "source":
                    source,
                "kind":
                    kind,
                "environment":
                    environment,
                "cluster_name":
                    cluster_name,
                "namespace":
                    namespace,
                "minimum_risk_score":
                    minimum_risk_score,
                "limit":
                    limit,
                "offset":
                    offset,
            },
        )

        return self._collection(
            value,
            keys=(
                "items",
                "events",
                "records",
            ),
        )


    def get_change_event(
        self,
        event_id: str,
    ) -> dict[str, Any]:
        value = self._request(
            "GET",
            (
                "/api/v1/change-events/"
                + self._encode_identifier(
                    event_id
                )
            ),
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Change-event endpoint "
                "returned an invalid "
                "response."
            )

        return value


    def ingest_change_event(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        value = self._request(
            "POST",
            "/api/v1/change-events",
            json_body=payload,
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Change-event ingestion "
                "returned an invalid "
                "response."
            )

        return value


    def correlate_change_event(
        self,
        *,
        event_id: str,
        snapshot_id: str | None,
    ) -> dict[str, Any]:
        value = self._request(
            "POST",
            (
                "/api/v1/change-events/"
                + self._encode_identifier(
                    event_id
                )
                + "/correlate"
            ),
            json_body={
                "snapshot_id":
                    snapshot_id,
            },
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Change-event correlation "
                "returned an invalid "
                "response."
            )

        return value


    def get_incident_change_events(
        self,
        *,
        incident_id: str,
        lookback_minutes: int,
        after_minutes: int,
        limit: int,
    ) -> dict[str, Any]:
        value = self._request(
            "GET",
            (
                "/api/v1/incidents/"
                + self._encode_identifier(
                    incident_id
                )
                + "/change-events"
            ),
            params={
                "lookback_minutes":
                    lookback_minutes,
                "after_minutes":
                    after_minutes,
                "limit":
                    limit,
            },
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Incident change-events "
                "endpoint returned an "
                "invalid response."
            )

        return value


    def get_suspected_change_events(
        self,
        *,
        incident_id: str,
        lookback_minutes: int,
        after_minutes: int,
        minimum_score: float,
        limit: int,
    ) -> dict[str, Any]:
        value = self._request(
            "GET",
            (
                "/api/v1/incidents/"
                + self._encode_identifier(
                    incident_id
                )
                + "/suspected-change-events"
            ),
            params={
                "lookback_minutes":
                    lookback_minutes,
                "after_minutes":
                    after_minutes,
                "minimum_score":
                    minimum_score,
                "limit":
                    limit,
            },
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Suspected-change endpoint "
                "returned an invalid "
                "response."
            )

        return value
    # ---------------------------------------------------------------
    # Native change sources
    # ---------------------------------------------------------------

    def create_change_source(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        value = self._request(
            "POST",
            "/api/v1/change-sources",
            json_body=payload,
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Invalid change-source "
                "response."
            )

        return value


    def list_change_sources(
        self,
    ) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            "/api/v1/change-sources",
        )

        return self._collection(
            value,
            keys=(
                "items",
                "sources",
                "records",
            ),
        )


    def get_change_source(
        self,
        source_id: str,
    ) -> dict[str, Any]:
        value = self._request(
            "GET",
            (
                "/api/v1/change-sources/"
                + self._encode_identifier(
                    source_id
                )
            ),
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Invalid change-source "
                "response."
            )

        return value


    def doctor_change_source(
        self,
        source_id: str,
    ) -> dict[str, Any]:
        value = self._request(
            "GET",
            (
                "/api/v1/change-sources/"
                + self._encode_identifier(
                    source_id
                )
                + "/doctor"
            ),
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Invalid change-source "
                "doctor response."
            )

        return value


    def list_change_source_deliveries(
        self,
        *,
        source_id: str | None,
        status: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            (
                "/api/v1/"
                "change-sources/deliveries"
            ),
            params={
                "source_id": source_id,
                "status": status,
                "limit": limit,
            },
        )

        return self._collection(
            value,
            keys=(
                "items",
                "deliveries",
                "records",
            ),
        )


    def list_change_source_dead_letters(
        self,
        *,
        source_id: str | None,
        status: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            (
                "/api/v1/"
                "change-sources/"
                "dead-letters"
            ),
            params={
                "source_id": source_id,
                "status": status,
                "limit": limit,
            },
        )

        return self._collection(
            value,
            keys=(
                "items",
                "dead_letters",
                "records",
            ),
        )


    def replay_change_source_dead_letter(
        self,
        dead_letter_id: str,
    ) -> dict[str, Any]:
        value = self._request(
            "POST",
            (
                "/api/v1/"
                "change-sources/"
                "dead-letters/"
                + self._encode_identifier(
                    dead_letter_id
                )
                + "/replay"
            ),
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Invalid dead-letter "
                "replay response."
            )

        return value
    # ---------------------------------------------------------------
    # Causal RCA
    # ---------------------------------------------------------------

    def analyze_causal_rca(
        self,
        *,
        incident_id: str,
        lookback_minutes: int,
        after_minutes: int,
        minimum_change_score: float,
        max_topology_hops: int,
        max_hypotheses: int,
    ) -> dict[str, Any]:
        value = self._request(
            "POST",
            (
                "/api/v1/incidents/"
                + self._encode_identifier(
                    incident_id
                )
                + "/causal-rca"
            ),
            json_body={
                "lookback_minutes":
                    lookback_minutes,

                "after_minutes":
                    after_minutes,

                "minimum_change_score":
                    minimum_change_score,

                "max_topology_hops":
                    max_topology_hops,

                "max_hypotheses":
                    max_hypotheses,
            },
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Invalid causal RCA "
                "response."
            )

        return value


    def latest_causal_rca(
        self,
        *,
        incident_id: str,
    ) -> dict[str, Any]:
        value = self._request(
            "GET",
            (
                "/api/v1/incidents/"
                + self._encode_identifier(
                    incident_id
                )
                + "/causal-rca/latest"
            ),
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Invalid causal RCA "
                "response."
            )

        return value


    def get_causal_analysis(
        self,
        *,
        analysis_id: str,
    ) -> dict[str, Any]:
        value = self._request(
            "GET",
            (
                "/api/v1/"
                "causal-analyses/"
                + self._encode_identifier(
                    analysis_id
                )
            ),
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ApiFailure(
                "Invalid causal "
                "analysis response."
            )

        return value
