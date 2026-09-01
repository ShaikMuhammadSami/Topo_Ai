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
  IncidentOwnershipImpact,
  WebhookDeliveryStatus,
  WebhookDeliveryView,
  WebhookEventType,
  WebhookEndpointCreate,
  WebhookEndpointUpdate,
  WebhookEndpointView,
  NetworkDependencyAnalysisResponse,
  ExplanationProvider,
  IncidentExplanationResponse,
  CopilotQuestionResponse,
  CopilotSessionDetail,
  CopilotSessionSummary,
  InvestigationPlanDetail,
  InvestigationPlanSummary,
  InvestigationStepStatus,
  PostIncidentReportDetail,
  PostIncidentReportStatus,
  PostIncidentReportSummary,
  ReportActionStatus,
  IncidentBriefing,
  IncidentLifecycleStatus,
} from "@/lib/topo-types"


export type BrowserSession = {
  subject: string
  display_name: string
  roles: string[]
  authentication_type: "session" | "development"
  absolute_expires_at: string | null
}

export type ApiFailureKind =
  | "unauthenticated"
  | "tenant-access-denied"
  | "forbidden"
  | "backend-unavailable"
  | "http"

export type AuthTransportEvent =
  | { kind: "unauthenticated" }
  | { kind: "forbidden" }
  | { kind: "backend-unavailable" }

type AuthTransportListener = (
  event: AuthTransportEvent,
) => void

const authTransportListeners =
  new Set<AuthTransportListener>()

export type TenantView = {
  tenant_id: string
  display_name: string
}

// Non-secret selection only. The server proves membership on every request.
let selectedTenantId: string | null = null
const tenantDeniedListeners = new Set<(tenantId: string | null) => void>()

export function selectApiTenant(tenantId: string | null): void {
  selectedTenantId = tenantId
}

export function subscribeTenantDenied(listener: (tenantId: string | null) => void): () => void {
  tenantDeniedListeners.add(listener)
  return () => { tenantDeniedListeners.delete(listener) }
}

export function listTenants(): Promise<TenantView[]> {
  return apiRequest<TenantView[]>("/api/v1/tenants")
}

export class TopoApiError extends Error {
  readonly status: number | null
  readonly kind: ApiFailureKind

  constructor(
    message: string,
    options: {
      status: number | null
      kind: ApiFailureKind
    },
  ) {
    super(message)
    this.name = "TopoApiError"
    this.status = options.status
    this.kind = options.kind
  }
}

export function subscribeAuthTransport(
  listener: AuthTransportListener,
): () => void {
  authTransportListeners.add(listener)
  return () => {
    authTransportListeners.delete(listener)
  }
}

function publishAuthTransport(
  event: AuthTransportEvent,
) {
  for (const listener of authTransportListeners) {
    listener(event)
  }
}

export function csrfCookieValue(
  cookieHeader?: string,
): string | null {
  const source = cookieHeader ?? (
    typeof document === "undefined"
      ? ""
      : document.cookie
  )
  for (const item of source.split(";")) {
    const [name, ...valueParts] = item.trim().split("=")
    if (name === "topo_csrf") {
      const value = valueParts.join("=")
      return value ? decodeURIComponent(value) : null
    }
  }
  return null
}

function isUnsafeMethod(method?: string): boolean {
  return ["POST", "PUT", "PATCH", "DELETE"].includes(
    (method ?? "GET").toUpperCase(),
  )
}

function requireCurrentTenant(path: string, requestTenant: string | null): void {
  if (!path.startsWith("/api/v1/auth/") && requestTenant !== selectedTenantId) {
    throw new TopoApiError("Tenant selection changed; reload this request.", { status: null, kind: "http" })
  }
}

async function apiResponse(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  if (!path.startsWith("/api/")) {
    throw new TopoApiError(
      "Topo API requests must use the same-origin API boundary.",
      { status: null, kind: "http" },
    )
  }

  const headers = new Headers(options?.headers)
  const requestTenant = selectedTenantId
  // Call-site headers cannot override the active workspace boundary.
  headers.delete("X-Topo-Tenant-ID")
  if (requestTenant && !path.startsWith("/api/v1/auth/")) {
    headers.set("X-Topo-Tenant-ID", requestTenant)
  }
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json")
  }
  if (isUnsafeMethod(options?.method)) {
    const csrf = csrfCookieValue()
    if (csrf) {
      headers.set("X-Topo-CSRF", csrf)
    }
  }

  let response: Response
  try {
    response = await fetch(path, {
      ...options,
      headers,
      cache: "no-store",
      credentials: "same-origin",
    })
  } catch {
    publishAuthTransport({ kind: "backend-unavailable" })
    throw new TopoApiError(
      "Topo backend is unavailable.",
      { status: null, kind: "backend-unavailable" },
    )
  }

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

    const kind: ApiFailureKind =
      response.status === 401
        ? "unauthenticated"
        : response.status === 403 && message === "TENANT_ACCESS_DENIED"
          ? "tenant-access-denied"
        : response.status === 403
          ? "forbidden"
          : "http"
    if (kind === "unauthenticated" || kind === "forbidden") {
      if (kind === "unauthenticated") selectApiTenant(null)
      publishAuthTransport({ kind })
    }
    if (kind === "tenant-access-denied") {
      for (const listener of tenantDeniedListeners) listener(requestTenant)
    }
    throw new TopoApiError(message, {
      status: response.status,
      kind,
    })
  }

  requireCurrentTenant(path, requestTenant)
  return response
}

export async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const requestTenant = selectedTenantId
  const response = await apiResponse(path, options)
  if (response.status === 204) {
    return undefined as T
  }
  const value = await response.json() as T
  requireCurrentTenant(path, requestTenant)
  return value
}

export async function downloadApiFile(path: string, filename: string): Promise<void> {
  const requestTenant = selectedTenantId
  const response = await apiResponse(path)
  const blob = await response.blob()
  requireCurrentTenant(path, requestTenant)
  const url = URL.createObjectURL(blob)
  try {
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    link.click()
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function getBrowserSession(): Promise<BrowserSession> {
  return apiRequest<BrowserSession>("/api/v1/auth/session")
}

export function createBrowserSession(
  credential: string,
): Promise<BrowserSession> {
  return apiRequest<BrowserSession>("/api/v1/auth/session", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${credential}`,
    },
  })
}

export function deleteBrowserSession(): Promise<void> {
  return apiRequest<void>("/api/v1/auth/session", {
    method: "DELETE",
  })
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

export function getIncidentBriefing(
  incidentId: string,
  options?: {
    includeAi?: boolean
    signal?: AbortSignal
  },
): Promise<IncidentBriefing> {
  const query = new URLSearchParams({
    include_ai: String(
      options?.includeAi ?? false,
    ),
  })

  return apiRequest<IncidentBriefing>(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/briefing?${query.toString()}`,
    {
      signal: options?.signal,
    },
  )
}

export function getIncidentLifecycleStatus(
  incidentId: string,
  options?: { signal?: AbortSignal },
): Promise<IncidentLifecycleStatus> {
  return apiRequest<IncidentLifecycleStatus>(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/lifecycle-status`,
    { signal: options?.signal },
  )
}
export function createWebhookEndpoint(
  request: WebhookEndpointCreate,
): Promise<WebhookEndpointView> {
  return apiRequest<WebhookEndpointView>(
    "/api/v1/integrations/webhooks",
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


export function listWebhookEndpoints(
  active?: boolean,
): Promise<WebhookEndpointView[]> {
  const query = new URLSearchParams()

  if (active !== undefined) {
    query.set(
      "active",
      String(active),
    )
  }

  const suffix = query.toString()
    ? `?${query.toString()}`
    : ""

  return apiRequest<
    WebhookEndpointView[]
  >(
    `/api/v1/integrations/webhooks${suffix}`,
  )
}


export function updateWebhookEndpoint(
  webhookId: string,
  request: WebhookEndpointUpdate,
): Promise<WebhookEndpointView> {
  return apiRequest<WebhookEndpointView>(
    `/api/v1/integrations/webhooks/${encodeURIComponent(
      webhookId,
    )}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type":
          "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(request),
    },
  )
}


export function testWebhookEndpoint(
  webhookId: string,
): Promise<WebhookDeliveryView> {
  return apiRequest<WebhookDeliveryView>(
    `/api/v1/integrations/webhooks/${encodeURIComponent(
      webhookId,
    )}/test`,
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify({
        summary:
          "Test delivery from Topo AI.",
      }),
    },
  )
}


export function listWebhookDeliveries(
  options?: {
    webhookId?: string
    status?: WebhookDeliveryStatus
    eventType?: WebhookEventType
    limit?: number
  },
): Promise<WebhookDeliveryView[]> {
  const query = new URLSearchParams()

  if (options?.webhookId) {
    query.set(
      "webhook_id",
      options.webhookId,
    )
  }

  if (options?.status) {
    query.set(
      "status",
      options.status,
    )
  }

  if (options?.eventType) {
    query.set(
      "event_type",
      options.eventType,
    )
  }

  query.set(
    "limit",
    String(options?.limit ?? 200),
  )

  return apiRequest<
    WebhookDeliveryView[]
  >(
    `/api/v1/integrations/deliveries?${query.toString()}`,
  )
}

export function getNetworkDependencies(
  snapshotId: string,
  maxDepth = 5,
): Promise<
  NetworkDependencyAnalysisResponse
> {
  const query = new URLSearchParams({
    max_depth: String(maxDepth),
  })

  return apiRequest<
    NetworkDependencyAnalysisResponse
  >(
    `/api/v1/snapshots/${encodeURIComponent(
      snapshotId,
    )}/network-dependencies?${query.toString()}`,
  )
}

export function getLatestIncidentExplanation(
  incidentId: string,
): Promise<
  IncidentExplanationResponse | null
> {
  return apiRequest<
    IncidentExplanationResponse | null
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/explanations/latest`,
  )
}


export function generateIncidentExplanation(
  incidentId: string,
  options?: {
    provider?: ExplanationProvider
    forceRegenerate?: boolean
  },
): Promise<IncidentExplanationResponse> {
  return apiRequest<
    IncidentExplanationResponse
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/explanations`,
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify({
        provider:
          options?.provider ?? "auto",
        force_regenerate:
          options?.forceRegenerate
          ?? false,
      }),
    },
  )
}

export function createIncidentCopilotSession(
  incidentId: string,
  options?: {
    title?: string
    provider?: ExplanationProvider
  },
): Promise<CopilotSessionDetail> {
  return apiRequest<
    CopilotSessionDetail
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/copilot/sessions`,
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify({
        title:
          options?.title ?? null,
        provider:
          options?.provider ?? "auto",
      }),
    },
  )
}


export function listIncidentCopilotSessions(
  incidentId: string,
): Promise<CopilotSessionSummary[]> {
  return apiRequest<
    CopilotSessionSummary[]
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/copilot/sessions`,
  )
}


export function getIncidentCopilotSession(
  incidentId: string,
  sessionId: string,
): Promise<CopilotSessionDetail> {
  return apiRequest<
    CopilotSessionDetail
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/copilot/sessions/${encodeURIComponent(
      sessionId,
    )}`,
  )
}


export function sendIncidentCopilotMessage(
  incidentId: string,
  sessionId: string,
  question: string,
): Promise<CopilotQuestionResponse> {
  return apiRequest<
    CopilotQuestionResponse
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/copilot/sessions/${encodeURIComponent(
      sessionId,
    )}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify({
        question,
      }),
    },
  )
}

export function generateInvestigationPlan(
  incidentId: string,
  options?: {
    provider?: ExplanationProvider
    forceRegenerate?: boolean
  },
): Promise<InvestigationPlanDetail> {
  return apiRequest<
    InvestigationPlanDetail
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/investigation-plans`,
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify({
        provider:
          options?.provider ?? "auto",
        force_regenerate:
          options?.forceRegenerate
          ?? false,
      }),
    },
  )
}


export function listInvestigationPlans(
  incidentId: string,
): Promise<InvestigationPlanSummary[]> {
  return apiRequest<
    InvestigationPlanSummary[]
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/investigation-plans`,
  )
}


export function getInvestigationPlan(
  incidentId: string,
  planId: string,
): Promise<InvestigationPlanDetail> {
  return apiRequest<
    InvestigationPlanDetail
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/investigation-plans/${encodeURIComponent(
      planId,
    )}`,
  )
}


export function updateInvestigationStep(
  incidentId: string,
  planId: string,
  stepId: string,
  request: {
    status?: InvestigationStepStatus
    finding?: string | null
    responder_notes?: string | null
  },
): Promise<InvestigationPlanDetail> {
  return apiRequest<
    InvestigationPlanDetail
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/investigation-plans/${encodeURIComponent(
      planId,
    )}/steps/${encodeURIComponent(
      stepId,
    )}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify(request),
    },
  )
}

export function generatePostIncidentReport(
  incidentId: string,
  options?: {
    provider?: ExplanationProvider
    forceRegenerate?: boolean
  },
): Promise<PostIncidentReportDetail> {
  return apiRequest<
    PostIncidentReportDetail
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/reports`,
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify({
        provider:
          options?.provider ?? "auto",
        force_regenerate:
          options?.forceRegenerate
          ?? false,
      }),
    },
  )
}


export function listPostIncidentReports(
  incidentId: string,
): Promise<PostIncidentReportSummary[]> {
  return apiRequest<
    PostIncidentReportSummary[]
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/reports`,
  )
}


export function getPostIncidentReport(
  incidentId: string,
  reportId: string,
): Promise<PostIncidentReportDetail> {
  return apiRequest<
    PostIncidentReportDetail
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/reports/${encodeURIComponent(
      reportId,
    )}`,
  )
}


export function updatePostIncidentReport(
  incidentId: string,
  reportId: string,
  request: {
    status?: PostIncidentReportStatus
    reviewer_name?: string | null
    review_notes?: string | null
  },
): Promise<PostIncidentReportDetail> {
  return apiRequest<
    PostIncidentReportDetail
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/reports/${encodeURIComponent(
      reportId,
    )}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify(request),
    },
  )
}


export function updateReportActionItem(
  incidentId: string,
  reportId: string,
  actionItemId: string,
  request: {
    status?: ReportActionStatus
    owner_team?: string | null
    owner_contact?: string | null
    due_date?: string | null
    notes?: string | null
  },
): Promise<PostIncidentReportDetail> {
  return apiRequest<
    PostIncidentReportDetail
  >(
    `/api/v1/incidents/${encodeURIComponent(
      incidentId,
    )}/reports/${encodeURIComponent(
      reportId,
    )}/actions/${encodeURIComponent(
      actionItemId,
    )}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type":
          "application/json",
      },
      body: JSON.stringify(request),
    },
  )
}
