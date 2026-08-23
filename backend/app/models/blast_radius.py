from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.services.blast_impact_policy import (
    BLAST_POLICY_VERSION,
    BlastImpactSemantic,
)


class ImpactLevel(str):
    pass


class BlastRadiusEntity(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    entity_id: str

    entity_kind: str | None = None

    entity_name: str

    namespace: str | None = None
    
    distance: int = Field(
        ge=0
    )

    impact: str

    impact_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    relationship: str | None = None
    risk_score: float | None = None  # 0.0–1.0, higher means more risk

    impact_semantic: BlastImpactSemantic = (
        BlastImpactSemantic.UNKNOWN_UNPROVEN
    )
    blast_policy_version: str = BLAST_POLICY_VERSION
    impact_score_semantics: str = (
        "distance_heuristic_not_probability"
    )
    evidence_ids: list[str] = Field(default_factory=list)
    path_relationship_ids: list[str] = Field(default_factory=list)
    path_traversal_directions: list[str] = Field(default_factory=list)
    path_relationship_origins: list[str | None] = Field(default_factory=list)
    path_relationship_source_systems: list[str] = Field(default_factory=list)
    aggregate_evidence: dict[str, object] | None = None


class DependencyPath(BaseModel):

    model_config = ConfigDict(
        extra="forbid"
    )

    path: list[str]
    relationship_ids: list[str] = Field(default_factory=list)
    predicates: list[str] = Field(default_factory=list)
    traversal_directions: list[str] = Field(default_factory=list)
    relationship_origins: list[str | None] = Field(default_factory=list)
    relationship_source_systems: list[str] = Field(default_factory=list)
    impact_semantic: BlastImpactSemantic = (
        BlastImpactSemantic.UNKNOWN_UNPROVEN
    )
    blast_policy_version: str = BLAST_POLICY_VERSION


class BlastRadiusResponse(BaseModel):

    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str

    root_entity_id: str

    root_entity_name: str

    blast_policy_version: str = BLAST_POLICY_VERSION
    warnings: list[str] = Field(default_factory=list)

    affected_entity_count: int

    direct_impact_count: int

    indirect_impact_count: int

    potential_impact_count: int

    affected_entities: list[
        BlastRadiusEntity
    ] = Field(
        default_factory=list
    )

    dependency_paths: list[
        DependencyPath
    ] = Field(
        default_factory=list
    )
