import type {
  ChangeCategory,
  ChangeImportance,
  ChangeSummary,
  GraphSnapshot,
  IdentityOverrideCreate,
  IdentityOverrideDeleteResult,
  IdentityOverrideView,
  IdentityResolutionResult,
  IdentityResolutionSummary,
  IncidentAnalysis,
  IncidentAnalysisSummary,
  NormalizedChange,
  NormalizedSignal,
  RecommendationStatus,
  RecommendationStatusUpdate,
  RecommendationSummary,
  RecoveryStatus,
  RecoveryVerification,
  RecoveryVerificationSummary,
  RemediationRecommendation,
  SignalSeverity,
  SignalSummary,
  SnapshotDiffResult,
  SnapshotSummary,
  IncidentRecordSummary,
  IncidentRecordView,
  IncidentRelatedSignals,
  IncidentSeverity,
  IncidentStatus,
  IncidentStatusUpdate,
  BlastRadiusResponse,
  PreDeploymentImpactRequest,
  PreDeploymentImpactResponse,
  IncidentOwnershipImpact
} from "@/lib/topo-types"

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_TOPO_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "")

async function apiRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(
    `${API_BASE_URL}${path}`,
    {
      ...options,
      headers: {
        Accept: "application/json",
        ...options?.headers,
      },
      cache: "no-store",
    },
  )

if (!response.ok) {
  let message =
    `${response.status} ${response.statusText}`

  try {
    const payload: unknown =
      await response.json()

    if (
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload
    ) {
      const detail = (
        payload as {
          detail: unknown
        }
      ).detail

      message =
        typeof detail === "string"
          ? detail
          : JSON.stringify(
              detail,
              null,
              2,
            )
    }
  } catch {
    // Keep the default HTTP message.
  }

  throw new Error(message)
}

  return await response.json() as T
}

export function listSnapshots(
  limit = 20,
): Promise<SnapshotSummary[]> {
  return apiRequest<SnapshotSummary[]>(
    `/api/v1/snapshots?limit=${limit}`,
  )
}

export function getSnapshot(
  snapshotId: string,
): Promise<GraphSnapshot> {
  return apiRequest<GraphSnapshot>(
    `/api/v1/snapshots/${encodeURIComponent(snapshotId)}`,
  )
}

export function captureSnapshot(
  namespace?: string,
): Promise<SnapshotSummary> {
  const query = namespace
    ? `?namespace=${encodeURIComponent(namespace)}`
    : ""

  return apiRequest<SnapshotSummary>(
    `/api/v1/snapshots/capture${query}`,
    {
      method: "POST",
    },
  )
}
export function getSnapshotDiff(
  fromSnapshotId: string,
  toSnapshotId: string,
): Promise<SnapshotDiffResult> {
  const query = new URLSearchParams({
    from_snapshot_id: fromSnapshotId,
    to_snapshot_id: toSnapshotId,
  })

  return apiRequest<SnapshotDiffResult>(
    `/api/v1/snapshots/diff?${query.toString()}`,
  )
}

export function materializeIdentities(
  snapshotId: string,
): Promise<IdentityResolutionSummary> {
  const query = new URLSearchParams({
    snapshot_id: snapshotId,
  })

  return apiRequest<IdentityResolutionSummary>(
    `/api/v1/identities/materialize?${query.toString()}`,
    {
      method: "POST",
    },
  )
}

export function getStoredIdentities(
  snapshotId: string,
): Promise<IdentityResolutionResult> {
  const query = new URLSearchParams({
    snapshot_id: snapshotId,
  })

  return apiRequest<IdentityResolutionResult>(
    `/api/v1/identities/stored?${query.toString()}`,
  )
}

export function listIdentityOverrides(
  options?: {
    clusterName?: string
    namespace?: string
    activeOnly?: boolean
  },
): Promise<IdentityOverrideView[]> {
  const query = new URLSearchParams()

  if (options?.clusterName) {
    query.set(
      "cluster_name",
      options.clusterName,
    )
  }

  if (options?.namespace) {
    query.set(
      "namespace",
      options.namespace,
    )
  }

  query.set(
    "active_only",
    String(options?.activeOnly ?? true),
  )

  return apiRequest<IdentityOverrideView[]>(
    `/api/v1/identities/overrides?${query.toString()}`,
  )
}

export function createIdentityOverride(
  request: IdentityOverrideCreate,
): Promise<IdentityOverrideView> {
  return apiRequest<IdentityOverrideView>(
    "/api/v1/identities/overrides",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    },
  )
}

export function deactivateIdentityOverride(
  overrideId: string,
): Promise<IdentityOverrideDeleteResult> {
  return apiRequest<IdentityOverrideDeleteResult>(
    `/api/v1/identities/overrides/${encodeURIComponent(
      overrideId,
    )}`,
    {
      method: "DELETE",
    },
  )
}

export function listSignals(
  options?: {
    clusterName?: string
    namespace?: string
    severity?: SignalSeverity
    limit?: number
  },
): Promise<SignalSummary[]> {
  const query = new URLSearchParams()

  if (options?.clusterName) {
    query.set(
      "cluster_name",
      options.clusterName,
    )
  }

  if (options?.namespace) {
    query.set(
      "namespace",
      options.namespace,
    )
  }

  if (options?.severity) {
    query.set(
      "severity",
      options.severity,
    )
  }

  query.set(
    "limit",
    String(options?.limit ?? 200),
  )

  return apiRequest<SignalSummary[]>(
    `/api/v1/signals?${query.toString()}`,
  )
}

export function getSignal(
  signalId: string,
): Promise<NormalizedSignal> {
  return apiRequest<NormalizedSignal>(
    `/api/v1/signals/${encodeURIComponent(
      signalId,
    )}`,
  )
}

export function listChanges(
  options?: {
    clusterName?: string
    namespace?: string
    category?: ChangeCategory
    importance?: ChangeImportance
    limit?: number
  },
): Promise<ChangeSummary[]> {
  const query = new URLSearchParams()

  if (options?.clusterName) {
    query.set(
      "cluster_name",
      options.clusterName,
    )
  }

  if (options?.namespace) {
    query.set(
      "namespace",
      options.namespace,
    )
  }

  if (options?.category) {
    query.set(
      "category",
      options.category,
    )
  }

  if (options?.importance) {
    query.set(
      "importance",
      options.importance,
    )
  }

  query.set(
    "limit",
    String(options?.limit ?? 300),
  )

  return apiRequest<ChangeSummary[]>(
    `/api/v1/changes?${query.toString()}`,
  )
}

export function getChange(
  changeId: string,
): Promise<NormalizedChange> {
  return apiRequest<NormalizedChange>(
    `/api/v1/changes/${encodeURIComponent(
      changeId,
    )}`,
  )
}

export function analyzeIncident(
  signalId: string,
  options?: {
    lookbackMinutes?: number
    graceMinutes?: number
    maxGraphHops?: number
    maxHypotheses?: number
  },
): Promise<IncidentAnalysis> {
  const query = new URLSearchParams({
    signal_id: signalId,
    lookback_minutes: String(
      options?.lookbackMinutes ?? 60,
    ),
    grace_minutes: String(
      options?.graceMinutes ?? 2,
    ),
    max_graph_hops: String(
      options?.maxGraphHops ?? 6,
    ),
    max_hypotheses: String(
      options?.maxHypotheses ?? 10,
    ),
  })

  return apiRequest<IncidentAnalysis>(
    `/api/v1/incidents/analyze?${query.toString()}`,
    {
      method: "POST",
    },
  )
}

export function listIncidentAnalyses(
  options?: {
    signalId?: string
    limit?: number
  },
): Promise<IncidentAnalysisSummary[]> {
  const query = new URLSearchParams()

  if (options?.signalId) {
    query.set(
      "signal_id",
      options.signalId,
    )
  }

  query.set(
    "limit",
    String(options?.limit ?? 100),
  )

  return apiRequest<IncidentAnalysisSummary[]>(
    `/api/v1/incidents?${query.toString()}`,
  )
}

export function getIncidentAnalysis(
  analysisId: string,
): Promise<IncidentAnalysis> {
  return apiRequest<IncidentAnalysis>(
    `/api/v1/incidents/${encodeURIComponent(
      analysisId,
    )}`,
  )
}

export function generateRecommendations(
  analysisId: string,
  options?: {
    minimumScore?: number
    maxRecommendations?: number
  },
): Promise<RemediationRecommendation[]> {
  const query = new URLSearchParams({
    analysis_id: analysisId,
    minimum_score: String(
      options?.minimumScore ?? 0.5,
    ),
    max_recommendations: String(
      options?.maxRecommendations ?? 3,
    ),
  })

  return apiRequest<
    RemediationRecommendation[]
  >(
    `/api/v1/recommendations/generate?${query.toString()}`,
    {
      method: "POST",
    },
  )
}

export function listRecommendations(
  options?: {
    analysisId?: string
    signalId?: string
    status?: RecommendationStatus
    limit?: number
  },
): Promise<RecommendationSummary[]> {
  const query = new URLSearchParams()

  if (options?.analysisId) {
    query.set(
      "analysis_id",
      options.analysisId,
    )
  }

  if (options?.signalId) {
    query.set(
      "signal_id",
      options.signalId,
    )
  }

  if (options?.status) {
    query.set(
      "status",
      options.status,
    )
  }

  query.set(
    "limit",
    String(options?.limit ?? 100),
  )

  return apiRequest<
    RecommendationSummary[]
  >(
    `/api/v1/recommendations?${query.toString()}`,
  )
}

export function getRecommendation(
  recommendationId: string,
): Promise<RemediationRecommendation> {
  return apiRequest<
    RemediationRecommendation
  >(
    `/api/v1/recommendations/${encodeURIComponent(
      recommendationId,
    )}`,
  )
}

export function updateRecommendationStatus(
  recommendationId: string,
  request: RecommendationStatusUpdate,
): Promise<RemediationRecommendation> {
  return apiRequest<
    RemediationRecommendation
  >(
    `/api/v1/recommendations/${encodeURIComponent(
      recommendationId,
    )}/status`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    },
  )
}

export function verifyRecovery(
  recommendationId: string,
  postSnapshotId: string,
): Promise<RecoveryVerification> {
  const query = new URLSearchParams({
    recommendation_id: recommendationId,
    post_snapshot_id: postSnapshotId,
  })

  return apiRequest<RecoveryVerification>(
    `/api/v1/recovery/verify?${query.toString()}`,
    {
      method: "POST",
    },
  )
}

export function listRecoveryVerifications(
  options?: {
    recommendationId?: string
    status?: RecoveryStatus
    limit?: number
  },
): Promise<RecoveryVerificationSummary[]> {
  const query = new URLSearchParams()

  if (options?.recommendationId) {
    query.set(
      "recommendation_id",
      options.recommendationId,
    )
  }

  if (options?.status) {
    query.set(
      "status",
      options.status,
    )
  }

  query.set(
    "limit",
    String(options?.limit ?? 100),
  )

  return apiRequest<
    RecoveryVerificationSummary[]
  >(
    `/api/v1/recovery?${query.toString()}`,
  )
}

export function getRecoveryVerification(
  verificationId: string,
): Promise<RecoveryVerification> {
  return apiRequest<RecoveryVerification>(
    `/api/v1/recovery/${encodeURIComponent(
      verificationId,
    )}`,
  )
}

export function listIncidentRecords(
  options?: {
    status?: IncidentStatus
    severity?: IncidentSeverity
    namespace?: string
    limit?: number
  },
): Promise<IncidentRecordSummary[]> {
  const query = new URLSearchParams()

  if (options?.status) {
    query.set("status", options.status)
  }

  if (options?.severity) {
    query.set("severity", options.severity)
  }

  if (options?.namespace) {
    query.set("namespace", options.namespace)
  }

  query.set("limit", String(options?.limit ?? 100))

  return apiRequest<IncidentRecordSummary[]>(
    `/api/v1/incident-records?${query.toString()}`,
  )
}

export function getIncidentRecord(
  incidentId: string,
): Promise<IncidentRecordView> {
  return apiRequest<IncidentRecordView>(
    `/api/v1/incident-records/${encodeURIComponent(
      incidentId,
    )}`,
  )
}

export function updateIncidentRecordStatus(
  incidentId: string,
  request: IncidentStatusUpdate,
): Promise<IncidentRecordView> {
  return apiRequest<IncidentRecordView>(
    `/api/v1/incident-records/${encodeURIComponent(
      incidentId,
    )}/status`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    },
  )
}

export function getIncidentRelatedSignals(
  incidentId: string,
  options?: {
    limit?: number
  },
): Promise<IncidentRelatedSignals> {
  const query = new URLSearchParams({
    limit: String(options?.limit ?? 200),
  })

  return apiRequest<IncidentRelatedSignals>(
    `/api/v1/incident-records/${encodeURIComponent(
      incidentId,
    )}/signals?${query.toString()}`,
  )
}

export function getBlastRadius(
  incidentId: string
): Promise<BlastRadiusResponse> {
  return apiRequest<BlastRadiusResponse>(
    `/api/v1/incidents/${encodeURIComponent(incidentId)}/blast-radius`
  );
}

export function getTopologySnapshot(
  snapshotId: string,
): Promise<GraphSnapshot> {
  return apiRequest<GraphSnapshot>(
    `/api/v1/snapshots/${encodeURIComponent(
      snapshotId,
    )}`,
  )
}


export function analyzePreDeploymentImpact(
  request: PreDeploymentImpactRequest,
): Promise<PreDeploymentImpactResponse> {
  return apiRequest<
    PreDeploymentImpactResponse
  >(
    "/api/v1/predeployment/analyze",
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify(request),
    },
  )
}

export function getIncidentOwnershipImpact(
  incidentId: string,
): Promise<IncidentOwnershipImpact> {
  return apiRequest<
    IncidentOwnershipImpact
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/ownership-impact`,
  )
}