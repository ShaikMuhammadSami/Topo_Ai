"use client"

import Link from "next/link"
import {
  useCallback,
  useEffect,
  useState,
} from "react"
import {
  AlertCircle,
  CheckCircle2,
  CircleHelp,
  ExternalLink,
  LoaderCircle,
  RefreshCw,
  Server,
  ShieldCheck,
  ShieldX,
} from "lucide-react"

import {
  Button,
  buttonVariants,
} from "@/components/ui/button"
import {
  getRecoveryVerification,
  listRecoveryVerifications,
  listSnapshots,
  verifyRecovery,
} from "@/lib/topo-api"
import type {
  RecoveryCheck,
  RecoveryCheckStatus,
  RecoveryStatus,
  RecoveryVerification,
  RecoveryVerificationSummary,
  RemediationRecommendation,
  SnapshotSummary,
} from "@/lib/topo-types"
import { cn } from "@/lib/utils"


const recoveryStatusStyles: Record<
  RecoveryStatus,
  string
> = {
  verified:
    "border-ok/30 bg-ok/10 text-ok",
  failed:
    "border-danger/30 bg-danger/10 text-danger",
  inconclusive:
    "border-warn/30 bg-warn/10 text-warn",
}


const checkStatusStyles: Record<
  RecoveryCheckStatus,
  string
> = {
  pass:
    "border-ok/30 bg-ok/5 text-ok",
  fail:
    "border-danger/30 bg-danger/5 text-danger",
  unknown:
    "border-warn/30 bg-warn/5 text-warn",
}


export function IncidentRecoveryVerification({
  recommendation,
}: {
  recommendation: RemediationRecommendation
}) {
  const [snapshots, setSnapshots] =
    useState<SnapshotSummary[]>([])

  const [
    verifications,
    setVerifications,
  ] = useState<
    RecoveryVerificationSummary[]
  >([])

  const [
    selectedSnapshotId,
    setSelectedSnapshotId,
  ] = useState("")

  const [
    selectedVerificationId,
    setSelectedVerificationId,
  ] = useState("")

  const [verification, setVerification] =
    useState<RecoveryVerification | null>(
      null,
    )

  const [loading, setLoading] =
    useState(false)

  const [verifying, setVerifying] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)


  const refresh = useCallback(
    async (
      preferredVerificationId?: string,
    ) => {
      if (
        recommendation.status !==
          "applied" ||
        !recommendation.applied_at
      ) {
        setSnapshots([])
        setVerifications([])
        setSelectedSnapshotId("")
        setSelectedVerificationId("")
        setVerification(null)
        return
      }

      setLoading(true)
      setError(null)

      try {
        const [
          snapshotResults,
          verificationResults,
        ] = await Promise.all([
          listSnapshots(100),
          listRecoveryVerifications({
            recommendationId:
              recommendation
                .recommendation_id,
            limit: 50,
          }),
        ])

        const appliedAt = Date.parse(
          recommendation.applied_at,
        )

        const candidateSnapshots =
          snapshotResults
            .filter((snapshot) => {
              const sameCluster =
                snapshot.cluster_name ===
                recommendation.cluster_name

              const sameNamespace =
                (
                  snapshot.namespace ??
                  null
                ) ===
                (
                  recommendation.namespace ??
                  null
                )

              const capturedAfterAction =
                Date.parse(
                  snapshot.collected_at,
                ) > appliedAt

              const kubernetesSnapshot =
                snapshot.snapshot_id.startsWith(
                  "snapshot:kubernetes:",
                )

              return (
                sameCluster &&
                sameNamespace &&
                capturedAfterAction &&
                kubernetesSnapshot
              )
            })
            .sort(
              (first, second) =>
                Date.parse(
                  second.collected_at,
                ) -
                Date.parse(
                  first.collected_at,
                ),
            )

        setSnapshots(
          candidateSnapshots,
        )

        setSelectedSnapshotId(
          (current) => {
            if (
              current &&
              candidateSnapshots.some(
                (snapshot) =>
                  snapshot.snapshot_id ===
                  current,
              )
            ) {
              return current
            }

            return (
              candidateSnapshots[0]
                ?.snapshot_id ?? ""
            )
          },
        )

        setVerifications(
          verificationResults,
        )

        setSelectedVerificationId(
          (current) => {
            if (
              preferredVerificationId &&
              verificationResults.some(
                (item) =>
                  item.verification_id ===
                  preferredVerificationId,
              )
            ) {
              return preferredVerificationId
            }

            if (
              current &&
              verificationResults.some(
                (item) =>
                  item.verification_id ===
                  current,
              )
            ) {
              return current
            }

            return (
              verificationResults[0]
                ?.verification_id ?? ""
            )
          },
        )

        if (
          verificationResults.length ===
          0
        ) {
          setVerification(null)
        }
      } catch (requestError) {
        setError(
          errorMessage(requestError),
        )
      } finally {
        setLoading(false)
      }
    },
    [
      recommendation.applied_at,
      recommendation.cluster_name,
      recommendation.namespace,
      recommendation.recommendation_id,
      recommendation.status,
    ],
  )


  useEffect(() => {
    void refresh()
  }, [refresh])


  useEffect(() => {
    if (!selectedVerificationId) {
      setVerification(null)
      return
    }

    let cancelled = false

    async function loadVerification() {
      setLoading(true)
      setError(null)

      try {
        const result =
          await getRecoveryVerification(
            selectedVerificationId,
          )

        if (!cancelled) {
          setVerification(result)
        }
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

    void loadVerification()

    return () => {
      cancelled = true
    }
  }, [selectedVerificationId])


  async function handleVerify() {
    if (!selectedSnapshotId) {
      setError(
        "Select a post-remediation snapshot.",
      )
      return
    }

    setVerifying(true)
    setError(null)

    try {
      const result =
        await verifyRecovery(
          recommendation
            .recommendation_id,
          selectedSnapshotId,
        )

      setVerification(result)

      setSelectedVerificationId(
        result.verification_id,
      )

      await refresh(
        result.verification_id,
      )
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setVerifying(false)
    }
  }


  if (
    recommendation.status !==
    "applied"
  ) {
    return (
      <section className="rounded-md border border-dashed border-border p-6">
        <div className="flex items-start gap-3">
          <CircleHelp className="mt-0.5 h-5 w-5 text-muted-foreground" />

          <div>
            <h4 className="font-heading text-lg font-bold">
              Recovery verification pending
            </h4>

            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Perform the remediation manually,
              verify the workload, and then mark
              this recommendation as applied.
              Topo AI will require a fresh
              topology snapshot captured after
              the applied timestamp.
            </p>
          </div>
        </div>
      </section>
    )
  }


  const topologyUrl =
    verification?.target_entity_id
      ? `/app/topology?snapshot_id=${encodeURIComponent(
          verification.post_snapshot_id,
        )}&entity_id=${encodeURIComponent(
          verification.target_entity_id,
        )}`
      : null


  return (
    <section className="overflow-hidden rounded-md border border-border bg-card">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-ok" />

            <h3 className="font-heading text-lg font-bold">
              Recovery verification
            </h3>
          </div>

          <p className="mt-1 text-sm text-muted-foreground">
            Compare a post-remediation snapshot
            with the incident state and confirm
            whether the original failure stopped.
          </p>
        </div>

        <Button
          variant="outline"
          disabled={loading}
          onClick={() =>
            void refresh(
              selectedVerificationId,
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
      </header>


      {error && (
        <div className="m-5 flex items-start gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}


      <div className="space-y-5 p-5">
        <section className="rounded-md border border-border bg-background p-4">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">
            <label>
              <FieldLabel>
                Post-remediation snapshot
              </FieldLabel>

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

                {snapshots.map(
                  (snapshot) => (
                    <option
                      key={
                        snapshot.snapshot_id
                      }
                      value={
                        snapshot.snapshot_id
                      }
                    >
                      {new Date(
                        snapshot.collected_at,
                      ).toLocaleString()}
                      {" — "}
                      {snapshot.cluster_name}
                      {" — "}
                      {snapshot.namespace ??
                        "*"}
                    </option>
                  ),
                )}
              </select>
            </label>

            <Button
              className="self-end"
              disabled={
                verifying ||
                !selectedSnapshotId
              }
              onClick={() =>
                void handleVerify()
              }
            >
              {verifying ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <ShieldCheck />
              )}

              {verifying
                ? "Verifying"
                : "Verify recovery"}
            </Button>
          </div>

          {snapshots.length === 0 &&
            !loading && (
              <p className="mt-4 font-mono text-xs text-warn">
                No Kubernetes snapshot captured
                after the recommendation was
                marked as applied. Capture a new
                snapshot and select Refresh.
              </p>
            )}
        </section>


        {verifications.length > 0 && (
          <label>
            <FieldLabel>
              Previous verification
            </FieldLabel>

            <select
              value={
                selectedVerificationId
              }
              onChange={(event) =>
                setSelectedVerificationId(
                  event.target.value,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
            >
              <option value="">
                Select verification
              </option>

              {verifications.map(
                (item) => (
                  <option
                    key={
                      item.verification_id
                    }
                    value={
                      item.verification_id
                    }
                  >
                    {new Date(
                      item.generated_at,
                    ).toLocaleString()}
                    {" — "}
                    {item.status}
                    {" — "}
                    check score {item.confidence.toFixed(2)}
                  </option>
                ),
              )}
            </select>
          </label>
        )}


        {loading && !verification ? (
          <LoadingPanel text="Loading recovery evidence…" />
        ) : verification ? (
          <VerificationDetail
            verification={
              verification
            }
            topologyUrl={
              topologyUrl
            }
          />
        ) : (
          <div className="rounded-md border border-dashed border-border p-8 text-center">
            <ShieldCheck className="mx-auto h-7 w-7 text-muted-foreground" />

            <h4 className="mt-4 font-heading text-lg font-bold">
              No recovery result yet
            </h4>

            <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
              Select a post-remediation snapshot
              captured after the applied action,
              then run verification.
            </p>
          </div>
        )}
      </div>
    </section>
  )
}


function VerificationDetail({
  verification,
  topologyUrl,
}: {
  verification: RecoveryVerification
  topologyUrl: string | null
}) {
  return (
    <div className="space-y-5">
      <section
        className={cn(
          "rounded-md border p-5",
          recoveryStatusStyles[
            verification.status
          ],
        )}
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <StatusBadge
              status={
                verification.status
              }
            />

            <h4 className="mt-4 font-heading text-2xl font-bold">
              {statusTitle(
                verification.status,
              )}
            </h4>

            <p className="mt-2 max-w-3xl text-sm leading-relaxed">
              {verification.summary}
            </p>
          </div>

          <p className="font-heading text-4xl font-black">
            {verification.confidence.toFixed(2)} check score
          </p>
        </div>
      </section>


      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-4">
        <Metric
          label="PASSED"
          value={
            verification.passed_count
          }
          className="text-ok"
        />

        <Metric
          label="FAILED"
          value={
            verification.failed_count
          }
          className="text-danger"
        />

        <Metric
          label="UNKNOWN"
          value={
            verification.unknown_count
          }
          className="text-warn"
        />

        <Metric
          label="CHECK SCORE"
          value={verification.confidence.toFixed(2)}
        />
      </section>


      {topologyUrl && (
        <Link
          href={topologyUrl}
          className={cn(
            buttonVariants({
              variant: "outline",
            }),
            "w-full",
          )}
        >
          <Server />
          Open verified target
          <ExternalLink />
        </Link>
      )}


      <DetailSection title="Verification context">
        <DetailRow
          label="applied"
          value={formatDate(
            verification.applied_at,
          )}
        />

        <DetailRow
          label="verified"
          value={formatDate(
            verification.generated_at,
          )}
        />

        <DetailRow
          label="target"
          value={[
            verification
              .target_entity_kind,
            verification
              .target_entity_name,
          ]
            .filter(Boolean)
            .join("/")}
        />

        <DetailRow
          label="pre snapshot"
          value={
            verification
              .pre_snapshot_id
          }
        />

        <DetailRow
          label="post snapshot"
          value={
            verification
              .post_snapshot_id
          }
        />
      </DetailSection>


      <DetailSection title="Recovery checks">
        <div className="space-y-3">
          {verification.checks.map(
            (check) => (
              <RecoveryCheckCard
                key={check.code}
                check={check}
              />
            ),
          )}
        </div>
      </DetailSection>


      {verification.warnings.length >
        0 && (
        <DetailSection title="Warnings">
          <ul className="space-y-2">
            {verification.warnings.map(
              (warning, index) => (
                <li
                  key={`${warning}-${index}`}
                  className="flex items-start gap-2 text-sm text-warn"
                >
                  <span>•</span>
                  <span>{warning}</span>
                </li>
              ),
            )}
          </ul>
        </DetailSection>
      )}
    </div>
  )
}


function RecoveryCheckCard({
  check,
}: {
  check: RecoveryCheck
}) {
  const Icon =
    check.status === "pass"
      ? CheckCircle2
      : check.status === "fail"
        ? ShieldX
        : CircleHelp

  return (
    <article
      className={cn(
        "rounded-md border p-4",
        checkStatusStyles[
          check.status
        ],
      )}
    >
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 h-5 w-5 shrink-0" />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h5 className="font-heading font-bold">
              {check.title}
            </h5>

            <span className="font-mono text-[10px] uppercase">
              {check.status}
            </span>
          </div>

          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {check.summary}
          </p>

          <div className="mt-3 grid gap-2 font-mono text-[10px] sm:grid-cols-2">
            <div>
              <p className="text-muted-foreground">
                expected
              </p>

              <p className="mt-1 break-all text-foreground">
                {check.expected ?? "—"}
              </p>
            </div>

            <div>
              <p className="text-muted-foreground">
                observed
              </p>

              <p className="mt-1 break-all text-foreground">
                {check.observed ?? "—"}
              </p>
            </div>
          </div>

          {Object.keys(
            check.attributes,
          ).length > 0 && (
            <pre className="mt-3 max-h-52 overflow-auto rounded-sm border border-border bg-background p-3 font-mono text-[10px] text-muted-foreground">
              {JSON.stringify(
                check.attributes,
                null,
                2,
              )}
            </pre>
          )}
        </div>
      </div>
    </article>
  )
}


function StatusBadge({
  status,
}: {
  status: RecoveryStatus
}) {
  return (
    <span className="inline-flex rounded-sm border border-current px-2 py-1 font-mono text-[10px] uppercase">
      {status}
    </span>
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
        className={`mt-1 font-heading text-2xl font-bold ${className}`}
      >
        {value}
      </p>
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


function DetailSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="border-t border-border pt-5">
      <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {title}
      </p>

      {children}
    </section>
  )
}


function DetailRow({
  label,
  value,
}: {
  label: string
  value: string | null | undefined
}) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-3 py-1.5 font-mono text-[10px]">
      <span className="text-muted-foreground">
        {label}
      </span>

      <span className="break-all text-foreground">
        {value || "—"}
      </span>
    </div>
  )
}


function LoadingPanel({
  text,
}: {
  text: string
}) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-border p-6 font-mono text-xs text-muted-foreground">
      <LoaderCircle className="h-4 w-4 animate-spin" />
      {text}
    </div>
  )
}


function statusTitle(
  status: RecoveryStatus,
): string {
  if (status === "verified") {
    return "Recovery verified"
  }

  if (status === "failed") {
    return "Recovery not confirmed"
  }

  return "Recovery inconclusive"
}


function formatDate(
  value: string,
): string {
  const parsed = new Date(value)

  return Number.isNaN(
    parsed.getTime(),
  )
    ? value
    : parsed.toLocaleString()
}


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : "An unexpected request error occurred."
}
