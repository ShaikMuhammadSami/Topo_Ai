"use client"

import type {
  ReactNode,
} from "react"
import {
  useEffect,
  useState,
} from "react"
import {
  AlertCircle,
  BrainCircuit,
  LoaderCircle,
  RefreshCw,
  ShieldQuestion,
  Sparkles,
} from "lucide-react"

import {
  Button,
} from "@/components/ui/button"
import {
  generateIncidentExplanation,
  getLatestIncidentExplanation,
} from "@/lib/topo-api"
import type {
  IncidentExplanationResponse,
} from "@/lib/topo-types"


export function IncidentAiExplanation({
  incidentId,
}: {
  incidentId: string
}) {
  const [
    explanation,
    setExplanation,
  ] = useState<
    IncidentExplanationResponse | null
  >(null)

  const [loading, setLoading] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)


  useEffect(() => {
    if (!incidentId) {
      setExplanation(null)
      return
    }

    let cancelled = false

    async function loadLatest() {
      setLoading(true)
      setError(null)

      try {
        const result =
          await getLatestIncidentExplanation(
            incidentId,
          )

        if (!cancelled) {
          setExplanation(result)
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

    void loadLatest()

    return () => {
      cancelled = true
    }
  }, [incidentId])


  async function handleGenerate(
    forceRegenerate: boolean,
  ) {
    setLoading(true)
    setError(null)

    try {
      const result =
        await generateIncidentExplanation(
          incidentId,
          {
            provider: "auto",
            forceRegenerate,
          },
        )

      setExplanation(result)
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  return (
    <section className="overflow-hidden rounded-md border border-border bg-background">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            grounded intelligence
          </p>

          <div className="mt-2 flex items-center gap-2">
            <BrainCircuit className="h-5 w-5 text-info" />

            <h3 className="font-heading text-lg font-bold">
              AI incident explanation
            </h3>
          </div>
        </div>

        <Button
          variant="outline"
          disabled={loading}
          onClick={() =>
            void handleGenerate(
              Boolean(explanation),
            )
          }
        >
          {loading ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : explanation ? (
            <RefreshCw className="h-4 w-4" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}

          {explanation
            ? "Regenerate"
            : "Generate explanation"}
        </Button>
      </header>


      {error && (
        <div className="m-5 flex gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="h-5 w-5 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}


      {loading && !explanation && (
        <div className="flex items-center gap-2 p-5 font-mono text-xs text-muted-foreground">
          <LoaderCircle className="h-4 w-4 animate-spin" />

          Building grounded incident
          explanation…
        </div>
      )}


      {!loading &&
        !error &&
        !explanation && (
        <div className="p-5">
          <p className="text-sm text-muted-foreground">
            Generate an explanation from the
            current incident, deterministic RCA,
            blast radius, ownership, network and
            recovery evidence.
          </p>
        </div>
      )}


      {explanation && (
        <div className="space-y-6 p-5">
          <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase">
            <Badge>
              {explanation.provider}
            </Badge>

            <Badge>
              generated self-score {explanation.confidence.toFixed(2)} (uncalibrated)
            </Badge>

            {explanation.model_name && (
              <Badge>
                {explanation.model_name}
              </Badge>
            )}
          </div>


          <TextSection
            title="Executive summary"
            value={
              explanation.explanation
                .executive_summary
            }
          />

          <TextSection
            title="Technical explanation"
            value={
              explanation.explanation
                .technical_summary
            }
          />

          <TextSection
            title="Probable root cause"
            value={
              explanation.explanation
                .probable_root_cause
            }
          />

          <TextSection
            title="Business impact"
            value={
              explanation.explanation
                .business_impact
            }
          />


          <div>
            <SectionTitle>
              Recommended response
            </SectionTitle>

            <ol className="mt-3 space-y-3">
              {[
                ...explanation.explanation
                  .response_steps,
              ]
                .sort(
                  (first, second) =>
                    first.priority
                    - second.priority,
                )
                .map((step) => (
                  <li
                    key={`${step.priority}-${step.action}`}
                    className="rounded-md border border-border bg-card p-4"
                  >
                    <div className="flex gap-3">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border font-mono text-xs">
                        {step.priority}
                      </span>

                      <div>
                        <p className="font-semibold">
                          {step.action}
                        </p>

                        <p className="mt-1 text-xs leading-5 text-muted-foreground">
                          {step.rationale}
                        </p>

                        <EvidenceIds
                          values={
                            step.evidence_ids
                          }
                        />
                      </div>
                    </div>
                  </li>
                ))}
            </ol>
          </div>


          <div>
            <SectionTitle>
              Evidence timeline
            </SectionTitle>

            <div className="mt-3 space-y-4">
              {explanation.explanation
                .timeline
                .map((item, index) => (
                  <div
                    key={`${item.timestamp}-${index}`}
                    className="border-l-2 border-border pl-4"
                  >
                    <p className="font-mono text-[10px] text-muted-foreground">
                      {formatTimestamp(
                        item.timestamp,
                      )}
                    </p>

                    <p className="mt-1 text-sm">
                      {item.event}
                    </p>

                    <EvidenceIds
                      values={
                        item.evidence_ids
                      }
                    />
                  </div>
                ))}
            </div>
          </div>


          <div>
            <SectionTitle>
              Grounded claims
            </SectionTitle>

            <div className="mt-3 space-y-3">
              {explanation.explanation
                .claims
                .map((claim, index) => (
                  <div
                    key={`${claim.text}-${index}`}
                    className="rounded-md border border-border bg-card p-4"
                  >
                    <p className="text-sm">
                      {claim.text}
                    </p>

                    <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                      Generated claim self-score: {claim.confidence.toFixed(2)} (uncalibrated)
                    </p>

                    <EvidenceIds
                      values={
                        claim.evidence_ids
                      }
                    />
                  </div>
                ))}
            </div>
          </div>


          {explanation.explanation
            .uncertainty.length > 0 && (
            <div className="rounded-md border border-warn/40 bg-warn/10 p-4">
              <div className="flex items-center gap-2">
                <ShieldQuestion className="h-4 w-4 text-warn" />

                <SectionTitle>
                  Uncertainty
                </SectionTitle>
              </div>

              <ul className="mt-3 space-y-2 text-sm">
                {explanation.explanation
                  .uncertainty
                  .map((item) => (
                    <li key={item}>
                      • {item}
                    </li>
                  ))}
              </ul>
            </div>
          )}


          {explanation.warnings.length >
            0 && (
            <div>
              <SectionTitle>
                Generation warnings
              </SectionTitle>

              <ul className="mt-3 space-y-2 font-mono text-xs text-muted-foreground">
                {explanation.warnings.map(
                  (warning) => (
                    <li key={warning}>
                      • {warning}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}


function TextSection({
  title,
  value,
}: {
  title: string
  value: string
}) {
  return (
    <div>
      <SectionTitle>
        {title}
      </SectionTitle>

      <p className="mt-3 whitespace-pre-wrap text-sm leading-6">
        {value}
      </p>
    </div>
  )
}


function SectionTitle({
  children,
}: {
  children: ReactNode
}) {
  return (
    <h4 className="font-heading font-bold">
      {children}
    </h4>
  )
}


function Badge({
  children,
}: {
  children: ReactNode
}) {
  return (
    <span className="rounded-sm border border-border px-2 py-1">
      {children}
    </span>
  )
}


function EvidenceIds({
  values,
}: {
  values: string[]
}) {
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {values.map((value) => (
        <span
          key={value}
          title={value}
          className="max-w-[260px] truncate rounded-sm border border-border px-2 py-1 font-mono text-[9px] text-muted-foreground"
        >
          {value}
        </span>
      ))}
    </div>
  )
}


function formatTimestamp(
  value: string | null,
): string {
  if (!value) {
    return "Time unavailable"
  }

  const date = new Date(value)

  if (
    Number.isNaN(
      date.getTime(),
    )
  ) {
    return value
  }

  return date.toLocaleString()
}


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : (
        "Unable to generate the "
        + "incident explanation."
      )
}
