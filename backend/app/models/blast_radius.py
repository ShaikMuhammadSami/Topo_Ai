from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
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


class DependencyPath(BaseModel):

    model_config = ConfigDict(
        extra="forbid"
    )

    path: list[str]


class BlastRadiusResponse(BaseModel):

    model_config = ConfigDict(
        extra="forbid"
    )

    incident_id: str

    root_entity_id: str

    root_entity_name: str

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