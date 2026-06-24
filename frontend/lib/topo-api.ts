import type {
  GraphSnapshot,
  IdentityOverrideCreate,
  IdentityOverrideDeleteResult,
  IdentityOverrideView,
  IdentityResolutionResult,
  IdentityResolutionSummary,
  SnapshotDiffResult,
  SnapshotSummary,
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
      `API request failed with status ${response.status}`

    try {
      const errorBody = await response.json() as {
        detail?: unknown
      }

      if (errorBody.detail) {
        message = String(errorBody.detail)
      }
    } catch {
      // Use the original HTTP message.
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