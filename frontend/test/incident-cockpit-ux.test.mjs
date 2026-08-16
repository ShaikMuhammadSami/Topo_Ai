import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import {
  filterIncidentHomeRecords,
  incidentNeedsAttention,
} from "../lib/incident-home.ts"
import {
  TECHNICAL_SECTION_ORDER,
  compactDependencyPath,
  incidentWorkspaceHref,
  isMutationControlLabel,
  partitionRemediationActions,
} from "../lib/incident-briefing.ts"

async function source(path) {
  return readFile(
    new URL(`../${path}`, import.meta.url),
    "utf8",
  )
}

const [
  appPageSource,
  homeSource,
  advancedSource,
  workspaceSource,
  technicalSource,
  responseSource,
  businessSource,
  sidebarSource,
  topologySource,
  packageSource,
] = await Promise.all([
  source("app/app/page.tsx"),
  source("components/app/incident-home.tsx"),
  source("components/app/live-incident-workspace.tsx"),
  source("components/app/incident-briefing-workspace.tsx"),
  source("components/app/incident-briefing-technical.tsx"),
  source("components/app/incident-briefing-response.tsx"),
  source("components/app/incident-briefing-business.tsx"),
  source("components/app/app-sidebar.tsx"),
  source("components/app/live-topology-view.tsx"),
  source("package.json"),
])

const cockpitSource = [
  workspaceSource,
  technicalSource,
  responseSource,
  businessSource,
].join("\n")

function incident(overrides = {}) {
  return {
    incident_id: "incident:checkout/1",
    status: "open",
    severity: "critical",
    title: "Checkout degradation",
    cluster_name: "production",
    namespace: "payments",
    affected_object_kind: "KubernetesService",
    affected_object_name: "checkout-api",
    first_observed_at: "2026-08-16T10:00:00Z",
    last_observed_at: "2026-08-16T10:05:00Z",
    top_hypothesis_title: "payment-api revision 42",
    top_hypothesis_score: 0.87,
    recommendation_count: 2,
    recovery_status: null,
    occurrence_count: 3,
    ...overrides,
  }
}

function action(rank) {
  return {
    action_id: `action:${rank}`,
    rank,
  }
}

test("/app defaults to incident discovery", () => {
  assert.match(appPageSource, /<IncidentHome \/>/)
  assert.match(homeSource, /What needs attention\?/)
  assert.doesNotMatch(homeSource, /Lookback min|Max hops|Hypotheses/)
})

test("advanced custom analysis remains directly accessible", () => {
  assert.match(homeSource, /Run custom analysis/)
  assert.match(homeSource, /\/app\?mode=advanced#custom-analysis/)
  assert.match(appPageSource, /<LiveIncidentWorkspace \/>/)
  assert.match(advancedSource, /id="custom-analysis"/)
})

test("stored analysis history remains accessible", () => {
  assert.match(homeSource, /Analysis history/)
  assert.match(homeSource, /#analysis-history/)
  assert.match(advancedSource, /id="analysis-history"/)
  assert.match(advancedSource, /Previous analysis/)
})

test("legacy expert-analysis deep links still open Advanced Analysis", () => {
  assert.match(appPageSource, /query\.analysis_id/)
  assert.match(appPageSource, /query\.signal_id/)
  assert.match(appPageSource, /query\.incident_id/)
  assert.match(advancedSource, /searchParams\.get\("analysis_id"\)/)
  assert.match(advancedSource, /searchParams\.get\("signal_id"\)/)
  assert.match(advancedSource, /searchParams\.get\("incident_id"\)/)
})

test("incident selection links to the unified cockpit", () => {
  assert.match(homeSource, /incidentWorkspaceHref/)
  assert.match(homeSource, /<Link[\s\S]*href=\{incidentWorkspaceHref/)
  assert.equal(
    incidentWorkspaceHref("incident:checkout/1"),
    "/app/incidents/incident%3Acheckout%2F1",
  )
})

test("incident-home filtering prioritizes active incidents", () => {
  const active = incident()
  const resolved = incident({
    incident_id: "incident:resolved",
    status: "resolved",
  })

  assert.equal(incidentNeedsAttention(active), true)
  assert.equal(incidentNeedsAttention(resolved), false)
  assert.deepEqual(
    filterIncidentHomeRecords([resolved, active]).map(
      (item) => item.incident_id,
    ),
    [active.incident_id],
  )
})

test("incident-home search covers operational context", () => {
  assert.equal(
    filterIncidentHomeRecords(
      [incident()],
      { query: "payments", scope: "recent" },
    ).length,
    1,
  )
  assert.equal(
    filterIncidentHomeRecords(
      [incident()],
      { query: "inventory", scope: "recent" },
    ).length,
    0,
  )
})

test("technical cockpit opens with answer, cause, impact and action", () => {
  assert.deepEqual(
    TECHNICAL_SECTION_ORDER.slice(0, 4),
    ["what-happened", "root-cause", "impact", "next-action"],
  )
  for (const phrase of [
    "What happened",
    "Likely root cause",
    "Primary impact",
    "First response",
  ]) {
    assert.match(technicalSource, new RegExp(phrase))
  }
})

test("failure path remains in the primary investigation column", () => {
  assert.ok(
    technicalSource.indexOf("<FailurePath") <
      technicalSource.indexOf("<ResponseGuidance"),
  )
  assert.match(technicalSource, /id="dependency-path"/)
})

test("long failure paths are bounded without reordering endpoints", () => {
  const path = Array.from({ length: 9 }, (_, index) => ({
    order: index + 1,
  }))
  const compact = compactDependencyPath(path, 5)

  assert.equal(compact.length, 5)
  assert.deepEqual(
    compact.map((step) => step.order),
    [1, 2, 3, 8, 9],
  )
})

test("only the first three response actions are primary", () => {
  const groups = partitionRemediationActions(
    [1, 2, 3, 4, 5].map(action),
  )

  assert.deepEqual(groups.primary.map((item) => item.rank), [1, 2, 3])
  assert.deepEqual(groups.additional.map((item) => item.rank), [4, 5])
  assert.match(responseSource, /Show \{actionGroups\.additional\.length\} additional response action/)
})

test("remediation rationale and previews are progressive", () => {
  assert.match(responseSource, /<details className="mt-3 border-t/)
  assert.match(responseSource, /Review rationale, potential impact and verification/)
  assert.ok(
    responseSource.indexOf("<RemediationPreview") >
      responseSource.indexOf("<details className=\"mt-3 border-t"),
  )
})

test("historical cases are progressively disclosed", () => {
  assert.match(responseSource, /View historical cases/)
  assert.match(businessSource, /<details className="rounded-md border border-border bg-card p-4">/)
  assert.match(businessSource, /Similar incidents/)
})

test("raw evidence and technical IDs are progressive", () => {
  assert.match(responseSource, /View causal evidence/)
  assert.match(responseSource, /Technical metadata/)
  assert.doesNotMatch(responseSource, /<details[^>]*open/)
})

test("blast-radius entities remain bounded by default", () => {
  assert.match(technicalSource, /important_affected_entities/)
  assert.match(technicalSource, /View \{blast\.returned_entity_count\} important affected entities/)
  assert.match(technicalSource, /omitted_entity_count/)
})

test("owner is visible in the immediate answer and context rail", () => {
  assert.match(technicalSource, /label="Root owner"/)
  assert.match(technicalSource, /<OwnershipSection briefing=\{briefing\}/)
  assert.match(technicalSource, /label="On-call"/)
})

test("verification follows response guidance in the main flow", () => {
  assert.ok(
    technicalSource.indexOf("<ResponseGuidance") <
      technicalSource.indexOf("<VerificationPlan"),
  )
  assert.match(responseSource, /After manual remediation/)
  assert.match(responseSource, /aria-hidden="true"/)
})

test("business overview is materially simpler than technical mode", () => {
  assert.ok(businessSource.length < technicalSource.length)
  assert.doesNotMatch(
    businessSource,
    /ResponseGuidance|VerificationPlan|EvidenceAndWarnings|important_affected_entities/,
  )
  for (const label of [
    "Current status",
    "Business impact",
    "Owner",
    "What caused it?",
    "What is being done?",
    "Resolution status",
  ]) {
    assert.match(businessSource, new RegExp(label.replace("?", "\\?")))
  }
})

test("view switching preserves the loaded briefing", () => {
  assert.match(workspaceSource, /router\.replace/)
  assert.match(workspaceSource, /\{ scroll: false \}/)
  assert.match(workspaceSource, /mode === "technical"/)
  assert.match(workspaceSource, /<BusinessOverview briefing=\{briefing\}/)
})

test("cockpit still issues exactly one unified briefing request", () => {
  assert.match(workspaceSource, /getIncidentBriefing/)
  assert.doesNotMatch(
    cockpitSource,
    /getIncidentOwnershipImpact|getBlastRadius|getIncidentRecord|getLatestCausalAnalysis/,
  )
})

test("cockpit has no infrastructure execution controls", () => {
  for (const label of [
    "Execute",
    "Auto-fix",
    "Rollback now",
    "Restart now",
    "Approve and execute",
  ]) {
    assert.equal(isMutationControlLabel(label), true)
    assert.doesNotMatch(
      cockpitSource,
      new RegExp(`>\\s*${label}\\s*<`, "i"),
    )
  }
})

test("cockpit has no 14F, 14G or 14H dependency", () => {
  assert.doesNotMatch(
    cockpitSource,
    /execution-readiness|action-approvals|execution-intents|execution-transactions/,
  )
})

test("pinned topology selection is preserved end to end", () => {
  assert.match(technicalSource, /topologyHref/)
  assert.match(technicalSource, /View pinned topology/)
  assert.match(
    topologySource,
    /setToSnapshotId\(\s*selectedSnapshot\.snapshot_id/,
  )
  assert.match(
    topologySource,
    /searchParams\.get\("snapshot_id"\)/,
  )
})

test("incident deep-link route remains backward compatible", () => {
  assert.match(workspaceSource, /incidentWorkspaceHref\(incidentId, nextMode\)/)
  assert.equal(
    incidentWorkspaceHref("incident:one", "business"),
    "/app/incidents/incident%3Aone?view=business",
  )
})

test("all established sidebar routes remain present", () => {
  for (const href of [
    "/app",
    "/app/topology",
    "/app/live-cluster",
    "/app/code-to-runtime",
    "/app/change-impact",
    "/app/signals",
    "/app/identities",
    "/app/cli",
    "/app/ask",
    "/app/integrations",
    "/app/network-dependencies",
  ]) {
    assert.match(sidebarSource, new RegExp(`href: "${href}"`))
  }
})

test("sidebar groups operations, intelligence and tools", () => {
  for (const group of ["Operations", "Intelligence", "Tools"]) {
    assert.match(sidebarSource, new RegExp(`label: "${group}"`))
  }
  assert.match(sidebarSource, /pathname\.startsWith\(\s*"\/app\/incidents\/"/)
})

test("disclosure controls use native keyboard semantics", () => {
  const disclosures = cockpitSource.match(/<details/g) ?? []
  assert.ok(disclosures.length >= 8)
  assert.match(cockpitSource, /<summary/g)
  assert.doesNotMatch(cockpitSource, /onKeyDown/)
})

test("incident home and cockpit expose loading recovery", () => {
  assert.match(homeSource, /aria-label="Loading incident home"/)
  assert.match(homeSource, /Retry/)
  assert.match(workspaceSource, /aria-label="Loading incident briefing"/)
  assert.match(workspaceSource, /Retry briefing/)
})

test("degraded briefing sections remain local", () => {
  assert.match(technicalSource, /Blast-radius detail is unavailable/)
  assert.match(technicalSource, /Root-cause ownership is unresolved/)
  assert.match(technicalSource, /A dependency path is not available/)
  assert.match(responseSource, /No similar resolved incidents were found/)
})

test("active and resolved outcomes remain distinct", () => {
  assert.match(responseSource, /Incident still active/)
  assert.match(responseSource, /Time to resolution/)
  assert.match(businessSource, /Incident in progress/)
  assert.match(businessSource, /Recorded outcome/)
})

test("responsive cockpit uses a desktop context rail and mobile stack", () => {
  assert.match(technicalSource, /xl:grid-cols-\[minmax\(0,1fr\)_300px\]/)
  assert.match(technicalSource, /xl:sticky/)
  assert.match(homeSource, /sm:grid-cols-/)
  assert.match(businessSource, /lg:grid-cols-/)
})

test("new surfaces avoid fixed wide canvases and horizontal overflow", () => {
  const newSurfaces = `${homeSource}\n${cockpitSource}`
  assert.doesNotMatch(newSurfaces, /min-w-\[(?:[8-9]\d{2}|\d{4,})px\]/)
  assert.match(newSurfaces, /min-w-0/)
  assert.match(workspaceSource, /max-w-\[1480px\]/)
})

test("frontend validation scripts remain available", () => {
  const packageJson = JSON.parse(packageSource)

  for (const script of ["typecheck", "lint", "test", "build"]) {
    assert.equal(typeof packageJson.scripts[script], "string")
  }
})
