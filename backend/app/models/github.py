from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class GitHubConnectionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connected: bool
    repository: str
    private: bool
    default_branch: str
    latest_commit_sha: str | None

    api_url: str
    authenticated: bool


class GitHubEnrichmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_snapshot_id: str
    enriched_snapshot_id: str

    repository: str

    commits_collected: int

    mapped_commit_count: int
    mapped_image_count: int
    commit_image_relationship_count: int

    unresolved_image_count: int

    warnings: list[str] = Field(
        default_factory=list
    )