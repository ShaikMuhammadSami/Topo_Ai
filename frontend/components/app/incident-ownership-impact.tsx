"use client"

import {
  useEffect,
  useState,
} from "react"
import {
  AlertCircle,
  Building2,
  ExternalLink,
  LoaderCircle,
  Radio,
  Users,
} from "lucide-react"

import {
  getIncidentOwnershipImpact,
} from "@/lib/topo-api"
import type {
  IncidentOwnershipImpact,
} from "@/lib/topo-types"


export function IncidentOwnershipImpactPanel({
  incidentId,
}: {
  incidentId: string
}) {
  const [impact, setImpact] =
    useState<
      IncidentOwnershipImpact | null
    >(null)

  const [loading, setLoading] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)


  useEffect(() => {
    if (!incidentId) {
      setImpact(null)
      return
    }

    let cancelled = false

    async function loadImpact() {
      setLoading(true)
      setError(null)

      try {
        const value =
          await getIncidentOwnershipImpact(
            incidentId,
          )

        if (!cancelled) {
          setImpact(value)
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load ownership impact.",
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadImpact()

    return () => {
      cancelled = true
    }
  }, [incidentId])


  if (loading && !impact) {
    return (
      <section className="rounded-md border border-border bg-background p-5">
        <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Resolving service ownership…
        </div>
      </section>
    )
  }


  if (error) {
    return (
      <section className="rounded-md border border-danger/40 bg-danger/10 p-5 text-danger">
        <div className="flex gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      </section>
    )
  }


  if (!impact) {
    return null
  }


  return (
    <section className="overflow-hidden rounded-md border border-border bg-background">
      <header className="border-b border-border px-5 py-4">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          ownership and business impact
        </p>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-4">
          <h4 className="font-heading text-lg font-bold">
            Incident routing
          </h4>

          <span className="rounded-sm border border-current px-2 py-1 font-mono text-[10px] uppercase">
            {impact.business_impact_level}
          </span>
        </div>
      </header>


      <div className="grid grid-cols-2 gap-px bg-border lg:grid-cols-4">
        <Metric
          label="TEAMS"
          value={
            impact.affected_team_count
          }
        />

        <Metric
          label="CAPABILITIES"
          value={
            impact
              .affected_capability_count
          }
        />

        <Metric
          label="RESOLVED"
          value={
            impact
              .resolved_entity_count
          }
        />

        <Metric
          label="UNRESOLVED"
          value={
            impact
              .unresolved_entity_count
          }
        />
      </div>


      <div className="space-y-5 p-5">
        <div className="rounded-md border border-border bg-card p-4">
          <div className="flex items-start gap-3">
            <Radio className="mt-0.5 h-4 w-4 text-info" />

            <div>
              <p className="font-mono text-[10px] uppercase text-muted-foreground">
                recommended routing
              </p>

              <p className="mt-1 text-sm">
                {
                  impact
                    .routing_recommendation
                }
              </p>
            </div>
          </div>
        </div>


        <div className="grid gap-4 lg:grid-cols-2">
          <InfoGroup
            icon={Users}
            title="Owning teams"
            values={impact.owner_teams}
            empty="No owning team resolved."
          />

          <InfoGroup
            icon={Building2}
            title="Business capabilities"
            values={
              impact
                .business_capabilities
            }
            empty="No business capability resolved."
          />
        </div>


        {impact.oncall_contacts.length >
          0 && (
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              On-call contacts
            </p>

            <div className="mt-2 flex flex-wrap gap-2">
              {impact.oncall_contacts.map(
                (contact) => (
                  <span
                    key={contact}
                    className="rounded-sm border border-border bg-card px-3 py-2 font-mono text-xs"
                  >
                    {contact}
                  </span>
                ),
              )}
            </div>
          </div>
        )}


        {impact.repositories.length >
          0 && (
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Repositories
            </p>

            <div className="mt-2 space-y-2">
              {impact.repositories.map(
                (repository) => (
                  <a
                    key={repository}
                    href={repository}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-2 font-mono text-xs text-info hover:underline"
                  >
                    {repository}

                    <ExternalLink className="h-3 w-3" />
                  </a>
                ),
              )}
            </div>
          </div>
        )}


        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Affected entity ownership
          </p>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border font-mono text-muted-foreground">
                <tr>
                  <th className="p-3">
                    Entity
                  </th>
                  <th className="p-3">
                    Impact
                  </th>
                  <th className="p-3">
                    Service
                  </th>
                  <th className="p-3">
                    Team
                  </th>
                  <th className="p-3">
                    Tier
                  </th>
                </tr>
              </thead>

              <tbody>
                {impact
                  .affected_entities
                  .map((item) => (
                    <tr
                      key={item.entity_id}
                      className="border-b border-border last:border-0"
                    >
                      <td className="p-3">
                        <p className="font-semibold">
                          {item.entity_name}
                        </p>

                        <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                          {item.entity_kind}
                        </p>
                      </td>

                      <td className="p-3">
                        {item.impact}
                      </td>

                      <td className="p-3 font-mono">
                        {item.ownership
                          .service_name ??
                          "—"}
                      </td>

                      <td className="p-3">
                        {item.ownership
                          .owner_team ??
                          "Unresolved"}
                      </td>

                      <td className="p-3 font-mono">
                        {item.ownership
                          .criticality ??
                          "—"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
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


function InfoGroup({
  icon: Icon,
  title,
  values,
  empty,
}: {
  icon: typeof Users
  title: string
  values: string[]
  empty: string
}) {
  return (
    <div className="rounded-md border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-info" />

        <p className="font-heading font-bold">
          {title}
        </p>
      </div>

      {values.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {values.map((value) => (
            <span
              key={value}
              className="rounded-sm border border-border px-2 py-1 font-mono text-xs"
            >
              {value}
            </span>
          ))}
        </div>
      ) : (
        <p className="mt-3 font-mono text-xs text-muted-foreground">
          {empty}
        </p>
      )}
    </div>
  )
}