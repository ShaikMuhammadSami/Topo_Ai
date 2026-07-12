"use client"

import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  AlertCircle,
  GitPullRequestArrow,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
} from "lucide-react"

import { BlastRadiusGraph } from "@/components/app/blast-radius-graph"
import { Button } from "@/components/ui/button"
import {
  analyzePreDeploymentImpact,
  getTopologySnapshot,
  listSnapshots,
} from "@/lib/topo-api"
import type {
  BlastRadiusResponse,
  GraphSnapshot,
  PlannedChangeType,
  PreDeploymentImpactResponse,
  SnapshotSummary,
} from "@/lib/topo-types"


const changeTypes: Array<{
  value: PlannedChangeType
  label: string
}> = [
  {
    value: "container_image_update",
    label: "Container image update",
  },
  {
    value: "configuration_change",
    label: "Configuration change",
  },
  {
    value: "resource_limit_change",
    label: "Resource limit change",
  },
  {
    value: "replica_change",
    label: "Replica change",
  },
  {
    value: "network_policy_change",
    label: "Network policy change",
  },
  {
    value: "service_routing_change",
    label: "Service routing change",
  },
  {
    value:
      "secret_or_certificate_change",
    label: "Secret or certificate change",
  },
  {
    value: "database_schema_change",
    label: "Database schema change",
  },
  {
    value: "other",
    label: "Other",
  },
]


export function PreDeploymentImpactView() {
  const [snapshots, setSnapshots] =
    useState<SnapshotSummary[]>([])

  const [snapshotId, setSnapshotId] =
    useState("")

  const [snapshot, setSnapshot] =
    useState<GraphSnapshot | null>(null)

  const [entityId, setEntityId] =
    useState("")

  const [
    changeType,
    setChangeType,
  ] = useState<PlannedChangeType>(
    "container_image_update",
  )

  const [
    changeSummary,
    setChangeSummary,
  ] = useState("")

  const [maxDepth, setMaxDepth] =
    useState(5)

  const [result, setResult] =
    useState<
      PreDeploymentImpactResponse | null
    >(null)

  const [loading, setLoading] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)


  async function loadSnapshots() {
    setLoading(true)
    setError(null)

    try {
      const values =
        await listSnapshots(100)

      setSnapshots(values)

      if (!snapshotId && values[0]) {
        setSnapshotId(
          values[0].snapshot_id,
        )
      }
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  useEffect(() => {
    void loadSnapshots()
  }, [])


  useEffect(() => {
    if (!snapshotId) {
      setSnapshot(null)
      setEntityId("")
      return
    }

    let cancelled = false

    async function loadSelectedSnapshot() {
      setLoading(true)
      setError(null)

      try {
        const value =
          await getTopologySnapshot(
            snapshotId,
          )

        if (cancelled) {
          return
        }

        setSnapshot(value)

        const preferredEntity =
          value.entities.find(
            (entity) =>
              entity.kind ===
              "KubernetesDeployment",
          ) ??
          value.entities.find(
            (entity) =>
              entity.entity_type ===
              "workload",
          ) ??
          value.entities[0]

        setEntityId(
          preferredEntity?.id ?? "",
        )

        setResult(null)
      } catch (requestError) {
        if (!cancelled) {
          setError(
            errorMessage(requestError),
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadSelectedSnapshot()

    return () => {
      cancelled = true
    }
  }, [snapshotId])


  const selectableEntities =
    useMemo(() => {
      if (!snapshot) {
        return []
      }

      const preferredTypes = new Set([
        "application",
        "workload",
        "endpoint",
        "datastore",
        "network",
        "security_asset",
        "cloud_resource",
      ])

      return snapshot.entities
        .filter((entity) =>
          preferredTypes.has(
            entity.entity_type,
          ),
        )
        .sort((first, second) =>
          `${first.kind}:${first.name}`.localeCompare(
            `${second.kind}:${second.name}`,
          ),
        )
    }, [snapshot])


  async function handleAnalyze() {
    if (
      !snapshotId ||
      !entityId ||
      !changeSummary.trim()
    ) {
      setError(
        "Select a snapshot and entity, then describe the planned change.",
      )
      return
    }

    setLoading(true)
    setError(null)

    try {
      const value =
        await analyzePreDeploymentImpact(
          {
            snapshot_id: snapshotId,
            entity_id: entityId,
            change_type: changeType,
            change_summary:
              changeSummary.trim(),
            max_depth: maxDepth,
            metadata: {
              source: "topo-ui",
            },
          },
        )

      setResult(value)
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  const graphData:
    BlastRadiusResponse | null =
    result
      ? {
          incident_id:
            result.analysis_id,

          root_entity_id:
            result.root_entity_id,

          root_entity_name:
            result.root_entity_name,

          affected_entity_count:
            result
              .affected_entity_count,

          direct_impact_count:
            result
              .direct_impact_count,

          indirect_impact_count:
            result
              .dependent_impact_count +
            result
              .indirect_impact_count,

          potential_impact_count:
            result
              .potential_impact_count,

          affected_entities:
            result.affected_entities.map(
              (entity) => ({
                entity_id:
                  entity.entity_id,
                entity_kind:
                  entity.entity_kind,
                entity_name:
                  entity.entity_name,
                namespace:
                  entity.namespace,
                distance:
                  entity.distance,
                impact:
                  entity.impact,
                impact_score:
                  entity.impact_score,
                relationship:
                  entity.relationship,
                risk_score:
                  entity.risk_score,
              }),
            ),

          dependency_paths:
            result.dependency_paths,
        }
      : null


  return (
    <div className="space-y-6 p-6">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
          change intelligence
        </p>

        <h1 className="mt-2 font-heading text-3xl font-bold">
          Pre-deployment impact
        </h1>

        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Predict the dependency scope and risk
          of a planned change without modifying
          the selected environment.
        </p>
      </header>


      {error && (
        <div className="flex gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}


      <section className="rounded-md border border-border bg-card p-5">
        <div className="grid gap-4 xl:grid-cols-2">
          <label>
            <FieldLabel>
              Topology snapshot
            </FieldLabel>

            <select
              value={snapshotId}
              onChange={(event) =>
                setSnapshotId(
                  event.target.value,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs"
            >
              <option value="">
                Select snapshot
              </option>

              {snapshots.map(
                (item) => (
                  <option
                    key={item.snapshot_id}
                    value={item.snapshot_id}
                  >
                    {item.cluster_name}
                    {" / "}
                    {item.namespace ?? "*"}
                    {" — "}
                    {new Date(
                      item.collected_at,
                    ).toLocaleString()}
                  </option>
                ),
              )}
            </select>
          </label>


          <label>
            <FieldLabel>
              Planned change target
            </FieldLabel>

            <select
              value={entityId}
              onChange={(event) =>
                setEntityId(
                  event.target.value,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs"
            >
              <option value="">
                Select entity
              </option>

              {selectableEntities.map(
                (entity) => (
                  <option
                    key={entity.id}
                    value={entity.id}
                  >
                    {entity.kind}
                    {" — "}
                    {entity.name}
                  </option>
                ),
              )}
            </select>
          </label>


          <label>
            <FieldLabel>
              Change type
            </FieldLabel>

            <select
              value={changeType}
              onChange={(event) =>
                setChangeType(
                  event.target
                    .value as PlannedChangeType,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs"
            >
              {changeTypes.map(
                (item) => (
                  <option
                    key={item.value}
                    value={item.value}
                  >
                    {item.label}
                  </option>
                ),
              )}
            </select>
          </label>


          <label>
            <FieldLabel>
              Maximum graph depth
            </FieldLabel>

            <input
              type="number"
              min={1}
              max={10}
              value={maxDepth}
              onChange={(event) =>
                setMaxDepth(
                  Number(
                    event.target.value,
                  ),
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs"
            />
          </label>
        </div>


        <label className="mt-4 block">
          <FieldLabel>
            Planned change summary
          </FieldLabel>

          <textarea
            value={changeSummary}
            onChange={(event) =>
              setChangeSummary(
                event.target.value,
              )
            }
            rows={3}
            placeholder="Example: Update checkout-api image from v7 to v8."
            className="mt-2 w-full rounded-sm border border-input bg-background px-3 py-2 font-mono text-xs"
          />
        </label>


        <div className="mt-4 flex gap-3">
          <Button
            disabled={loading}
            onClick={() =>
              void handleAnalyze()
            }
          >
            {loading ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <GitPullRequestArrow />
            )}

            Analyze planned change
          </Button>

          <Button
            variant="outline"
            disabled={loading}
            onClick={() =>
              void loadSnapshots()
            }
          >
            <RefreshCw />
            Refresh snapshots
          </Button>
        </div>
      </section>


      {result && (
        <>
          <section className="rounded-md border border-border bg-card p-5">
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div>
                <span className="rounded-sm border border-current px-2 py-1 font-mono text-xs uppercase">
                  {result.risk_level}
                </span>

                <h2 className="mt-4 font-heading text-2xl font-bold">
                  {
                    result
                      .deployment_decision
                  }
                </h2>

                <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                  {result.recommendation}
                </p>
              </div>

              <div className="text-right">
                <p className="font-heading text-5xl font-black">
                  {Math.round(
                    result.risk_score *
                      100,
                  )}
                  %
                </p>

                <p className="font-mono text-xs text-muted-foreground">
                  predicted risk
                </p>
              </div>
            </div>
          </section>


          <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-4">
            <Metric
              label="AFFECTED"
              value={
                result
                  .affected_entity_count
              }
            />

            <Metric
              label="DOWNSTREAM"
              value={
                result
                  .downstream_entity_count
              }
            />

            <Metric
              label="HIGH RISK"
              value={
                result
                  .high_risk_entity_count
              }
            />

            <Metric
              label="MAX DEPTH"
              value={maxDepth}
            />
          </section>


          <BlastRadiusGraph
            data={graphData}
          />


          <section className="overflow-hidden rounded-md border border-border bg-card">
            <header className="border-b border-border px-5 py-4">
              <h2 className="font-heading text-lg font-bold">
                Predicted affected entities
              </h2>
            </header>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border font-mono text-muted-foreground">
                  <tr>
                    <th className="p-3">
                      Entity
                    </th>
                    <th className="p-3">
                      Kind
                    </th>
                    <th className="p-3">
                      Impact
                    </th>
                    <th className="p-3">
                      Relationship
                    </th>
                    <th className="p-3">
                      Risk
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {result
                    .affected_entities
                    .map((entity) => (
                      <tr
                        key={
                          entity.entity_id
                        }
                        className="border-b border-border last:border-0"
                      >
                        <td className="p-3 font-semibold">
                          {
                            entity
                              .entity_name
                          }
                        </td>

                        <td className="p-3 font-mono">
                          {
                            entity
                              .entity_kind
                          }
                        </td>

                        <td className="p-3">
                          {entity.impact}
                        </td>

                        <td className="p-3 font-mono">
                          {entity.relationship ??
                            "root"}
                        </td>

                        <td className="p-3">
                          {Math.round(
                            entity.risk_score *
                              100,
                          )}
                          %
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>


          {result.warnings.length >
            0 && (
            <section className="rounded-md border border-warn/40 bg-warn/10 p-5">
              <div className="flex items-center gap-2 text-warn">
                <ShieldAlert className="h-5 w-5" />

                <h2 className="font-heading font-bold">
                  Analysis warnings
                </h2>
              </div>

              <ul className="mt-3 space-y-2 font-mono text-xs">
                {result.warnings.map(
                  (warning) => (
                    <li key={warning}>
                      • {warning}
                    </li>
                  ),
                )}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  )
}


function FieldLabel({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
      {children}
    </span>
  )
}


function Metric({
  label,
  value,
}: {
  label: string
  value: string | number
}) {
  return (
    <div className="bg-card p-4 text-center">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>

      <p className="mt-1 font-heading text-2xl font-bold">
        {value}
      </p>
    </div>
  )
}


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : "An unexpected request error occurred."
}