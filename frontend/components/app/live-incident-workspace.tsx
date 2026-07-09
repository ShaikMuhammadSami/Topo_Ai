"use client"

import Link from "next/link"
import { useRouter,
  useSearchParams,
 } from "next/navigation"
import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  ExternalLink,
  FileSearch,
  GitCompareArrows,
  LoaderCircle,
  RefreshCw,
  Server,
  ShieldAlert,
  Sparkles,
} from "lucide-react"
import { IncidentInbox } from "@/components/app/incident-inbox"
import {
  Button,
  buttonVariants,
} from "@/components/ui/button"
import {
  analyzeIncident,
  getIncidentAnalysis,
  listIncidentAnalyses,
  listSignals,
} from "@/lib/topo-api"
import type {
  IncidentAnalysis,
  IncidentAnalysisSummary,
  IncidentEvidence,
  RootCauseHypothesis,
  SignalSummary,
} from "@/lib/topo-types"
import { cn } from "@/lib/utils"
import { IncidentRecommendations } from "@/components/app/incident-recommendations"

export function LiveIncidentWorkspace() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const requestedSignalId =
    searchParams.get("signal_id") ?? ""

  const requestedAnalysisId =
    searchParams.get("analysis_id") ?? ""

  const requestedIncidentId =
  searchParams.get("incident_id") ?? ""

  const [signals, setSignals] =
    useState<SignalSummary[]>([])

  const [analyses, setAnalyses] =
    useState<IncidentAnalysisSummary[]>([])

  const [
    selectedSignalId,
    setSelectedSignalId,
  ] = useState("")

  const [
    selectedAnalysisId,
    setSelectedAnalysisId,
  ] = useState("")

  const [analysis, setAnalysis] =
    useState<IncidentAnalysis | null>(null)

  const [
    selectedHypothesisId,
    setSelectedHypothesisId,
  ] = useState("")
  const [
    selectedIncidentId,
    setSelectedIncidentId,
  ] = useState("")
  const [lookbackMinutes, setLookbackMinutes] =
    useState(60)

  const [graceMinutes, setGraceMinutes] =
    useState(2)

  const [maxGraphHops, setMaxGraphHops] =
    useState(6)

  const [maxHypotheses, setMaxHypotheses] =
    useState(10)

  const [loading, setLoading] =
    useState(true)

  const [analyzing, setAnalyzing] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)
function openAnalysisFromIncident(
  analysisId: string,
) {
  if (!analysisId) {
    return
  }

  setSelectedAnalysisId(analysisId)

  router.push(
    `/app?analysis_id=${encodeURIComponent(
      analysisId,
    )}`,
    {
      scroll: false,
    },
  )

  void loadAnalysis(analysisId)

  window.setTimeout(() => {
    document
      .getElementById(
        "incident-analysis-panel",
      )
      ?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      })
  }, 150)
}

  async function loadAnalysis(
    analysisId: string,
  ) {
    if (!analysisId) {
      setAnalysis(null)
      setSelectedHypothesisId("")
      return
    }

    setLoading(true)
    setError(null)

    try {
      const result =
        await getIncidentAnalysis(
          analysisId,
        )

      setAnalysis(result)

      setSelectedAnalysisId(
        result.analysis_id,
      )

      setSelectedSignalId(
        result.signal_id,
      )

      setLookbackMinutes(
        result.lookback_minutes,
      )

      setGraceMinutes(
        result.grace_minutes,
      )

      setMaxGraphHops(
        result.max_graph_hops,
      )

      setSelectedHypothesisId(
        result.hypotheses[0]
          ?.hypothesis_id ?? "",
      )
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  async function loadWorkspace() {
    setLoading(true)
    setError(null)

    try {
      const [
        signalResults,
        analysisResults,
      ] = await Promise.all([
        listSignals({
          limit: 500,
        }),
        listIncidentAnalyses({
          limit: 100,
        }),
      ])

      const incidentSignals =
        signalResults.filter(
          (signal) =>
            signal.severity ===
              "critical" ||
            signal.severity === "error" ||
            signal.severity ===
              "warning",
        )

      setSignals(incidentSignals)
      setAnalyses(analysisResults)

      if (requestedAnalysisId) {
        await loadAnalysis(
          requestedAnalysisId,
        )

        return
      }

      const requestedSignal =
        incidentSignals.find(
          (signal) =>
            signal.signal_id ===
            requestedSignalId,
        )

      const nextSignalId =
        requestedSignal?.signal_id ??
        incidentSignals[0]?.signal_id ??
        ""

      setSelectedSignalId(
        nextSignalId,
      )

      const existingAnalysis =
        analysisResults.find(
          (item) =>
            item.signal_id ===
            nextSignalId,
        )

      if (existingAnalysis) {
        await loadAnalysis(
          existingAnalysis.analysis_id,
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
  if (requestedIncidentId) {
    setSelectedIncidentId(
      requestedIncidentId,
    )
  }

  void loadWorkspace()
}, [
  requestedSignalId,
  requestedAnalysisId,
  requestedIncidentId,
])
  useEffect(() => {
    void loadWorkspace()
  }, [
    requestedSignalId,
    requestedAnalysisId,
  ])


  useEffect(() => {
    if (!analysis) {
      return
    }

    const stillExists =
      analysis.hypotheses.some(
        (hypothesis) =>
          hypothesis.hypothesis_id ===
          selectedHypothesisId,
      )

    if (!stillExists) {
      setSelectedHypothesisId(
        analysis.hypotheses[0]
          ?.hypothesis_id ?? "",
      )
    }
  }, [
    analysis,
    selectedHypothesisId,
  ])


  const selectedSignal =
    signals.find(
      (signal) =>
        signal.signal_id ===
        selectedSignalId,
    ) ?? null


  const selectedHypothesis =
    analysis?.hypotheses.find(
      (hypothesis) =>
        hypothesis.hypothesis_id ===
        selectedHypothesisId,
    ) ??
    analysis?.hypotheses[0] ??
    null


  async function handleAnalyze() {
    if (!selectedSignalId) {
      setError(
        "Select a failure signal before running analysis.",
      )

      return
    }

    setAnalyzing(true)
    setError(null)

    try {
      const result =
        await analyzeIncident(
          selectedSignalId,
          {
            lookbackMinutes,
            graceMinutes,
            maxGraphHops,
            maxHypotheses,
          },
        )

      setAnalysis(result)

      setSelectedAnalysisId(
        result.analysis_id,
      )

      setSelectedHypothesisId(
        result.hypotheses[0]
          ?.hypothesis_id ?? "",
      )

      const refreshed =
        await listIncidentAnalyses({
          limit: 100,
        })

      setAnalyses(refreshed)
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setAnalyzing(false)
    }
  }


  return (
    <div className="mx-auto w-full max-w-[1750px] space-y-6 p-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
            evidence-based incident analysis
          </p>

          <h2 className="font-heading text-4xl font-black tracking-tight">
            Incident workspace
          </h2>

          <p className="mt-2 max-w-3xl leading-relaxed text-muted-foreground">
            Rank infrastructure changes that
            may explain a failure using temporal,
            topological and categorical evidence.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-sm border border-ok/30 bg-ok/10 px-3 py-2 font-mono text-xs text-ok">
          <CheckCircle2 className="h-4 w-4" />
          deterministic analysis
        </div>
      </header>


      <section className="rounded-md border border-border bg-card p-5">
        <div className="grid gap-4 xl:grid-cols-[minmax(300px,1fr)_180px_150px_150px_150px_auto]">
          <label>
            <FieldLabel>
              Failure signal
            </FieldLabel>

            <select
              value={selectedSignalId}
              onChange={(event) => {
                setSelectedSignalId(
                  event.target.value,
                )

                setAnalysis(null)
                setSelectedAnalysisId("")
              }}
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
            >
              <option value="">
                Select a signal
              </option>

              {signals.map((signal) => (
                <option
                  key={signal.signal_id}
                  value={signal.signal_id}
                >
                  {signal.severity.toUpperCase()}
                  {" — "}
                  {signal.reason ??
                    signal.title}
                  {" — "}
                  {signal.namespace ??
                    "cluster"}
                  {" — "}
                  {signal.involved_object_name ??
                    "unknown"}
                </option>
              ))}
            </select>
          </label>

          <NumberField
            label="Lookback min"
            value={lookbackMinutes}
            min={5}
            max={1440}
            onChange={setLookbackMinutes}
          />

          <NumberField
            label="Grace min"
            value={graceMinutes}
            min={0}
            max={30}
            onChange={setGraceMinutes}
          />

          <NumberField
            label="Max hops"
            value={maxGraphHops}
            min={1}
            max={20}
            onChange={setMaxGraphHops}
          />

          <NumberField
            label="Hypotheses"
            value={maxHypotheses}
            min={1}
            max={50}
            onChange={setMaxHypotheses}
          />

          <Button
            className="self-end"
            disabled={
              analyzing ||
              !selectedSignalId
            }
            onClick={() =>
              void handleAnalyze()
            }
          >
            {analyzing ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <Sparkles />
            )}

            {analyzing
              ? "Analyzing"
              : "Analyze"}
          </Button>
        </div>
      </section>


      {analyses.length > 0 && (
        <section className="rounded-md border border-border bg-card p-5">
          <label>
            <FieldLabel>
              Previous analysis
            </FieldLabel>

            <div className="mt-2 flex gap-3">
              <select
                value={selectedAnalysisId}
                onChange={(event) =>
                  void loadAnalysis(
                    event.target.value,
                  )
                }
                className="h-10 min-w-0 flex-1 rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
              >
                <option value="">
                  Select stored analysis
                </option>

                {analyses.map((item) => (
                  <option
                    key={item.analysis_id}
                    value={item.analysis_id}
                  >
                    {new Date(
                      item.generated_at,
                    ).toLocaleString()}
                    {" — "}
                    {item.incident_title}
                    {" — "}
                    {formatScore(
                      item
                        .top_hypothesis_score,
                    )}
                  </option>
                ))}
              </select>

              <Button
                variant="outline"
                onClick={() =>
                  void loadWorkspace()
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
          </label>
        </section>
      )}


      {error && (
        <div className="flex items-start gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}


      {loading && (
        <LoadingPanel text="Loading incident evidence…" />
      )}
      <IncidentInbox
  selectedIncidentId={selectedIncidentId}
  onSelectIncident={setSelectedIncidentId}
  onOpenAnalysis={openAnalysisFromIncident}
/>

      {!loading &&
        !analysis &&
        selectedSignal && (
          <section className="rounded-md border border-dashed border-border p-10 text-center">
            <ShieldAlert className="mx-auto h-8 w-8 text-warn" />

            <h3 className="mt-4 font-heading text-xl font-bold">
              Ready to analyze
            </h3>

            <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
              Selected signal:{" "}
              {selectedSignal.reason ??
                selectedSignal.title}
              . Run the deterministic analysis to
              rank related changes.
            </p>
          </section>
        )}


{analysis && !loading && (
  <div
    id="incident-analysis-panel"
    className="space-y-6"
  >
    <IncidentSummary
      analysis={analysis}
    />

          <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-5">
            <Metric
              label="CANDIDATES"
              value={
                analysis.candidate_count
              }
            />

            <Metric
              label="HYPOTHESES"
              value={
                analysis.hypotheses.length
              }
            />

            <Metric
              label="LOOKBACK"
              value={`${analysis.lookback_minutes}m`}
            />

            <Metric
              label="MAX HOPS"
              value={
                analysis.max_graph_hops
              }
            />

            <Metric
              label="TOP SCORE"
              value={
                analysis.hypotheses[0]
                  ? `${Math.round(
                      analysis
                        .hypotheses[0]
                        .score * 100,
                    )}%`
                  : "—"
              }
              className="text-ok"
            />
          </section>


          <div className="grid min-h-[720px] gap-6 xl:grid-cols-[minmax(0,1fr)_500px]">
            <section className="overflow-hidden rounded-md border border-border bg-card">
              <header className="flex items-center justify-between border-b border-border px-5 py-4">
                <div className="flex items-center gap-2">
                  <FileSearch className="h-4 w-4 text-info" />

                  <h3 className="font-heading text-lg font-bold">
                    Ranked hypotheses
                  </h3>
                </div>

                <span className="font-mono text-[11px] text-muted-foreground">
                  not a proven root cause
                </span>
              </header>

              {analysis.hypotheses.length ===
              0 ? (
                <EmptyPanel text="No candidate changes were found inside the configured analysis window." />
              ) : (
                <div className="divide-y divide-border">
                  {analysis.hypotheses.map(
                    (hypothesis) => (
                      <HypothesisRow
                        key={
                          hypothesis
                            .hypothesis_id
                        }
                        hypothesis={
                          hypothesis
                        }
                        selected={
                          selectedHypothesis
                            ?.hypothesis_id ===
                          hypothesis
                            .hypothesis_id
                        }
                        onSelect={() =>
                          setSelectedHypothesisId(
                            hypothesis
                              .hypothesis_id,
                          )
                        }
                      />
                    ),
                  )}
                </div>
              )}
            </section>


            <aside className="rounded-md border border-border bg-card">
              <header className="border-b border-border px-5 py-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  hypothesis evidence
                </p>

                <h3 className="mt-1 font-heading text-lg font-bold">
                  Why this candidate?
                </h3>
              </header>

              {selectedHypothesis ? (
                <HypothesisDetail
                  analysis={analysis}
                  hypothesis={
                    selectedHypothesis
                  }
                />
              ) : (
                <EmptyPanel text="Select a hypothesis to inspect its evidence." />
              )}
            </aside>
          </div>
          <IncidentRecommendations
             analysis={analysis}
           />

          {analysis.warnings.length > 0 && (
            <section className="rounded-md border border-warn/30 bg-warn/5 p-5">
              <p className="font-mono text-[10px] uppercase tracking-widest text-warn">
                Analysis warnings
              </p>

              <ul className="mt-3 space-y-2 font-mono text-xs text-muted-foreground">
                {analysis.warnings.map(
                  (warning, index) => (
                    <li
                      key={`${warning}-${index}`}
                    >
                      • {warning}
                    </li>
                  ),
                )}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  )
}


function IncidentSummary({
  analysis,
}: {
  analysis: IncidentAnalysis
}) {
  const symptomTopologyUrl =
    analysis.symptom_entity_id
      ? `/app/topology?snapshot_id=${encodeURIComponent(
          analysis.topology_snapshot_id,
        )}&entity_id=${encodeURIComponent(
          analysis.symptom_entity_id,
        )}`
      : null

  return (
    <section className="rounded-md border border-danger/30 bg-danger/5 p-5">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-danger">
            observed symptom
          </p>

          <h3 className="mt-2 font-heading text-2xl font-bold">
            {analysis.incident_title}
          </h3>

          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            {analysis.symptom_summary}
          </p>

          <p className="mt-3 font-mono text-[10px] text-muted-foreground">
            {analysis.cluster_name}
            {" / "}
            {analysis.namespace ??
              "cluster"}
            {" · first observed "}
            {formatDate(
              analysis
                .signal_first_observed_at,
            )}
          </p>
        </div>

        {symptomTopologyUrl && (
          <Link
            href={symptomTopologyUrl}
            className={cn(
              buttonVariants({
                variant: "outline",
              }),
            )}
          >
            <Server />
            Open symptom entity
            <ExternalLink />
          </Link>
        )}
      </div>
    </section>
  )
}


function HypothesisRow({
  hypothesis,
  selected,
  onSelect,
}: {
  hypothesis: RootCauseHypothesis
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "grid w-full gap-4 px-5 py-5 text-left transition-colors lg:grid-cols-[70px_minmax(0,1fr)_130px_30px]",
        selected
          ? "bg-info/10"
          : "hover:bg-secondary/40",
      )}
    >
      <div>
        <p className="font-heading text-3xl font-black">
          #{hypothesis.rank}
        </p>

        <p
          className={cn(
            "mt-2 font-mono text-sm font-bold",
            scoreColor(
              hypothesis.score,
            ),
          )}
        >
          {Math.round(
            hypothesis.score * 100,
          )}
          %
        </p>
      </div>

      <div className="min-w-0">
        <h4 className="font-heading text-lg font-bold">
          {hypothesis.title}
        </h4>

        <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
          {hypothesis.explanation}
        </p>

        <div className="mt-3 flex flex-wrap gap-2 font-mono text-[9px] uppercase">
          <Tag>
            {hypothesis.category}
          </Tag>

          <Tag>
            {hypothesis.importance}
          </Tag>

          <Tag>
            {hypothesis.change_type}
          </Tag>

          {hypothesis
            .changed_entity_kind && (
            <Tag>
              {
                hypothesis
                  .changed_entity_kind
              }
              /
              {
                hypothesis
                  .changed_entity_name
              }
            </Tag>
          )}
        </div>
      </div>

      <div className="font-mono text-[10px] text-muted-foreground">
        <p>
          time:{" "}
          {formatMinutes(
            hypothesis
              .minutes_before_signal,
          )}
        </p>

        <p className="mt-2">
          graph:{" "}
          {hypothesis.graph_distance ===
          null
            ? "no path"
            : `${hypothesis.graph_distance} hops`}
        </p>

        <p className="mt-2 text-ok">
          {
            hypothesis
              .supporting_evidence
              .length
          }{" "}
          supporting
        </p>

        <p className="mt-1 text-danger">
          {
            hypothesis
              .counter_evidence
              .length
          }{" "}
          counter
        </p>
      </div>

      <ChevronRight className="mt-2 h-4 w-4 text-muted-foreground" />
    </button>
  )
}


function HypothesisDetail({
  analysis,
  hypothesis,
}: {
  analysis: IncidentAnalysis
  hypothesis: RootCauseHypothesis
}) {
  const changedTopologyUrl =
    hypothesis.changed_entity_id
      ? `/app/topology?snapshot_id=${encodeURIComponent(
          analysis.topology_snapshot_id,
        )}&entity_id=${encodeURIComponent(
          hypothesis.changed_entity_id,
        )}`
      : null

  const affectedTopologyUrl =
    hypothesis.affected_entity_id
      ? `/app/topology?snapshot_id=${encodeURIComponent(
          analysis.topology_snapshot_id,
        )}&entity_id=${encodeURIComponent(
          hypothesis.affected_entity_id,
        )}`
      : null

  const changeTimelineUrl =
    `/app/signals?change_id=${encodeURIComponent(
      hypothesis.change_id,
    )}`

  return (
    <div className="space-y-5 p-5">
      <div>
        <div className="flex items-center justify-between gap-4">
          <span
            className={cn(
              "font-heading text-4xl font-black",
              scoreColor(
                hypothesis.score,
              ),
            )}
          >
            {Math.round(
              hypothesis.score * 100,
            )}
            %
          </span>

          <span className="rounded-sm border border-border bg-background px-2 py-1 font-mono text-[10px] uppercase text-muted-foreground">
            hypothesis #{hypothesis.rank}
          </span>
        </div>

        <h4 className="mt-4 font-heading text-xl font-bold">
          {hypothesis.title}
        </h4>

        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {hypothesis.explanation}
        </p>
      </div>


      <div className="grid gap-2 sm:grid-cols-2">
        {changedTopologyUrl && (
          <Link
            href={changedTopologyUrl}
            className={cn(
              buttonVariants({
                variant: "outline",
              }),
              "w-full",
            )}
          >
            <GitCompareArrows />
            Changed entity
          </Link>
        )}

        {affectedTopologyUrl && (
          <Link
            href={affectedTopologyUrl}
            className={cn(
              buttonVariants({
                variant: "outline",
              }),
              "w-full",
            )}
          >
            <Server />
            Affected entity
          </Link>
        )}

        <Link
          href={changeTimelineUrl}
          className={cn(
            buttonVariants({
              variant: "outline",
            }),
            "w-full sm:col-span-2",
          )}
        >
          <ArrowRight />
          Open change record
          <ExternalLink />
        </Link>
      </div>


      <DetailSection title="Candidate">
        <DetailRow
          label="change ID"
          value={hypothesis.change_id}
        />

        <DetailRow
          label="category"
          value={hypothesis.category}
        />

        <DetailRow
          label="importance"
          value={
            hypothesis.importance
          }
        />

        <DetailRow
          label="detected"
          value={formatDate(
            hypothesis
              .change_detected_at,
          )}
        />

        <DetailRow
          label="time"
          value={formatMinutes(
            hypothesis
              .minutes_before_signal,
          )}
        />

        <DetailRow
          label="distance"
          value={
            hypothesis.graph_distance ===
            null
              ? "No graph path"
              : `${hypothesis.graph_distance} hops`
          }
        />
      </DetailSection>


      <DetailSection title="Scoring components">
        <ScoringBreakdown
          components={
            hypothesis
              .scoring_components
          }
        />
      </DetailSection>


      <DetailSection title="Supporting evidence">
        <EvidenceList
          evidence={
            hypothesis
              .supporting_evidence
          }
          emptyText="No explicit supporting evidence."
        />
      </DetailSection>


      <DetailSection title="Counter-evidence">
        <EvidenceList
          evidence={
            hypothesis
              .counter_evidence
          }
          emptyText="No counter-evidence was identified."
        />
      </DetailSection>
    </div>
  )
}


function ScoringBreakdown({
  components,
}: {
  components: Record<string, number>
}) {
  return (
    <div className="space-y-3">
      {Object.entries(components).map(
        ([name, value]) => {
          const percentage = Math.min(
            Math.abs(value) * 100,
            100,
          )

          return (
            <div key={name}>
              <div className="flex justify-between gap-3 font-mono text-[10px]">
                <span className="text-muted-foreground">
                  {name}
                </span>

                <span
                  className={
                    name ===
                    "counter_penalty"
                      ? "text-danger"
                      : "text-foreground"
                  }
                >
                  {value.toFixed(3)}
                </span>
              </div>

              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-secondary">
                <div
                  className={
                    name ===
                    "counter_penalty"
                      ? "h-full bg-danger"
                      : "h-full bg-info"
                  }
                  style={{
                    width: `${percentage}%`,
                  }}
                />
              </div>
            </div>
          )
        },
      )}
    </div>
  )
}


function EvidenceList({
  evidence,
  emptyText,
}: {
  evidence: IncidentEvidence[]
  emptyText: string
}) {
  if (evidence.length === 0) {
    return (
      <p className="font-mono text-xs text-muted-foreground">
        {emptyText}
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {evidence.map((item) => (
        <article
          key={item.evidence_id}
          className={cn(
            "rounded-sm border p-3",
            item.direction ===
            "supporting"
              ? "border-ok/30 bg-ok/5"
              : "border-danger/30 bg-danger/5",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <CircleDot
                className={
                  item.direction ===
                  "supporting"
                    ? "h-3.5 w-3.5 text-ok"
                    : "h-3.5 w-3.5 text-danger"
                }
              />

              <p className="font-mono text-[10px] uppercase text-muted-foreground">
                {item.code}
              </p>
            </div>

            <span
              className={
                item.weight >= 0
                  ? "font-mono text-xs text-ok"
                  : "font-mono text-xs text-danger"
              }
            >
              {item.weight > 0
                ? "+"
                : ""}
              {item.weight.toFixed(3)}
            </span>
          </div>

          <p className="mt-2 text-sm leading-relaxed text-foreground">
            {item.summary}
          </p>

          <p className="mt-2 break-all font-mono text-[9px] text-muted-foreground">
            {item.source_type}
            {" · "}
            {item.source_id}
          </p>
        </article>
      ))}
    </div>
  )
}


function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  onChange: (value: number) => void
}) {
  return (
    <label>
      <FieldLabel>
        {label}
      </FieldLabel>

      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(event) =>
          onChange(
            Number(event.target.value),
          )
        }
        className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
      />
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
        className={`mt-1 truncate font-heading text-2xl font-bold ${className}`}
      >
        {value}
      </p>
    </div>
  )
}


function Tag({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <span className="rounded-sm border border-border bg-background px-2 py-1 text-muted-foreground">
      {children}
    </span>
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
    <section className="border-t border-border pt-4">
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
    <div className="grid grid-cols-[95px_1fr] gap-3 py-1.5 font-mono text-[10px]">
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
    <div className="flex items-center gap-2 rounded-md border border-border bg-card p-6 font-mono text-xs text-muted-foreground">
      <LoaderCircle className="h-4 w-4 animate-spin" />
      {text}
    </div>
  )
}


function EmptyPanel({
  text,
}: {
  text: string
}) {
  return (
    <div className="p-10 text-center font-mono text-xs text-muted-foreground">
      {text}
    </div>
  )
}


function scoreColor(
  score: number,
): string {
  if (score >= 0.8) {
    return "text-ok"
  }

  if (score >= 0.6) {
    return "text-warn"
  }

  return "text-muted-foreground"
}


function formatMinutes(
  value: number,
): string {
  if (value >= 0) {
    return `${value.toFixed(1)}m before`
  }

  return `${Math.abs(value).toFixed(1)}m after`
}


function formatScore(
  value: number | null,
): string {
  return value === null
    ? "no hypothesis"
    : `${Math.round(value * 100)}%`
}


function formatDate(
  value: string,
): string {
  const date = new Date(value)

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString()
}


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : "An unexpected request error occurred."
}