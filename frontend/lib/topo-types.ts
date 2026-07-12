export type SnapshotSummary = {
  snapshot_id: string;
  schema_version: string;
  collected_at: string;
  collector_name: string;
  collector_version: string;
  cluster_name: string | null;
  namespace: string | null;
  entity_count: number;
  relationship_count: number;
  evidence_count: number;
};

export type TopologyEntity = {
  id: string;
  entity_type: string;
  kind: string;
  name: string;
  source_system: string;
  external_id: string | null;
  environment: string | null;
  observed_at: string;
  confidence: number;
  labels: Record<string, string>;
  properties: Record<string, unknown>;
};

export type TopologyRelationship = {
  id: string;
  source_entity_id: string;
  target_entity_id: string;
  relationship_type: string;
  source_system: string;
  observed_at: string;
  confidence: number;
  directed: boolean;
  evidence_ids: string[];
  properties: Record<string, unknown>;
};

export type TopologyEvidence = {
  id: string;
  evidence_type: string;
  source_system: string;
  summary: string;
  observed_at: string;
  related_entity_ids: string[];
  related_relationship_ids: string[];
  payload: Record<string, unknown>;
};

export type GraphSnapshot = {
  schema_version: string;
  snapshot_id: string;
  collected_at: string;
  collector_name: string;
  collector_version: string;
  scope: Record<string, string>;
  entities: TopologyEntity[];
  relationships: TopologyRelationship[];
  evidence: TopologyEvidence[];
  metadata: Record<string, unknown>;
};
export type EntityChange = {
  entity_id: string
  kind: string
  name: string
  changed_fields: Record<
    string,
    {
      before: unknown
      after: unknown
    }
  >
}

export type RelationshipChange = {
  relationship_id: string
  source_entity_id: string
  target_entity_id: string
  relationship_type: string
  changed_fields: Record<
    string,
    {
      before: unknown
      after: unknown
    }
  >
}

export type SnapshotDiffResult = {
  from_snapshot_id: string
  to_snapshot_id: string

  added_entities: TopologyEntity[]
  removed_entities: TopologyEntity[]
  changed_entities: EntityChange[]

  added_relationships: TopologyRelationship[]
  removed_relationships: TopologyRelationship[]
  changed_relationships: RelationshipChange[]

  summary: {
    added_entities: number
    removed_entities: number
    changed_entities: number
    added_relationships: number
    removed_relationships: number
    changed_relationships: number
  }
}

export type IdentityMatchMethod =
  | "label_exact"
  | "owner_reference"
  | "service_selector"
  | "image_reference"
  | "name_heuristic"
  | "manual_override"

export type IdentityRole =
  | "deployment"
  | "replica_set"
  | "pod"
  | "service"

export type IdentityMember = {
  entity_id: string
  kind: string
  name: string
  role: IdentityRole
  match_method: IdentityMatchMethod
  confidence: number
  evidence: string[]
}

export type LogicalIdentity = {
  identity_id: string
  canonical_name: string
  cluster: string | null
  namespace: string | null
  environment: string | null
  confidence: number
  members: IdentityMember[]
  image_references: string[]
  aliases: string[]
  warnings: string[]
}

export type IdentityResolutionResult = {
  snapshot_id: string
  generated_at: string
  identities: LogicalIdentity[]
  unresolved_entity_ids: string[]
  excluded_entity_ids: string[]
  warnings: string[]
}

export type IdentityResolutionSummary = {
  snapshot_id: string
  generated_at: string
  identity_count: number
  unresolved_count: number
  excluded_count: number
}

export type IdentityOverrideAction =
  | "assign"
  | "exclude"

export type IdentityOverrideCreate = {
  cluster_name: string
  namespace: string
  entity_kind: string
  entity_name: string
  action: IdentityOverrideAction
  canonical_name?: string | null
  reason: string
}

export type IdentityOverrideView = {
  override_id: string
  cluster_name: string
  namespace: string
  entity_kind: string
  entity_name: string
  action: IdentityOverrideAction
  canonical_name: string | null
  reason: string
  active: boolean
  created_at: string
  updated_at: string
}

export type IdentityOverrideDeleteResult = {
  status: string
  override_id: string
}

export type SignalType =
  | "kubernetes_event"

export type SignalSeverity =
  | "info"
  | "warning"
  | "error"
  | "critical"

export type SignalCategory =
  | "availability"
  | "health"
  | "scheduling"
  | "image"
  | "storage"
  | "configuration"
  | "lifecycle"
  | "security"
  | "other"

export type SignalSummary = {
  signal_id: string
  signal_type: SignalType
  severity: SignalSeverity
  category: SignalCategory

  title: string
  reason: string | null

  first_observed_at: string
  last_observed_at: string

  occurrence_count: number

  cluster_name: string
  namespace: string | null

  topology_snapshot_id: string | null

  involved_entity_id: string | null
  involved_object_kind: string | null
  involved_object_name: string | null
}

export type NormalizedSignal = {
  signal_id: string
  fingerprint: string

  signal_type: SignalType
  severity: SignalSeverity
  category: SignalCategory

  source_system: string

  title: string
  summary: string

  reason: string | null
  action: string | null

  first_observed_at: string
  last_observed_at: string

  occurrence_count: number

  cluster_name: string
  namespace: string | null

  topology_snapshot_id: string | null

  involved_entity_id: string | null
  involved_object_uid: string | null
  involved_object_kind: string | null
  involved_object_name: string | null

  reporting_controller: string | null
  reporting_instance: string | null

  attributes: Record<string, unknown>
  raw_payload: Record<string, unknown>
}

export type ChangeType =
  | "entity_added"
  | "entity_removed"
  | "entity_updated"
  | "relationship_added"
  | "relationship_removed"
  | "relationship_updated"

export type ChangeCategory =
  | "deployment"
  | "scaling"
  | "image"
  | "configuration"
  | "runtime"
  | "service"
  | "networking"
  | "topology"
  | "other"

export type ChangeImportance =
  | "low"
  | "medium"
  | "high"

export type ChangeSummary = {
  change_id: string

  change_type: ChangeType
  category: ChangeCategory
  importance: ChangeImportance

  title: string
  summary: string

  detected_at: string

  from_snapshot_id: string
  to_snapshot_id: string

  cluster_name: string
  namespace: string | null

  entity_id: string | null
  entity_kind: string | null
  entity_name: string | null

  relationship_id: string | null
  relationship_type: string | null
}

export type NormalizedChange = {
  change_id: string
  fingerprint: string

  change_type: ChangeType
  category: ChangeCategory
  importance: ChangeImportance

  source_system: string

  title: string
  summary: string

  detected_at: string

  from_snapshot_id: string
  to_snapshot_id: string

  cluster_name: string
  namespace: string | null

  entity_id: string | null
  entity_kind: string | null
  entity_name: string | null

  relationship_id: string | null
  relationship_type: string | null

  source_entity_id: string | null
  target_entity_id: string | null

  changed_fields: Record<
    string,
    {
      before: unknown
      after: unknown
    }
  >

  before: Record<string, unknown> | null
  after: Record<string, unknown> | null

  related_entity_ids: string[]

  attributes: Record<string, unknown>
}

export type EvidenceDirection =
  | "supporting"
  | "counter"

export type IncidentEvidence = {
  evidence_id: string
  direction: EvidenceDirection

  code: string
  summary: string

  weight: number

  source_type: string
  source_id: string

  observed_at: string | null

  related_entity_ids: string[]

  attributes: Record<string, unknown>
}

export type RootCauseHypothesis = {
  hypothesis_id: string
  rank: number

  change_id: string

  title: string
  explanation: string

  score: number

  change_type: ChangeType
  category: ChangeCategory
  importance: ChangeImportance

  change_detected_at: string

  minutes_before_signal: number

  graph_distance: number | null

  affected_entity_id: string | null
  changed_entity_id: string | null
  changed_entity_kind: string | null
  changed_entity_name: string | null

  supporting_evidence: IncidentEvidence[]
  counter_evidence: IncidentEvidence[]

  scoring_components: Record<string, number>
}

export type IncidentAnalysis = {
  analysis_id: string
  algorithm_version: string

  signal_id: string
  topology_snapshot_id: string

  generated_at: string

  incident_title: string

  cluster_name: string
  namespace: string | null

  symptom_reason: string | null
  symptom_summary: string
  symptom_entity_id: string | null

  signal_first_observed_at: string
  signal_last_observed_at: string

  lookback_minutes: number
  grace_minutes: number
  max_graph_hops: number

  candidate_count: number

  hypotheses: RootCauseHypothesis[]
  warnings: string[]
}

export type IncidentAnalysisSummary = {
  analysis_id: string
  signal_id: string

  generated_at: string

  incident_title: string

  cluster_name: string
  namespace: string | null

  candidate_count: number
  hypothesis_count: number

  top_hypothesis_title: string | null
  top_hypothesis_score: number | null
}

export type RecommendationStatus =
  | "proposed"
  | "approved"
  | "applied"
  | "dismissed"

export type RecommendationRisk =
  | "low"
  | "medium"
  | "high"

export type RecommendationActionType =
  | "rollback_deployment"
  | "restore_replica_count"
  | "restore_configuration"
  | "verify_image_access"
  | "investigate_runtime"

export type RecommendationStep = {
  order: number

  title: string
  description: string

  command: string | null

  requires_approval: boolean

  expected_result: string | null
}

export type RemediationRecommendation = {
  recommendation_id: string
  algorithm_version: string

  analysis_id: string
  hypothesis_id: string
  signal_id: string
  change_id: string

  generated_at: string

  title: string
  rationale: string

  action_type: RecommendationActionType
  status: RecommendationStatus

  confidence: number
  risk: RecommendationRisk

  cluster_name: string
  namespace: string | null

  target_entity_id: string | null
  target_entity_kind: string | null
  target_entity_name: string | null

  requires_approval: boolean

  steps: RecommendationStep[]

  expected_outcome: string

  verification_checks: string[]
  safety_notes: string[]
  evidence_ids: string[]

  attributes: Record<string, unknown>

  status_note: string | null
  applied_at: string | null
}

export type RecommendationSummary = {
  recommendation_id: string

  analysis_id: string
  signal_id: string

  generated_at: string

  title: string
  action_type: RecommendationActionType

  status: RecommendationStatus
  confidence: number
  risk: RecommendationRisk

  namespace: string | null

  target_entity_kind: string | null
  target_entity_name: string | null

  applied_at: string | null
}

export type RecommendationStatusUpdate = {
  status: RecommendationStatus
  note?: string | null
}

export type RecoveryStatus =
  | "verified"
  | "failed"
  | "inconclusive"

export type RecoveryCheckStatus =
  | "pass"
  | "fail"
  | "unknown"

export type RecoveryCheck = {
  code: string
  title: string

  status: RecoveryCheckStatus

  summary: string

  expected: string | null
  observed: string | null

  source_type: string
  source_id: string

  checked_at: string

  attributes: Record<string, unknown>
}

export type RecoveryVerification = {
  verification_id: string
  algorithm_version: string

  recommendation_id: string
  analysis_id: string
  signal_id: string

  pre_snapshot_id: string
  post_snapshot_id: string

  generated_at: string
  applied_at: string

  status: RecoveryStatus
  confidence: number

  summary: string

  cluster_name: string
  namespace: string | null

  target_entity_id: string | null
  target_entity_kind: string | null
  target_entity_name: string | null

  passed_count: number
  failed_count: number
  unknown_count: number

  checks: RecoveryCheck[]
  warnings: string[]
}

export type RecoveryVerificationSummary = {
  verification_id: string

  recommendation_id: string
  analysis_id: string
  signal_id: string

  generated_at: string

  status: RecoveryStatus
  confidence: number

  summary: string

  cluster_name: string
  namespace: string | null

  target_entity_kind: string | null
  target_entity_name: string | null

  passed_count: number
  failed_count: number
  unknown_count: number
}

export type IncidentStatus =
  | "open"
  | "investigating"
  | "recommended"
  | "remediating"
  | "resolved"
  | "dismissed"

export type IncidentSeverity =
  | "info"
  | "warning"
  | "error"
  | "critical"

export type IncidentRecordSummary = {
  incident_id: string

  status: IncidentStatus
  severity: IncidentSeverity

  title: string

  cluster_name: string
  namespace: string | null

  affected_object_kind: string | null
  affected_object_name: string | null

  first_observed_at: string
  last_observed_at: string

  top_hypothesis_title: string | null
  top_hypothesis_score: number | null

  recommendation_count: number
  recovery_status: string | null

  occurrence_count: number
}

export type IncidentRecordView = {
  incident_id: string
  fingerprint: string

  status: IncidentStatus
  severity: IncidentSeverity

  title: string
  summary: string

  cluster_name: string
  namespace: string | null

  primary_signal_id: string
  latest_signal_id: string | null

  topology_snapshot_id: string | null

  affected_entity_id: string | null
  affected_object_kind: string | null
  affected_object_name: string | null

  first_observed_at: string
  last_observed_at: string

  latest_analysis_id: string | null
  top_hypothesis_title: string | null
  top_hypothesis_score: number | null

  recommendation_count: number
  latest_recommendation_id: string | null

  recovery_status: string | null
  latest_recovery_verification_id: string | null

  occurrence_count: number

  created_at: string
  updated_at: string

  status_note: string | null
}

export type IncidentStatusUpdate = {
  status: IncidentStatus
  note?: string | null
}

export type IncidentRelatedSignals = {
  incident_id: string
  fingerprint: string

  signal_count: number

  signals: SignalSummary[]
}

export type BlastRadiusEntity = {
  risk_score: number;
  entity_id: string;
  entity_kind: string;
  entity_name: string;
  namespace: string | null;
  distance: number;
  impact: string;
  impact_score: number;
  relationship: string | null;
};

export type DependencyPath = {
  path: string[];
};

export type BlastRadiusResponse = {
  incident_id: string;
  root_entity_id: string;
  root_entity_name: string;
  affected_entity_count: number;
  direct_impact_count: number;
  indirect_impact_count: number;
  potential_impact_count: number;
  affected_entities: BlastRadiusEntity[];
  dependency_paths: DependencyPath[];
};

export type PlannedChangeType =
  | "container_image_update"
  | "configuration_change"
  | "resource_limit_change"
  | "replica_change"
  | "network_policy_change"
  | "service_routing_change"
  | "secret_or_certificate_change"
  | "database_schema_change"
  | "other"

export type ChangeRiskLevel =
  | "low"
  | "medium"
  | "high"
  | "critical"

export type DeploymentDecision =
  | "allow"
  | "review_required"
  | "approval_required"
  | "block_until_mitigated"

export type PreDeploymentImpactRequest = {
  snapshot_id: string
  entity_id: string
  change_type: PlannedChangeType
  change_summary: string
  max_depth: number
  metadata?: Record<string, unknown>
}

export type PreDeploymentAffectedEntity = {
  entity_id: string
  entity_kind: string
  entity_name: string
  namespace: string | null

  distance: number
  impact: string
  impact_score: number

  relationship: string | null

  risk_score: number
  risk_reasons: string[]
}

export type PreDeploymentDependencyPath = {
  path: string[]
}

export type PreDeploymentImpactResponse = {
  analysis_id: string
  algorithm_version: string
  generated_at: string

  snapshot_id: string

  root_entity_id: string
  root_entity_kind: string
  root_entity_name: string

  change_type: PlannedChangeType
  change_summary: string

  risk_score: number
  risk_level: ChangeRiskLevel
  deployment_decision: DeploymentDecision

  recommendation: string

  affected_entity_count: number
  downstream_entity_count: number

  direct_impact_count: number
  dependent_impact_count: number
  indirect_impact_count: number
  potential_impact_count: number

  high_risk_entity_count: number

  affected_entities:
    PreDeploymentAffectedEntity[]

  dependency_paths:
    PreDeploymentDependencyPath[]

  risk_factors: string[]
  warnings: string[]
}

export type ServiceCriticality =
  | "tier_1"
  | "tier_2"
  | "tier_3"
  | "tier_4"

export type OwnershipSource =
  | "manual"
  | "imported"
  | "entity_metadata"
  | "unresolved"

export type BusinessImpactLevel =
  | "none"
  | "low"
  | "medium"
  | "high"
  | "critical"

export type EntityOwnershipResolution = {
  resolved: boolean

  entity_id: string
  entity_kind: string
  entity_name: string

  service_name: string | null

  cluster_name: string | null
  namespace: string | null

  owner_team: string | null
  owner_email: string | null
  oncall_contact: string | null

  repository_url: string | null
  business_capability: string | null

  criticality: ServiceCriticality | null

  source: OwnershipSource
  confidence: number

  matched_ownership_id: string | null
  resolution_reason: string
}

export type AffectedEntityOwnership = {
  entity_id: string
  entity_kind: string
  entity_name: string

  impact: string
  distance: number
  impact_score: number

  ownership: EntityOwnershipResolution
}

export type IncidentOwnershipImpact = {
  incident_id: string

  business_impact_level:
    BusinessImpactLevel

  affected_entity_count: number
  resolved_entity_count: number
  unresolved_entity_count: number

  affected_team_count: number
  affected_capability_count: number

  highest_criticality:
    ServiceCriticality | null

  owner_teams: string[]
  business_capabilities: string[]
  oncall_contacts: string[]
  repositories: string[]

  routing_recommendation: string

  affected_entities:
    AffectedEntityOwnership[]

  warnings: string[]
}
export type WebhookEventType =
  | "incident.created"
  | "incident.status_changed"
  | "recommendation.generated"
  | "recovery.verified"
  | "recovery.failed"
  | "recovery.inconclusive"
  | "change.risk_detected"
  | "webhook.test"

export type WebhookDeliveryStatus =
  | "succeeded"
  | "failed"

export type WebhookEndpointCreate = {
  name: string
  url: string
  event_types: WebhookEventType[]
  headers?: Record<string, string>
  signing_secret?: string | null
  active?: boolean
  timeout_seconds?: number
  max_attempts?: number
}

export type WebhookEndpointUpdate = {
  name?: string
  url?: string
  event_types?: WebhookEventType[]
  headers?: Record<string, string>
  signing_secret?: string | null
  active?: boolean
  timeout_seconds?: number
  max_attempts?: number
}

export type WebhookEndpointView = {
  webhook_id: string
  name: string
  url: string

  event_types: WebhookEventType[]

  headers: Record<string, string>

  has_signing_secret: boolean

  active: boolean
  timeout_seconds: number
  max_attempts: number

  created_at: string
  updated_at: string
}

export type WebhookDeliveryView = {
  delivery_id: string

  webhook_id: string
  webhook_name: string | null

  event_id: string
  event_type: WebhookEventType

  resource_type: string
  resource_id: string

  status: WebhookDeliveryStatus

  attempt_count: number

  response_status: number | null
  response_body: string | null

  error_message: string | null

  requested_at: string
  completed_at: string | null

  created_at: string
  updated_at: string
}