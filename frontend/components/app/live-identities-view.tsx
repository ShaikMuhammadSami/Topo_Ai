"use client"

import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  AlertCircle,
  Ban,
  CheckCircle2,
  Fingerprint,
  Link2,
  LoaderCircle,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  createIdentityOverride,
  deactivateIdentityOverride,
  getSnapshot,
  getStoredIdentities,
  listIdentityOverrides,
  listSnapshots,
  materializeIdentities,
} from "@/lib/topo-api"
import type {
  GraphSnapshot,
  IdentityOverrideAction,
  IdentityOverrideView,
  IdentityResolutionResult,
  LogicalIdentity,
  SnapshotSummary,
  TopologyEntity,
} from "@/lib/topo-types"

const resolvableKinds = new Set([
  "KubernetesDeployment",
  "KubernetesReplicaSet",
  "KubernetesPod",
  "KubernetesService",
])

export function LiveIdentitiesView() {
  const [snapshots, setSnapshots] =
    useState<SnapshotSummary[]>([])

  const [
    selectedSnapshotId,
    setSelectedSnapshotId,
  ] = useState("")

  const [snapshot, setSnapshot] =
    useState<GraphSnapshot | null>(null)

  const [resolution, setResolution] =
    useState<IdentityResolutionResult | null>(
      null,
    )

  const [overrides, setOverrides] =
    useState<IdentityOverrideView[]>([])

  const [selectedEntityId, setSelectedEntityId] =
    useState("")

  const [action, setAction] =
    useState<IdentityOverrideAction>("assign")

  const [canonicalName, setCanonicalName] =
    useState("")

  const [reason, setReason] =
    useState("")

  const [loading, setLoading] =
    useState(true)

  const [materializing, setMaterializing] =
    useState(false)

  const [savingOverride, setSavingOverride] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)

  async function loadSnapshotList() {
    setLoading(true)
    setError(null)

    try {
      const results =
        await listSnapshots(100)

      setSnapshots(results)

      if (
        !selectedSnapshotId &&
        results[0]
      ) {
        setSelectedSnapshotId(
          results[0].snapshot_id,
        )
      }
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  async function refreshIdentityData(
    snapshotId: string,
  ) {
    if (!snapshotId) {
      setSnapshot(null)
      setResolution(null)
      setOverrides([])
      return
    }

    setMaterializing(true)
    setError(null)

    try {
      const loadedSnapshot =
        await getSnapshot(snapshotId)

      setSnapshot(loadedSnapshot)

      /*
       * Materialize every time so the page reflects
       * current automatic logic and active overrides.
       */
      await materializeIdentities(snapshotId)

      const storedResult =
        await getStoredIdentities(snapshotId)

      setResolution(storedResult)

      const clusterName =
        loadedSnapshot.scope.cluster

      const namespace =
        normalizeNamespace(
          loadedSnapshot.scope.namespace,
        )

      const activeOverrides =
        await listIdentityOverrides({
          clusterName,
          namespace,
          activeOnly: true,
        })

      setOverrides(activeOverrides)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setMaterializing(false)
    }
  }

  useEffect(() => {
    void loadSnapshotList()
  }, [])

  useEffect(() => {
    if (selectedSnapshotId) {
      void refreshIdentityData(
        selectedSnapshotId,
      )
    }
  }, [selectedSnapshotId])

  const entitiesById = useMemo(
    () =>
      new Map(
        (snapshot?.entities ?? []).map(
          (entity) => [
            entity.id,
            entity,
          ],
        ),
      ),
    [snapshot],
  )

  const resolvableEntities = useMemo(
    () =>
      (snapshot?.entities ?? [])
        .filter((entity) =>
          resolvableKinds.has(entity.kind),
        )
        .sort((first, second) => {
          const namespaceComparison =
            entityNamespace(first)
              .localeCompare(
                entityNamespace(second),
              )

          if (namespaceComparison !== 0) {
            return namespaceComparison
          }

          const kindComparison =
            first.kind.localeCompare(
              second.kind,
            )

          if (kindComparison !== 0) {
            return kindComparison
          }

          return first.name.localeCompare(
            second.name,
          )
        }),
    [snapshot],
  )

  const unresolvedEntities = useMemo(
    () =>
      (
        resolution
          ?.unresolved_entity_ids ?? []
      )
        .map((entityId) =>
          entitiesById.get(entityId),
        )
        .filter(
          (
            entity,
          ): entity is TopologyEntity =>
            Boolean(entity),
        ),
    [resolution, entitiesById],
  )

  const excludedEntities = useMemo(
    () =>
      (
        resolution
          ?.excluded_entity_ids ?? []
      )
        .map((entityId) =>
          entitiesById.get(entityId),
        )
        .filter(
          (
            entity,
          ): entity is TopologyEntity =>
            Boolean(entity),
        ),
    [resolution, entitiesById],
  )

  const selectedEntity =
    entitiesById.get(selectedEntityId) ??
    null

  async function handleCreateOverride() {
    if (!snapshot || !selectedEntity) {
      setError(
        "Select a resource before saving an override.",
      )
      return
    }

    if (
      action === "assign" &&
      !canonicalName.trim()
    ) {
      setError(
        "Canonical name is required for an assignment override.",
      )
      return
    }

    if (reason.trim().length < 3) {
      setError(
        "Provide a short reason for this override.",
      )
      return
    }

    const clusterName =
      entityCluster(selectedEntity) ||
      snapshot.scope.cluster

    const namespace =
      entityNamespace(selectedEntity)

    if (!clusterName || !namespace) {
      setError(
        "The selected resource is missing cluster or namespace information.",
      )
      return
    }

    setSavingOverride(true)
    setError(null)

    try {
      await createIdentityOverride({
        cluster_name: clusterName,
        namespace,
        entity_kind:
          selectedEntity.kind,
        entity_name:
          selectedEntity.name,
        action,
        canonical_name:
          action === "assign"
            ? canonicalName.trim()
            : null,
        reason: reason.trim(),
      })

      setReason("")
      setSelectedEntityId("")

      if (action === "exclude") {
        setCanonicalName("")
      }

      await refreshIdentityData(
        selectedSnapshotId,
      )
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSavingOverride(false)
    }
  }

  async function handleDeactivateOverride(
    overrideId: string,
  ) {
    setError(null)

    try {
      await deactivateIdentityOverride(
        overrideId,
      )

      await refreshIdentityData(
        selectedSnapshotId,
      )
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-6 p-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
            persisted identity resolution
          </p>

          <h2 className="font-heading text-4xl font-black tracking-tight">
            Logical application identities
          </h2>

          <p className="mt-2 max-w-3xl leading-relaxed text-muted-foreground">
            Group Kubernetes Deployments,
            ReplicaSets, Pods, Services and
            image references into logical
            applications using evidence and
            confidence-scored mappings.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-sm border border-ok/30 bg-ok/10 px-3 py-2 font-mono text-xs text-ok">
          <ShieldCheck className="h-4 w-4" />
          real backend identities
        </div>
      </header>

      <section className="rounded-md border border-border bg-card p-5">
        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
          <label>
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Topology snapshot
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
            disabled={
              !selectedSnapshotId ||
              materializing
            }
            onClick={() =>
              void refreshIdentityData(
                selectedSnapshotId,
              )
            }
          >
            {materializing ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <RefreshCw />
            )}

            Re-materialize
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

      {(loading || materializing) && (
        <div className="flex items-center gap-2 rounded-md border border-border bg-card p-5 font-mono text-xs text-muted-foreground">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Resolving logical identities…
        </div>
      )}

      {resolution &&
        !materializing && (
          <>
            <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-5">
              <Metric
                label="IDENTITIES"
                value={
                  resolution.identities.length
                }
              />

              <Metric
                label="MEMBERS"
                value={resolution.identities.reduce(
                  (total, identity) =>
                    total +
                    identity.members.length,
                  0,
                )}
              />

              <Metric
                label="UNRESOLVED"
                value={
                  resolution
                    .unresolved_entity_ids
                    .length
                }
                className="text-warn"
              />

              <Metric
                label="EXCLUDED"
                value={
                  resolution
                    .excluded_entity_ids
                    .length
                }
                className="text-danger"
              />

              <Metric
                label="OVERRIDES"
                value={overrides.length}
                className="text-info"
              />
            </section>

            <section className="grid gap-5 xl:grid-cols-2">
              {resolution.identities.map(
                (identity) => (
                  <IdentityCard
                    key={
                      identity.identity_id
                    }
                    identity={identity}
                  />
                ),
              )}

              {resolution.identities.length ===
                0 && (
                <EmptyPanel
                  text="No logical identities were resolved for this snapshot."
                />
              )}
            </section>

            <section className="grid gap-6 xl:grid-cols-2">
              <ResourceList
                title="Unresolved resources"
                description="Resources that could not be safely attached to a logical application."
                entities={
                  unresolvedEntities
                }
                tone="warn"
              />

              <ResourceList
                title="Manually excluded"
                description="Resources intentionally removed from logical identity resolution."
                entities={
                  excludedEntities
                }
                tone="danger"
              />
            </section>

            <OverrideForm
              entities={resolvableEntities}
              selectedEntityId={
                selectedEntityId
              }
              onSelectedEntityIdChange={
                setSelectedEntityId
              }
              action={action}
              onActionChange={setAction}
              canonicalName={
                canonicalName
              }
              onCanonicalNameChange={
                setCanonicalName
              }
              reason={reason}
              onReasonChange={setReason}
              identities={
                resolution.identities
              }
              saving={savingOverride}
              onSave={() =>
                void handleCreateOverride()
              }
            />

            <OverridesTable
              overrides={overrides}
              onDeactivate={(
                overrideId,
              ) =>
                void handleDeactivateOverride(
                  overrideId,
                )
              }
            />

            {resolution.warnings.length >
              0 && (
              <section className="rounded-md border border-warn/30 bg-warn/5 p-5">
                <p className="font-mono text-[10px] uppercase tracking-widest text-warn">
                  Resolution warnings
                </p>

                <ul className="mt-3 space-y-2 font-mono text-xs text-muted-foreground">
                  {resolution.warnings.map(
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
          </>
        )}
    </div>
  )
}

function IdentityCard({
  identity,
}: {
  identity: LogicalIdentity
}) {
  return (
    <article className="rounded-md border border-border bg-card">
      <header className="border-b border-border p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Fingerprint className="h-4 w-4 text-info" />

              <h3 className="font-heading text-xl font-bold">
                {identity.canonical_name}
              </h3>
            </div>

            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              {identity.cluster}
              {" / "}
              {identity.namespace}
            </p>
          </div>

          <ConfidenceBadge
            confidence={
              identity.confidence
            }
          />
        </div>

        {identity.image_references.length >
          0 && (
          <div className="mt-4 space-y-1">
            {identity.image_references.map(
              (image) => (
                <p
                  key={image}
                  className="break-all rounded-sm bg-background px-2 py-1 font-mono text-[10px] text-muted-foreground"
                >
                  {image}
                </p>
              ),
            )}
          </div>
        )}
      </header>

      <div className="divide-y divide-border">
        {identity.members.map(
          (member) => (
            <div
              key={member.entity_id}
              className="grid gap-2 px-5 py-3 md:grid-cols-[1fr_130px_140px_80px]"
            >
              <div className="min-w-0">
                <p className="truncate font-mono text-xs font-semibold">
                  {member.name}
                </p>

                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                  {member.kind}
                </p>
              </div>

              <p className="font-mono text-[10px] uppercase text-muted-foreground">
                {member.role}
              </p>

              <p
                className={
                  member.match_method ===
                  "manual_override"
                    ? "font-mono text-[10px] text-info"
                    : "font-mono text-[10px] text-muted-foreground"
                }
              >
                {member.match_method}
              </p>

              <p className="font-mono text-[11px] text-ok">
                {Math.round(
                  member.confidence *
                    100,
                )}
                %
              </p>
            </div>
          ),
        )}
      </div>

      {identity.warnings.length > 0 && (
        <footer className="border-t border-warn/20 bg-warn/5 px-5 py-3">
          {identity.warnings.map(
            (warning) => (
              <p
                key={warning}
                className="font-mono text-[10px] text-warn"
              >
                {warning}
              </p>
            ),
          )}
        </footer>
      )}
    </article>
  )
}

function OverrideForm({
  entities,
  selectedEntityId,
  onSelectedEntityIdChange,
  action,
  onActionChange,
  canonicalName,
  onCanonicalNameChange,
  reason,
  onReasonChange,
  identities,
  saving,
  onSave,
}: {
  entities: TopologyEntity[]
  selectedEntityId: string
  onSelectedEntityIdChange: (
    value: string,
  ) => void
  action: IdentityOverrideAction
  onActionChange: (
    value: IdentityOverrideAction,
  ) => void
  canonicalName: string
  onCanonicalNameChange: (
    value: string,
  ) => void
  reason: string
  onReasonChange: (
    value: string,
  ) => void
  identities: LogicalIdentity[]
  saving: boolean
  onSave: () => void
}) {
  return (
    <section className="rounded-md border border-info/30 bg-card p-5">
      <div className="flex items-center gap-2">
        <Link2 className="h-4 w-4 text-info" />

        <div>
          <h3 className="font-heading text-lg font-bold">
            Manual identity override
          </h3>

          <p className="mt-1 text-sm text-muted-foreground">
            Assign a resource to a logical
            application or exclude it from
            identity resolution.
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <label>
          <FieldLabel>
            Resource
          </FieldLabel>

          <select
            value={selectedEntityId}
            onChange={(event) =>
              onSelectedEntityIdChange(
                event.target.value,
              )
            }
            className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
          >
            <option value="">
              Select a resource
            </option>

            {entities.map((entity) => (
              <option
                key={entity.id}
                value={entity.id}
              >
                {entityNamespace(entity)}
                {" / "}
                {entity.kind}
                {" / "}
                {entity.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          <FieldLabel>
            Override action
          </FieldLabel>

          <select
            value={action}
            onChange={(event) =>
              onActionChange(
                event.target
                  .value as IdentityOverrideAction,
              )
            }
            className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
          >
            <option value="assign">
              Assign to identity
            </option>

            <option value="exclude">
              Exclude resource
            </option>
          </select>
        </label>

        {action === "assign" && (
          <label>
            <FieldLabel>
              Canonical application name
            </FieldLabel>

            <input
              value={canonicalName}
              onChange={(event) =>
                onCanonicalNameChange(
                  event.target.value,
                )
              }
              list="canonical-identities"
              placeholder="checkout-api"
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none placeholder:text-muted-foreground focus:border-info"
            />

            <datalist id="canonical-identities">
              {identities.map(
                (identity) => (
                  <option
                    key={
                      identity.identity_id
                    }
                    value={
                      identity.canonical_name
                    }
                  />
                ),
              )}
            </datalist>
          </label>
        )}

        <label
          className={
            action === "assign"
              ? ""
              : "lg:col-span-2"
          }
        >
          <FieldLabel>
            Reason
          </FieldLabel>

          <input
            value={reason}
            onChange={(event) =>
              onReasonChange(
                event.target.value,
              )
            }
            placeholder="Explain why this override is required"
            className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none placeholder:text-muted-foreground focus:border-info"
          />
        </label>
      </div>

      <div className="mt-5 flex justify-end">
        <Button
          onClick={onSave}
          disabled={
            saving ||
            !selectedEntityId
          }
        >
          {saving ? (
            <LoaderCircle className="animate-spin" />
          ) : action === "exclude" ? (
            <Ban />
          ) : (
            <Save />
          )}

          {saving
            ? "Saving"
            : "Save override"}
        </Button>
      </div>
    </section>
  )
}

function OverridesTable({
  overrides,
  onDeactivate,
}: {
  overrides: IdentityOverrideView[]
  onDeactivate: (
    overrideId: string,
  ) => void
}) {
  return (
    <section className="overflow-x-auto rounded-md border border-border bg-card">
      <header className="border-b border-border px-5 py-4">
        <h3 className="font-heading text-lg font-bold">
          Active overrides
        </h3>

        <p className="mt-1 text-sm text-muted-foreground">
          Overrides are applied every time
          identities are materialized.
        </p>
      </header>

      {overrides.length === 0 ? (
        <div className="p-8 text-center font-mono text-xs text-muted-foreground">
          No active overrides for this
          snapshot scope.
        </div>
      ) : (
        <table className="w-full min-w-[1000px] border-collapse">
          <thead>
            <tr className="border-b border-border font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              <TableHeader>
                Resource
              </TableHeader>
              <TableHeader>
                Action
              </TableHeader>
              <TableHeader>
                Canonical name
              </TableHeader>
              <TableHeader>
                Reason
              </TableHeader>
              <TableHeader>
                Updated
              </TableHeader>
              <TableHeader>
                Action
              </TableHeader>
            </tr>
          </thead>

          <tbody>
            {overrides.map(
              (override) => (
                <tr
                  key={
                    override.override_id
                  }
                  className="border-b border-border last:border-0"
                >
                  <TableCell>
                    <p className="font-mono text-xs font-semibold">
                      {override.entity_name}
                    </p>

                    <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                      {override.entity_kind}
                    </p>
                  </TableCell>

                  <TableCell>
                    <span
                      className={
                        override.action ===
                        "assign"
                          ? "font-mono text-xs text-info"
                          : "font-mono text-xs text-danger"
                      }
                    >
                      {override.action}
                    </span>
                  </TableCell>

                  <TableCell>
                    {override.canonical_name ??
                      "—"}
                  </TableCell>

                  <TableCell>
                    {override.reason}
                  </TableCell>

                  <TableCell>
                    {new Date(
                      override.updated_at,
                    ).toLocaleString()}
                  </TableCell>

                  <TableCell>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        onDeactivate(
                          override.override_id,
                        )
                      }
                    >
                      <Trash2 />
                      Deactivate
                    </Button>
                  </TableCell>
                </tr>
              ),
            )}
          </tbody>
        </table>
      )}
    </section>
  )
}

function ResourceList({
  title,
  description,
  entities,
  tone,
}: {
  title: string
  description: string
  entities: TopologyEntity[]
  tone: "warn" | "danger"
}) {
  return (
    <section className="rounded-md border border-border bg-card p-5">
      <h3 className="font-heading text-lg font-bold">
        {title}
      </h3>

      <p className="mt-1 text-sm text-muted-foreground">
        {description}
      </p>

      <div className="mt-4 space-y-2">
        {entities.map((entity) => (
          <div
            key={entity.id}
            className="rounded-sm border border-border bg-background px-3 py-2"
          >
            <p className="font-mono text-xs font-semibold">
              {entity.name}
            </p>

            <p
              className={
                tone === "warn"
                  ? "mt-1 font-mono text-[10px] text-warn"
                  : "mt-1 font-mono text-[10px] text-danger"
              }
            >
              {entity.kind}
            </p>
          </div>
        ))}

        {entities.length === 0 && (
          <p className="font-mono text-xs text-muted-foreground">
            None
          </p>
        )}
      </div>
    </section>
  )
}

function ConfidenceBadge({
  confidence,
}: {
  confidence: number
}) {
  return (
    <span className="rounded-sm border border-ok/30 bg-ok/10 px-2 py-1 font-mono text-[11px] text-ok">
      {Math.round(confidence * 100)}%
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
    <div className="bg-card px-5 py-4 text-center">
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

function EmptyPanel({
  text,
}: {
  text: string
}) {
  return (
    <div className="rounded-md border border-dashed border-border p-10 text-center font-mono text-xs text-muted-foreground">
      {text}
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
}: {
  children: React.ReactNode
}) {
  return (
    <td className="px-4 py-3 align-top font-mono text-[11px]">
      {children}
    </td>
  )
}

function entityNamespace(
  entity: TopologyEntity,
): string {
  const namespace =
    entity.properties.namespace

  return typeof namespace === "string"
    ? namespace
    : ""
}

function entityCluster(
  entity: TopologyEntity,
): string {
  const cluster =
    entity.properties.cluster

  return typeof cluster === "string"
    ? cluster
    : ""
}

function normalizeNamespace(
  namespace: string | undefined,
): string | undefined {
  if (
    !namespace ||
    namespace === "*"
  ) {
    return undefined
  }

  return namespace
}

function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : "An unexpected request error occurred."
}