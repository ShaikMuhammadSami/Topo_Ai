from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


MAX_GITHUB_ARTIFACT_BYTES = 32 * 1024 * 1024


class GitHubConnectorError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubSettings:
    owner: str
    repository: str

    token: str | None

    api_url: str
    api_version: str

    timeout_seconds: float
    commit_limit: int

    @property
    def full_name(self) -> str:
        return (
            f"{self.owner}/"
            f"{self.repository}"
        )

    @classmethod
    def from_environment(
        cls,
    ) -> "GitHubSettings":
        owner = os.getenv(
            "TOPO_GITHUB_OWNER",
            "",
        ).strip()

        repository = os.getenv(
            "TOPO_GITHUB_REPO",
            "",
        ).strip()

        if not owner or not repository:
            raise RuntimeError(
                "TOPO_GITHUB_OWNER and "
                "TOPO_GITHUB_REPO must be set."
            )

        commit_limit = int(
            os.getenv(
                "TOPO_GITHUB_COMMIT_LIMIT",
                "50",
            )
        )

        return cls(
            owner=owner,
            repository=repository,
            token=(
                os.getenv(
                    "TOPO_GITHUB_TOKEN"
                )
                or None
            ),
            api_url=os.getenv(
                "TOPO_GITHUB_API_URL",
                "https://api.github.com",
            ).rstrip("/"),
            api_version=os.getenv(
                "TOPO_GITHUB_API_VERSION",
                "2026-03-10",
            ),
            timeout_seconds=float(
                os.getenv(
                    "TOPO_GITHUB_TIMEOUT_SECONDS",
                    "20",
                )
            ),
            commit_limit=max(
                1,
                min(commit_limit, 100),
            ),
        )


class GitHubConnector:
    def __init__(
        self,
        settings: GitHubSettings,
    ) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": (
                "application/vnd.github+json"
            ),
            "X-GitHub-Api-Version": (
                self.settings.api_version
            ),
            "User-Agent": (
                "topo-ai-infrastructure-"
                "intelligence"
            ),
        }

        if self.settings.token:
            headers["Authorization"] = (
                f"Bearer "
                f"{self.settings.token}"
            )

        return headers

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = (
            f"{self.settings.api_url}/"
            f"{path.lstrip('/')}"
        )

        try:
            response = httpx.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=(
                    self.settings
                    .timeout_seconds
                ),
                follow_redirects=True,
            )

            response.raise_for_status()

        except httpx.HTTPStatusError as exc:
            status_code = (
                exc.response.status_code
            )

            try:
                body = exc.response.json()
                detail = body.get(
                    "message",
                    exc.response.text,
                )

            except ValueError:
                detail = exc.response.text

            raise GitHubConnectorError(
                "GitHub API returned "
                f"{status_code}: {detail}"
            ) from exc

        except httpx.RequestError as exc:
            raise GitHubConnectorError(
                "Could not reach the GitHub API: "
                f"{exc}"
            ) from exc

        try:
            return response.json()

        except ValueError as exc:
            raise GitHubConnectorError(
                "GitHub returned an invalid "
                "JSON response."
            ) from exc

    def get_repository(
        self,
    ) -> dict[str, Any]:
        payload = self._get(
            (
                f"/repos/"
                f"{self.settings.owner}/"
                f"{self.settings.repository}"
            )
        )

        if not isinstance(payload, dict):
            raise GitHubConnectorError(
                "Unexpected repository response."
            )

        return payload

    def list_commits(
        self,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        requested_limit = (
            limit
            or self.settings.commit_limit
        )

        requested_limit = max(
            1,
            min(requested_limit, 100),
        )

        payload = self._get(
            (
                f"/repos/"
                f"{self.settings.owner}/"
                f"{self.settings.repository}/"
                "commits"
            ),
            params={
                "per_page": requested_limit,
            },
        )

        if not isinstance(payload, list):
            raise GitHubConnectorError(
                "Unexpected commit-list response."
            )

        return [
            item
            for item in payload
            if isinstance(item, dict)
        ]

    def get_commit(
        self,
        sha: str,
    ) -> dict[str, Any]:
        payload = self._get(
            (
                f"/repos/{self.settings.owner}/"
                f"{self.settings.repository}/commits/{sha}"
            )
        )
        if not isinstance(payload, dict):
            raise GitHubConnectorError(
                "Unexpected commit response."
            )
        return payload

    def connection_information(
        self,
    ) -> dict[str, Any]:
        repository = self.get_repository()

        commits = self.list_commits(
            limit=1
        )

        latest_sha = None

        if commits:
            value = commits[0].get("sha")

            if isinstance(value, str):
                latest_sha = value

        return {
            "connected": True,
            "repository": (
                repository.get("full_name")
                or self.settings.full_name
            ),
            "private": bool(
                repository.get("private")
            ),
            "default_branch": (
                repository.get(
                    "default_branch"
                )
                or "unknown"
            ),
            "latest_commit_sha": (
                latest_sha
            ),
            "api_url": (
                self.settings.api_url
            ),
            "authenticated": bool(
                self.settings.token
            ),
        }
    def list_workflow_runs(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        requested_limit = max(
           1,
           min(limit, 100),
        )

        payload = self._get(
           (
            f"/repos/"
            f"{self.settings.owner}/"
            f"{self.settings.repository}/"
            "actions/runs"
          ),
           params={
            "per_page": requested_limit,
          },
    )

        if not isinstance(payload, dict):
            raise GitHubConnectorError(
            "Unexpected workflow-run response."
            )
 
        workflow_runs = payload.get(
            "workflow_runs"
        ) 

        if not isinstance(workflow_runs, list):
            raise GitHubConnectorError(
                 "GitHub response did not contain "
                "a workflow_runs list."
        )

        return [
            item
            for item in workflow_runs
            if isinstance(item, dict)
        ]

    def get_workflow_run(
        self,
        run_id: str | int,
    ) -> dict[str, Any]:
        payload = self._get(
            (
                f"/repos/{self.settings.owner}/"
                f"{self.settings.repository}/actions/runs/{run_id}"
            )
        )
        if not isinstance(payload, dict):
            raise GitHubConnectorError(
                "Unexpected workflow-run response."
            )
        return payload

    def list_workflow_run_artifacts(
        self,
        run_id: str | int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        requested_limit = max(1, min(limit, 100))
        payload = self._get(
            (
                f"/repos/{self.settings.owner}/"
                f"{self.settings.repository}/actions/runs/{run_id}/artifacts"
            ),
            params={"per_page": requested_limit},
        )
        if not isinstance(payload, dict) or not isinstance(
            payload.get("artifacts"), list
        ):
            raise GitHubConnectorError(
                "Unexpected workflow-artifact response."
            )
        return [
            item
            for item in payload["artifacts"]
            if isinstance(item, dict)
        ]

    def download_actions_artifact(
        self,
        artifact_id: str | int,
    ) -> bytes:
        url = (
            f"{self.settings.api_url}/repos/{self.settings.owner}/"
            f"{self.settings.repository}/actions/artifacts/{artifact_id}/zip"
        )
        try:
            response = httpx.get(
                url,
                headers=self._headers(),
                timeout=self.settings.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GitHubConnectorError(
                "GitHub artifact download returned "
                f"{exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise GitHubConnectorError(
                f"Could not download the GitHub artifact: {exc}"
            ) from exc
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_GITHUB_ARTIFACT_BYTES:
            raise GitHubConnectorError(
                "GitHub build artifact exceeds the safe size limit."
            )
        payload = response.content
        if len(payload) > MAX_GITHUB_ARTIFACT_BYTES:
            raise GitHubConnectorError(
                "GitHub build artifact exceeds the safe size limit."
            )
        return payload
