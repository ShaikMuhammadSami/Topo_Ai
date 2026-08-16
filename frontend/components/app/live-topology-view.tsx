"use client"

import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  AlertCircle,
  LoaderCircle,
} from "lucide-react"
import { useSearchParams } from "next/navigation"
import { LiveTopologyGraph } from "@/components/app/live-topology-graph"
import {
  getSnapshot,
  getSnapshotDiff,
  listSnapshots,
} from "@/lib/topo-api"
import type {
  GraphSnapshot,
  SnapshotDiffResult,
  SnapshotSummary,
} from "@/lib/topo-types"
import {
  buildVisualTopology,
  type VisualNode,
} from "@/lib/topology-visualizer"

export function LiveTopologyView() {
  const [snapshots, setSnapshots] =
    useState<SnapshotSummary[]>([])

  const [fromSnapshotId, setFromSnapshotId] =
    useState("")

  const [toSnapshotId, setToSnapshotId] =
    useState("")

  const [snapshot, setSnapshot] =
    useState<GraphSnapshot | null>(null)
  
  const searchParams = useSearchParams()

  const requestedSnapshotId =
   searchParams.get("snapshot_id") ?? ""

  const requestedEntityId =
    searchParams.get("entity_id") ?? ""

  const [diff, setDiff] =
    useState<SnapshotDiffResult | null>(null)

  const [selectedNode, setSelectedNode] =
    useState<VisualNode | null>(null)

  const [loading, setLoading] =
    useState(true)

  const [error, setError] =
    useState<string | null>(null)

  useEffect(() => {
    async function initialise() {
      setLoading(true)
      setError(null)

      try {
        const results =
          await listSnapshots(100)

        setSnapshots(results)

        const newest = results[0]

        if (!newest) {
          return
        }
        const requestedSnapshot =
  results.find(
    (item) =>
      item.snapshot_id ===
      requestedSnapshotId,
  )

const selectedSnapshot =
  requestedSnapshot ??
  results[0]

if (!selectedSnapshot) {
  return
}

        const previous = results.find(
          (candidate) =>
            candidate.snapshot_id !==
              selectedSnapshot.snapshot_id &&
            candidate.cluster_name ===
              selectedSnapshot.cluster_name &&
            candidate.namespace ===
              selectedSnapshot.namespace,
        )

        setToSnapshotId(
          selectedSnapshot.snapshot_id,
        )

        setFromSnapshotId(
          previous?.snapshot_id ?? "",
        )
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to load snapshots.",
        )
      } finally {
        setLoading(false)
      }
    }

    void initialise()
  }, [requestedSnapshotId])

  useEffect(() => {
    async function loadTopology() {
      if (!toSnapshotId) {
        setSnapshot(null)
        setDiff(null)
        return
      }

      setLoading(true)
      setError(null)

      try {
        const selectedSnapshot =
          await getSnapshot(
            toSnapshotId,
          )

        setSnapshot(selectedSnapshot)

        if (
          fromSnapshotId &&
          fromSnapshotId !== toSnapshotId
        ) {
          const selectedDiff =
            await getSnapshotDiff(
              fromSnapshotId,
              toSnapshotId,
            )

          setDiff(selectedDiff)
        } else {
          setDiff(null)
        }

        setSelectedNode(null)
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to build topology.",
        )
      } finally {
        setLoading(false)
      }
    }

    void loadTopology()
  }, [
    fromSnapshotId,
    toSnapshotId,
  ])

  const topology = useMemo(
    () =>
      snapshot
        ? buildVisualTopology(
            snapshot,
            diff,
          )
        : null,
    [snapshot, diff],
  )
  useEffect(() => {
  if (
    !topology ||
    !requestedEntityId
  ) {
    return
  }

  const requestedNode =
    topology.nodes.find(
      (node) =>
        node.id ===
        requestedEntityId,
    )

  if (requestedNode) {
    setSelectedNode(
      requestedNode,
    )
  }
}, [
  topology,
  requestedEntityId,
])

  const toSnapshotSummary =
    snapshots.find(
      (item) =>
        item.snapshot_id ===
        toSnapshotId,
    )

  const compatibleFromSnapshots =
    snapshots.filter(
      (item) =>
        item.snapshot_id !==
          toSnapshotId &&
        item.cluster_name ===
          toSnapshotSummary?.cluster_name &&
        item.namespace ===
          toSnapshotSummary?.namespace,
    )

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-6 p-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
            real temporal topology
          </p>

          <h2 className="font-heading text-4xl font-black tracking-tight">
            Kubernetes snapshot graph
          </h2>

          <p className="mt-2 max-w-2xl leading-relaxed text-muted-foreground">
            Compare two real snapshots. Added,
            removed and changed resources are
            highlighted using data from the
            Kubernetes collector.
          </p>
        </div>
      </header>

      <section className="grid gap-4 rounded-md border border-border bg-card p-5 lg:grid-cols-2">
        <SnapshotSelector
          label="From snapshot"
          value={fromSnapshotId}
          snapshots={
            compatibleFromSnapshots
          }
          onChange={
            setFromSnapshotId
          }
          allowEmpty
        />

        <SnapshotSelector
          label="To snapshot"
          value={toSnapshotId}
          snapshots={snapshots}
          onChange={setToSnapshotId}
        />
      </section>

      {error && (
        <div className="flex items-start gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 rounded-md border border-border bg-card p-5 font-mono text-xs text-muted-foreground">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Loading topology…
        </div>
      )}

      {snapshot &&
        topology &&
        !loading && (
          <>
            <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-6">
              <Metric
                label="NODES"
                value={
                  topology.nodes.length
                }
              />

              <Metric
                label="EDGES"
                value={
                  topology.edges.length
                }
              />

              <Metric
                label="ADDED"
                value={
                  diff?.summary
                    .added_entities ?? 0
                }
                className="text-ok"
              />

              <Metric
                label="CHANGED"
                value={
                  diff?.summary
                    .changed_entities ?? 0
                }
                className="text-warn"
              />

              <Metric
                label="REMOVED"
                value={
                  diff?.summary
                    .removed_entities ?? 0
                }
                className="text-danger"
              />

              <Metric
                label="SNAPSHOT"
                value={new Date(
                  snapshot.collected_at,
                ).toLocaleTimeString()}
              />
            </section>

            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
              <LiveTopologyGraph
                topology={topology}
                selectedNodeId={
                  selectedNode?.id ?? null
                }
                onSelectNode={
                  setSelectedNode
                }
              />

              <aside className="space-y-5 rounded-md border border-border bg-card p-5">
                <Legend />

                <div className="border-t border-border pt-4">
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Selected resource
                  </p>

                  {selectedNode ? (
                    <NodeDetails
                      node={selectedNode}
                    />
                  ) : (
                    <p className="mt-3 font-mono text-xs leading-relaxed text-muted-foreground">
                      Select a graph node to
                      inspect its canonical
                      entity properties.
                    </p>
                  )}
                </div>

                <div className="border-t border-border pt-4">
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Diff summary
                  </p>

                  <div className="mt-3 space-y-1 font-mono text-[11px]">
                    <p className="text-ok">
                      +{" "}
                      {diff?.summary
                        .added_entities ?? 0}{" "}
                      entities
                    </p>

                    <p className="text-warn">
                      ~{" "}
                      {diff?.summary
                        .changed_entities ?? 0}{" "}
                      entities
                    </p>

                    <p className="text-danger">
                      -{" "}
                      {diff?.summary
                        .removed_entities ?? 0}{" "}
                      entities
                    </p>

                    <p className="text-muted-foreground">
                      +{" "}
                      {diff?.summary
                        .added_relationships ??
                        0}{" "}
                      relationships
                    </p>

                    <p className="text-muted-foreground">
                      -{" "}
                      {diff?.summary
                        .removed_relationships ??
                        0}{" "}
                      relationships
                    </p>
                  </div>
                </div>
              </aside>
            </div>
          </>
        )}
    </div>
  )
}

function SnapshotSelector({
  label,
  value,
  snapshots,
  onChange,
  allowEmpty = false,
}: {
  label: string
  value: string
  snapshots: SnapshotSummary[]
  onChange: (value: string) => void
  allowEmpty?: boolean
}) {
  return (
    <label>
      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </span>

      <select
        value={value}
        onChange={(event) =>
          onChange(event.target.value)
        }
        className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
      >
        {allowEmpty && (
          <option value="">
            No comparison
          </option>
        )}

        {snapshots.map((item) => (
          <option
            key={item.snapshot_id}
            value={item.snapshot_id}
          >
            {new Date(
              item.collected_at,
            ).toLocaleString()}
            {" — "}
            {item.cluster_name}
            {" — "}
            {item.namespace ?? "*"}
          </option>
        ))}
      </select>
    </label>
  )
}

function Metric({
  label,
  value,
  className = "",
}: {
  label: string
  value: string | number
  className?: string
}) {
  return (
    <div className="bg-card px-4 py-3 text-center">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>

      <p
        className={`mt-1 truncate font-heading text-xl font-bold ${className}`}
      >
        {value}
      </p>
    </div>
  )
}

function Legend() {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        Snapshot diff legend
      </p>

      <ul className="mt-3 space-y-2 font-mono text-[11px]">
        <LegendItem
          label="unchanged"
          className="border-muted-foreground"
        />

        <LegendItem
          label="added"
          className="border-ok bg-ok/10"
        />

        <LegendItem
          label="changed"
          className="border-warn bg-warn/10"
        />

        <LegendItem
          label="removed"
          className="border-danger border-dashed bg-danger/10"
        />
      </ul>
    </div>
  )
}

function LegendItem({
  label,
  className,
}: {
  label: string
  className: string
}) {
  return (
    <li className="flex items-center gap-2">
      <span
        className={`h-3 w-3 rounded-sm border ${className}`}
      />
      {label}
    </li>
  )
}

function NodeDetails({
  node,
}: {
  node: VisualNode
}) {
  const properties = Object.entries(
    node.entity.properties,
  )

  return (
    <div className="mt-3 space-y-4">
      <div>
        <p className="break-all font-mono text-sm font-semibold">
          {node.label}
        </p>

        <p className="mt-1 font-mono text-[10px] text-muted-foreground">
          {node.kind}
        </p>

        <p className="mt-1 font-mono text-[10px] uppercase text-info">
          {node.state}
        </p>
      </div>

      <dl className="space-y-2 font-mono text-[10px]">
        {properties
          .slice(0, 12)
          .map(([key, value]) => (
            <div
              key={key}
              className="grid grid-cols-[100px_1fr] gap-2"
            >
              <dt className="text-muted-foreground">
                {key}
              </dt>

              <dd className="break-all text-foreground">
                {displayValue(value)}
              </dd>
            </div>
          ))}
      </dl>
    </div>
  )
}

function displayValue(
  value: unknown,
): string {
  if (
    value === null ||
    value === undefined
  ) {
    return "—"
  }

  if (typeof value === "object") {
    return JSON.stringify(value)
  }

  return String(value)
}
