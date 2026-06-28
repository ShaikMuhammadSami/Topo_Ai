"use client"

import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  AlertCircle,
  Box,
  CheckCircle2,
  GitCommitHorizontal,
  GitFork,
  LoaderCircle,
  RefreshCw,
  Server,
  Workflow,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  getSnapshot,
  listSnapshots,
} from "@/lib/topo-api"
import {
  buildCodeRuntimeChains,
  stringProperty,
  type CodeRuntimeChain,
} from "@/lib/code-runtime"
import type {
  GraphSnapshot,
  SnapshotSummary,
} from "@/lib/topo-types"

export function CodeToRuntimeView() {
  const [snapshots, setSnapshots] =
    useState<SnapshotSummary[]>([])

  const [
    selectedSnapshotId,
    setSelectedSnapshotId,
  ] = useState("")

  const [snapshot, setSnapshot] =
    useState<GraphSnapshot | null>(null)

  const [loading, setLoading] =
    useState(true)

  const [error, setError] =
    useState<string | null>(null)

  async function loadSnapshotList() {
    setLoading(true)
    setError(null)

    try {
      const results =
        await listSnapshots(100)

      const actionsSnapshots =
        results.filter(
          (item) =>
            item.collector_name ===
              "github-actions-graph-enricher" ||
            item.snapshot_id.startsWith(
              "snapshot:actions-enriched:",
            ),
        )

      setSnapshots(actionsSnapshots)

      if (actionsSnapshots[0]) {
        setSelectedSnapshotId(
          actionsSnapshots[0].snapshot_id,
        )
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to list snapshots.",
      )
    } finally {
      setLoading(false)
    }
  }

  async function loadSelectedSnapshot(
    snapshotId: string,
  ) {
    if (!snapshotId) {
      setSnapshot(null)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const result =
        await getSnapshot(snapshotId)

      setSnapshot(result)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load the enriched snapshot.",
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadSnapshotList()
  }, [])

  useEffect(() => {
    void loadSelectedSnapshot(
      selectedSnapshotId,
    )
  }, [selectedSnapshotId])

  const chains = useMemo(
    () =>
      snapshot
        ? buildCodeRuntimeChains(snapshot)
        : [],
    [snapshot],
  )

  const metrics = useMemo(() => {
    return {
      commits: new Set(
        chains.map(
          (chain) => chain.commit.id,
        ),
      ).size,

      runs: new Set(
        chains.map(
          (chain) => chain.workflowRun.id,
        ),
      ).size,

      images: new Set(
        chains.map(
          (chain) => chain.image.id,
        ),
      ).size,

      workloads: new Set(
        chains.flatMap((chain) =>
          chain.workloads.map(
            (workload) => workload.id,
          ),
        ),
      ).size,
    }
  }, [chains])

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-6 p-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
            verified delivery provenance
          </p>

          <h2 className="font-heading text-4xl font-black tracking-tight">
            Code to runtime
          </h2>

          <p className="mt-2 max-w-3xl leading-relaxed text-muted-foreground">
            Trace a Git commit through its GitHub
            Actions workflow run, container image
            and currently running Kubernetes
            workloads.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-sm border border-ok/30 bg-ok/10 px-3 py-2 font-mono text-xs text-ok">
          <CheckCircle2 className="h-4 w-4" />
          provenance-backed
        </div>
      </header>

      <section className="rounded-md border border-border bg-card p-5">
        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
          <label>
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Actions-enriched snapshot
            </span>

            <select
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

          <Button
            variant="outline"
            className="self-end"
            onClick={() =>
              void loadSnapshotList()
            }
            disabled={loading}
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
          Loading delivery provenance…
        </div>
      )}

      {snapshot && !loading && (
        <>
          <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-5">
            <Metric
              label="CHAINS"
              value={chains.length}
            />

            <Metric
              label="COMMITS"
              value={metrics.commits}
            />

            <Metric
              label="WORKFLOW RUNS"
              value={metrics.runs}
            />

            <Metric
              label="IMAGES"
              value={metrics.images}
            />

            <Metric
              label="WORKLOADS"
              value={metrics.workloads}
            />
          </section>

          <section className="space-y-6">
            {chains.map((chain) => (
              <ChainCard
                key={chain.id}
                chain={chain}
              />
            ))}

            {chains.length === 0 && (
              <div className="rounded-md border border-dashed border-border p-10 text-center">
                <GitFork className="mx-auto h-6 w-6 text-muted-foreground" />

                <p className="mt-3 text-sm font-medium">
                  No complete code-to-runtime chain
                  was found.
                </p>

                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  Confirm that the snapshot contains
                  Commit → Workflow Run → Image
                  relationships.
                </p>
              </div>
            )}
          </section>
        </>
      )}

      {!loading &&
        snapshots.length === 0 && (
          <div className="rounded-md border border-dashed border-border p-10 text-center">
            <Workflow className="mx-auto h-6 w-6 text-muted-foreground" />

            <p className="mt-3 text-sm font-medium">
              No Actions-enriched snapshots found
            </p>

            <p className="mt-1 font-mono text-xs text-muted-foreground">
              Complete the GitHub Actions enrichment
              endpoint first.
            </p>
          </div>
        )}
    </div>
  )
}

function ChainCard({
  chain,
}: {
  chain: CodeRuntimeChain
}) {
  const commitSha =
    stringProperty(
      chain.commit.properties,
      "sha",
    ) ||
    chain.commit.external_id ||
    chain.commit.name

  const commitSummary =
    stringProperty(
      chain.commit.properties,
      "summary",
    )

  const workflowConclusion =
    stringProperty(
      chain.workflowRun.properties,
      "conclusion",
    )

  const workflowStatus =
    stringProperty(
      chain.workflowRun.properties,
      "status",
    )

  const imageDigest =
    stringProperty(
      chain.image.properties,
      "digest",
    )

  const imageRepository =
    stringProperty(
      chain.image.properties,
      "repository",
    )

  const imageTag =
    stringProperty(
      chain.image.properties,
      "tag",
    )

  return (
    <article className="overflow-hidden rounded-md border border-border bg-card">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            {chain.repository?.name ??
              "Git repository"}
          </p>

          <h3 className="mt-1 font-heading text-xl font-bold">
            {commitSummary ||
              `Commit ${commitSha.slice(0, 12)}`}
          </h3>
        </div>

        <ConfidenceBadge
          confidence={chain.confidence}
        />
      </header>

      <div className="grid gap-px bg-border xl:grid-cols-4">
        <ChainStep
          icon={GitCommitHorizontal}
          eyebrow="source revision"
          title={commitSha.slice(0, 12)}
          details={[
            [
              "author",
              stringProperty(
                chain.commit.properties,
                "author_name",
              ),
            ],
            [
              "committed",
              formatDate(
                stringProperty(
                  chain.commit.properties,
                  "committed_at",
                ),
              ),
            ],
          ]}
        />

        <ChainStep
          icon={Workflow}
          eyebrow="workflow run"
          title={chain.workflowRun.name}
          details={[
            [
              "run id",
              chain.workflowRun.external_id ??
                "",
            ],
            [
              "status",
              `${workflowStatus} / ${workflowConclusion}`,
            ],
            [
              "event",
              stringProperty(
                chain.workflowRun.properties,
                "event",
              ),
            ],
          ]}
          tone={
            workflowConclusion === "success"
              ? "ok"
              : "warn"
          }
        />

        <ChainStep
          icon={Box}
          eyebrow="container image"
          title={
            imageRepository ||
            chain.image.name
          }
          details={[
            [
              "tag",
              imageTag || "—",
            ],
            [
              "digest",
              imageDigest
                ? imageDigest.slice(0, 28) +
                  "…"
                : "unresolved",
            ],
            [
              "immutable",
              String(
                chain.image.properties
                  .immutable ?? false,
              ),
            ],
          ]}
        />

        <ChainStep
          icon={Server}
          eyebrow="runtime workloads"
          title={`${chain.workloads.length} resources`}
          details={chain.workloads
            .slice(0, 5)
            .map((workload) => [
              workload.kind.replace(
                "Kubernetes",
                "",
              ),
              workload.name,
            ])}
        />
      </div>

      <footer className="grid gap-5 border-t border-border p-5 lg:grid-cols-3">
        <EvidenceItem
          title="Commit → workflow"
          confidence={
            chain.commitToRun.confidence
          }
          values={[
            [
              "head SHA",
              stringProperty(
                chain.commitToRun.properties,
                "head_sha",
              ).slice(0, 12),
            ],
            [
              "event",
              stringProperty(
                chain.commitToRun.properties,
                "event",
              ),
            ],
          ]}
        />

        <EvidenceItem
          title="Workflow → image"
          confidence={
            chain.runToImage.confidence
          }
          values={[
            [
              "method",
              chain.mappingMethod,
            ],
            [
              "run ID",
              stringProperty(
                chain.runToImage.properties,
                "workflow_run_id",
              ),
            ],
            [
              "digest",
              digestAgreement(
                chain.runToImage.properties,
              ),
            ],
          ]}
        />

        <EvidenceItem
          title="Image → runtime"
          confidence={
            chain.workloadToImage.length
              ? Math.min(
                  ...chain.workloadToImage.map(
                    (item) => item.confidence,
                  ),
                )
              : 0
          }
          values={[
            [
              "relationships",
              String(
                chain.workloadToImage.length,
              ),
            ],
            [
              "source",
              "Kubernetes runtime",
            ],
          ]}
        />
      </footer>
    </article>
  )
}

function ChainStep({
  icon: Icon,
  eyebrow,
  title,
  details,
  tone = "normal",
}: {
  icon: typeof GitCommitHorizontal
  eyebrow: string
  title: string
  details: Array<[string, string]>
  tone?: "normal" | "ok" | "warn"
}) {
  return (
    <div className="min-w-0 bg-card p-5">
      <div className="flex items-center gap-2">
        <Icon
          className={
            tone === "ok"
              ? "h-4 w-4 text-ok"
              : tone === "warn"
                ? "h-4 w-4 text-warn"
                : "h-4 w-4 text-info"
          }
        />

        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {eyebrow}
        </p>
      </div>

      <p className="mt-3 break-all font-heading text-lg font-bold">
        {title}
      </p>

      <dl className="mt-4 space-y-2 font-mono text-[10px]">
        {details.map(([label, value]) => (
          <div
            key={`${label}-${value}`}
            className="grid grid-cols-[80px_1fr] gap-2"
          >
            <dt className="text-muted-foreground">
              {label}
            </dt>

            <dd className="min-w-0 break-all text-foreground">
              {value || "—"}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function EvidenceItem({
  title,
  confidence,
  values,
}: {
  title: string
  confidence: number
  values: Array<[string, string]>
}) {
  return (
    <div className="rounded-sm border border-border bg-background p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {title}
        </p>

        <span className="font-mono text-[11px] text-ok">
          {Math.round(confidence * 100)}%
        </span>
      </div>

      <dl className="mt-3 space-y-2 font-mono text-[10px]">
        {values.map(([label, value]) => (
          <div
            key={`${label}-${value}`}
            className="grid grid-cols-[90px_1fr] gap-2"
          >
            <dt className="text-muted-foreground">
              {label}
            </dt>

            <dd className="break-all">
              {value || "—"}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function ConfidenceBadge({
  confidence,
}: {
  confidence: number
}) {
  const percent = Math.round(
    confidence * 100,
  )

  return (
    <span className="rounded-sm border border-ok/30 bg-ok/10 px-3 py-1.5 font-mono text-xs font-semibold text-ok">
      {percent}% chain confidence
    </span>
  )
}

function Metric({
  label,
  value,
}: {
  label: string
  value: number
}) {
  return (
    <div className="bg-card px-5 py-4 text-center">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>

      <p className="mt-1 font-heading text-2xl font-bold">
        {value}
      </p>
    </div>
  )
}

function digestAgreement(
  properties: Record<string, unknown>,
): string {
  const annotated =
    stringProperty(
      properties,
      "annotated_digest",
    )

  const runtime =
    stringProperty(
      properties,
      "runtime_digest",
    )

  if (!annotated || !runtime) {
    return "not fully verified"
  }

  return annotated === runtime
    ? "matching"
    : "mismatch"
}

function formatDate(
  value: string,
): string {
  if (!value) {
    return "—"
  }

  const parsed = new Date(value)

  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleString()
}