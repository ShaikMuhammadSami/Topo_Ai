"use client"

import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  AlertCircle,
  CheckCircle2,
  Database,
  LoaderCircle,
  RefreshCw,
  Server,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  captureSnapshot,
  getSnapshot,
  listSnapshots,
} from "@/lib/topo-api"
import type {
  GraphSnapshot,
  SnapshotSummary,
} from "@/lib/topo-types"

export function LiveClusterView() {
  const [snapshots, setSnapshots] =
    useState<SnapshotSummary[]>([])

  const [
    selectedSnapshotId,
    setSelectedSnapshotId,
  ] = useState("")

  const [snapshot, setSnapshot] =
    useState<GraphSnapshot | null>(null)

  const [namespace, setNamespace] =
    useState("")

  const [loadingList, setLoadingList] =
    useState(true)

  const [
    loadingSnapshot,
    setLoadingSnapshot,
  ] = useState(false)

  const [capturing, setCapturing] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)

  async function refreshSnapshots(
    preferredSnapshotId?: string,
  ) {
    setLoadingList(true)
    setError(null)

    try {
      const results = await listSnapshots()

      setSnapshots(results)

      const nextId =
        preferredSnapshotId ||
        selectedSnapshotId ||
        results[0]?.snapshot_id ||
        ""

      setSelectedSnapshotId(nextId)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to list snapshots.",
      )
    } finally {
      setLoadingList(false)
    }
  }

  async function loadSelectedSnapshot(
    snapshotId: string,
  ) {
    if (!snapshotId) {
      setSnapshot(null)
      return
    }

    setLoadingSnapshot(true)
    setError(null)

    try {
      const result =
        await getSnapshot(snapshotId)

      setSnapshot(result)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load the snapshot.",
      )
    } finally {
      setLoadingSnapshot(false)
    }
  }

  async function handleCapture() {
    setCapturing(true)
    setError(null)

    try {
      const created =
        await captureSnapshot(
          namespace.trim() || undefined,
        )

      await refreshSnapshots(
        created.snapshot_id,
      )
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to capture a snapshot.",
      )
    } finally {
      setCapturing(false)
    }
  }

  useEffect(() => {
    void refreshSnapshots()
  }, [])

  useEffect(() => {
    void loadSelectedSnapshot(
      selectedSnapshotId,
    )
  }, [selectedSnapshotId])

  const entityCounts = useMemo(() => {
    const counts = new Map<string, number>()

    for (
      const entity
      of snapshot?.entities ?? []
    ) {
      counts.set(
        entity.kind,
        (counts.get(entity.kind) ?? 0) + 1,
      )
    }

    return Array
      .from(counts.entries())
      .sort(
        ([first], [second]) =>
          first.localeCompare(second),
      )
  }, [snapshot])

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
            real backend data
          </p>

          <h2 className="font-heading text-4xl font-black tracking-tight">
            Live Kubernetes discovery
          </h2>

          <p className="mt-2 max-w-2xl leading-relaxed text-muted-foreground">
            Topo continuously checkpoints discovered
            infrastructure. Inspect immutable history here,
            or use the advanced capture control when you
            need an immediate manual refresh.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-sm border border-ok/30 bg-ok/10 px-3 py-2 font-mono text-xs text-ok">
          <CheckCircle2 className="h-4 w-4" />
          backend-connected view
        </div>
      </div>

      <section className="rounded-md border border-border bg-card p-5">
        <p className="mb-4 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Advanced manual capture
        </p>
        <div className="grid gap-4 lg:grid-cols-[1fr_auto_auto]">
          <label className="space-y-2">
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Namespace filter
            </span>

            <input
              value={namespace}
              onChange={(event) =>
                setNamespace(event.target.value)
              }
              placeholder="Leave empty for all namespaces"
              className="h-9 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none placeholder:text-muted-foreground focus:border-info"
            />
          </label>

          <Button
            className="self-end"
            variant="outline"
            onClick={() =>
              void handleCapture()
            }
            disabled={capturing}
          >
            {capturing ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <Database />
            )}

            {capturing
              ? "Capturing"
              : "Capture now"}
          </Button>

          <Button
            className="self-end"
            variant="outline"
            onClick={() =>
              void refreshSnapshots()
            }
            disabled={loadingList}
          >
            <RefreshCw
              className={
                loadingList
                  ? "animate-spin"
                  : ""
              }
            />

            Refresh
          </Button>
        </div>
      </section>

      {error && (
        <div className="flex items-start gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-sm text-danger">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />

          <div>
            <p className="font-semibold">
              Backend request failed
            </p>

            <p className="mt-1 font-mono text-xs">
              {error}
            </p>
          </div>
        </div>
      )}

      <section className="rounded-md border border-border bg-card p-5">
        <label
          htmlFor="snapshot"
          className="block"
        >
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Stored snapshot
          </span>

          <select
            id="snapshot"
            value={selectedSnapshotId}
            onChange={(event) =>
              setSelectedSnapshotId(
                event.target.value,
              )
            }
            className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
          >
            <option value="">
              Select a snapshot
            </option>

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

        <p className="mt-2 font-mono text-[11px] text-muted-foreground">
          {snapshots.length} stored snapshots
        </p>
      </section>

      {loadingSnapshot && (
        <div className="flex items-center gap-2 rounded-md border border-border bg-card p-5 font-mono text-xs text-muted-foreground">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Loading snapshot…
        </div>
      )}

      {snapshot && !loadingSnapshot && (
        <>
          <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-4">
            <MetricCard
              label="ENTITIES"
              value={snapshot.entities.length}
            />

            <MetricCard
              label="RELATIONSHIPS"
              value={
                snapshot.relationships.length
              }
            />

            <MetricCard
              label="CLUSTER"
              value={
                snapshot.scope.cluster ??
                "Unknown"
              }
            />

            <MetricCard
              label="NAMESPACE"
              value={
                snapshot.scope.namespace ??
                "—"
              }
            />
          </section>

          <section className="rounded-md border border-border bg-card p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  Entity inventory
                </p>

                <h3 className="mt-1 font-heading text-lg font-bold">
                  Resources by kind
                </h3>
              </div>

              <span className="font-mono text-[11px] text-muted-foreground">
                {new Date(
                  snapshot.collected_at,
                ).toLocaleString()}
              </span>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {entityCounts.map(
                ([kind, count]) => (
                  <span
                    key={kind}
                    className="rounded-sm border border-border bg-background px-2.5 py-1.5 font-mono text-[11px] text-muted-foreground"
                  >
                    <span className="text-foreground">
                      {kind}
                    </span>
                    {" · "}
                    {count}
                  </span>
                ),
              )}
            </div>
          </section>

          <section className="overflow-x-auto rounded-md border border-border bg-card">
            <header className="flex items-center justify-between border-b border-border px-5 py-3">
              <div className="flex items-center gap-2">
                <Server className="h-4 w-4 text-info" />

                <h3 className="font-heading text-sm font-bold">
                  Discovered entities
                </h3>
              </div>

              <span className="font-mono text-[11px] text-muted-foreground">
                source: kubernetes
              </span>
            </header>

            <table className="w-full min-w-[900px] border-collapse">
              <thead>
                <tr className="border-b border-border font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  <TableHeader>
                    Name
                  </TableHeader>
                  <TableHeader>
                    Kind
                  </TableHeader>
                  <TableHeader>
                    Type
                  </TableHeader>
                  <TableHeader>
                    Environment
                  </TableHeader>
                  <TableHeader>
                    Namespace
                  </TableHeader>
                  <TableHeader>
                    Entity heuristic score
                  </TableHeader>
                </tr>
              </thead>

              <tbody className="font-mono text-[12px]">
                {snapshot.entities.map(
                  (entity) => (
                    <tr
                      key={entity.id}
                      className="border-b border-border last:border-0 hover:bg-secondary/40"
                    >
                      <TableCell className="font-semibold">
                        {entity.name}
                      </TableCell>

                      <TableCell>
                        {entity.kind}
                      </TableCell>

                      <TableCell className="text-muted-foreground">
                        {entity.entity_type}
                      </TableCell>

                      <TableCell className="text-muted-foreground">
                        {entity.environment ??
                          "—"}
                      </TableCell>

                      <TableCell className="text-muted-foreground">
                        {propertyText(
                          entity.properties
                            .namespace,
                        )}
                      </TableCell>

                      <TableCell>
                        <span className="text-ok">
                          {entity.confidence.toFixed(2)}
                        </span>
                      </TableCell>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </section>
        </>
      )}

      {!snapshot &&
        !loadingSnapshot &&
        !loadingList && (
          <div className="rounded-md border border-dashed border-border p-10 text-center">
            <Server className="mx-auto h-6 w-6 text-muted-foreground" />

            <p className="mt-3 text-sm font-medium">
              No snapshot selected
            </p>

            <p className="mt-1 font-mono text-xs text-muted-foreground">
              Capture or select a snapshot.
            </p>
          </div>
        )}
    </div>
  )
}

function MetricCard({
  label,
  value,
}: {
  label: string
  value: string | number
}) {
  return (
    <div className="min-w-0 bg-card px-5 py-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>

      <p className="mt-1 truncate font-heading text-2xl font-bold">
        {value}
      </p>
    </div>
  )
}

function TableHeader({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <th className="px-4 py-3 text-left font-normal">
      {children}
    </th>
  )
}

function TableCell({
  children,
  className = "",
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <td className={`px-4 py-3 ${className}`}>
      {children}
    </td>
  )
}

function propertyText(
  value: unknown,
): string {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "—"
  }

  return String(value)
}
