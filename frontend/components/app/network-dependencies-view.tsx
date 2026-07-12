"use client"

import {
  useEffect,
  useState,
} from "react"
import {
  AlertCircle,
  LoaderCircle,
  Network,
  RefreshCw,
} from "lucide-react"

import {
  NetworkDependencyGraph,
} from "@/components/app/network-dependency-graph"
import {
  Button,
} from "@/components/ui/button"
import {
  getNetworkDependencies,
  listSnapshots,
} from "@/lib/topo-api"
import type {
  NetworkDependencyAnalysisResponse,
  SnapshotSummary,
} from "@/lib/topo-types"


export function NetworkDependenciesView() {
  const [snapshots, setSnapshots] =
    useState<SnapshotSummary[]>([])

  const [snapshotId, setSnapshotId] =
    useState("")

  const [analysis, setAnalysis] =
    useState<
      NetworkDependencyAnalysisResponse
      | null
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


  async function loadAnalysis(
    selectedSnapshotId: string,
  ) {
    if (!selectedSnapshotId) {
      setAnalysis(null)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const value =
        await getNetworkDependencies(
          selectedSnapshotId,
          5,
        )

      setAnalysis(value)
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
    if (snapshotId) {
      void loadAnalysis(snapshotId)
    }
  }, [snapshotId])


  return (
    <div className="space-y-6 p-6">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
          topology intelligence
        </p>

        <h1 className="mt-2 font-heading text-3xl font-bold">
          Network dependencies
        </h1>

        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Discover ingress, service,
          EndpointSlice, Pod and external
          application dependency paths.
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
        <div className="flex flex-wrap items-end gap-4">
          <label className="min-w-[320px] flex-1">
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Topology snapshot
            </span>

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
                (snapshot) => (
                  <option
                    key={
                      snapshot
                        .snapshot_id
                    }
                    value={
                      snapshot
                        .snapshot_id
                    }
                  >
                    {
                      snapshot
                        .cluster_name
                    }
                    {" / "}
                    {snapshot.namespace ??
                      "*"}
                    {" — "}
                    {new Date(
                      snapshot.collected_at,
                    ).toLocaleString()}
                  </option>
                ),
              )}
            </select>
          </label>

          <Button
            variant="outline"
            disabled={loading}
            onClick={() =>
              void loadAnalysis(
                snapshotId,
              )
            }
          >
            <RefreshCw
              className={
                loading
                  ? "animate-spin"
                  : ""
              }
            />

            Refresh
          </Button>
        </div>
      </section>


      {loading && !analysis && (
        <section className="rounded-md border border-border bg-card p-5">
          <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
            <LoaderCircle className="h-4 w-4 animate-spin" />
            Analyzing network topology…
          </div>
        </section>
      )}


      {analysis && (
        <>
          <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-4">
            <Metric
              label="ENTITIES"
              value={
                analysis.entity_count
              }
            />

            <Metric
              label="RELATIONSHIPS"
              value={
                analysis
                  .relationship_count
              }
            />

            <Metric
              label="PATHS"
              value={
                analysis.path_count
              }
            />

            <Metric
              label="ISSUES"
              value={
                analysis.issue_count
              }
            />
          </section>


          <section className="rounded-md border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-2">
              <Network className="h-5 w-5 text-info" />

              <h2 className="font-heading text-lg font-bold">
                Dependency graph
              </h2>
            </div>

            <NetworkDependencyGraph
              data={analysis}
            />
          </section>


          <section className="overflow-hidden rounded-md border border-border bg-card">
            <header className="border-b border-border px-5 py-4">
              <h2 className="font-heading text-lg font-bold">
                Network issues
              </h2>
            </header>

            {analysis.issues.length ===
            0 ? (
              <p className="p-5 font-mono text-xs text-muted-foreground">
                No network dependency issues
                were detected.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-border font-mono text-muted-foreground">
                    <tr>
                      <th className="p-3">
                        Severity
                      </th>
                      <th className="p-3">
                        Code
                      </th>
                      <th className="p-3">
                        Entity
                      </th>
                      <th className="p-3">
                        Summary
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {analysis.issues.map(
                      (issue) => (
                        <tr
                          key={
                            issue.issue_id
                          }
                          className="border-b border-border last:border-0"
                        >
                          <td className="p-3 uppercase">
                            {
                              issue
                                .severity
                            }
                          </td>

                          <td className="p-3 font-mono">
                            {issue.code}
                          </td>

                          <td className="p-3">
                            {issue
                              .entity_name ??
                              "—"}
                          </td>

                          <td className="p-3">
                            {
                              issue
                                .summary
                            }
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </section>


          <section className="overflow-hidden rounded-md border border-border bg-card">
            <header className="border-b border-border px-5 py-4">
              <h2 className="font-heading text-lg font-bold">
                Discovered paths
              </h2>
            </header>

            <div className="divide-y divide-border">
              {analysis
                .dependency_paths
                .slice(0, 100)
                .map((path, index) => (
                  <div
                    key={`${path.entity_ids.join(
                      ":",
                    )}-${index}`}
                    className="p-4"
                  >
                    <p className="font-mono text-xs">
                      {path.entity_ids
                        .map((entityId) => {
                          const entity =
                            analysis
                              .entities
                              .find(
                                (item) =>
                                  item.entity_id
                                  === entityId,
                              )

                          return (
                            entity
                              ?.entity_name
                            ?? entityId
                          )
                        })
                        .join(" → ")}
                    </p>

                    <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                      {path
                        .relationship_types
                        .join(" → ")}
                    </p>
                  </div>
                ))}
            </div>
          </section>
        </>
      )}
    </div>
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