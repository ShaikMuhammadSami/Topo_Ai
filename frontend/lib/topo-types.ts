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