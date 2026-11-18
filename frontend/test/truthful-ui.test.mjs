import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import {
  listSnapshots,
  selectApiTenant,
} from "../lib/topo-api.ts"

async function source(path) {
  return readFile(new URL(`../${path}`, import.meta.url), "utf8")
}

const fictionalEvidence =
  /INC-4419|prod-eu-west-1|payments-prod|9a4f12c|PR #2284|llama-3\.1|ollama|RAG over/i

test("shared application chrome contains no fictional incident or connection context", async () => {
  const [sidebar, topbar] = await Promise.all([
    source("components/app/app-sidebar.tsx"),
    source("components/app/app-topbar.tsx"),
  ])

  assert.doesNotMatch(sidebar, /topo-data|Demo context|collector connected/i)
  assert.doesNotMatch(sidebar, /href: "\/app\/(?:ask|cli)"/)
  assert.doesNotMatch(topbar, /topo-data|showIncidentContext|GitCommitHorizontal/)
  assert.doesNotMatch(`${sidebar}\n${topbar}`, fictionalEvidence)
})

test("CLI direct route is informational and lists only real terminal commands", async () => {
  const cli = await source("components/app/cli-view.tsx")

  assert.match(cli, /not an interactive terminal/i)
  assert.match(cli, /does not[\s\S]*represent a connection/i)
  assert.match(cli, /topo --tenant <tenant-id> incidents list/)
  assert.match(cli, /topo --tenant <tenant-id> causal-rca latest <incident-id>/)
  assert.match(cli, /topo --tenant <tenant-id> incidents blast-radius <incident-id>/)
  assert.match(cli, /topo --tenant <tenant-id> snapshots list/)
  assert.doesNotMatch(cli, /runCommand|useState|<input|connected to cluster/i)
  assert.doesNotMatch(cli, fictionalEvidence)
})

test("Ask direct route cannot manufacture analysis and points to real incident Copilot", async () => {
  const [ask, copilot] = await Promise.all([
    source("components/app/ask-view.tsx"),
    source("components/app/incident-copilot.tsx"),
  ])

  assert.match(ask, /does not run a general chatbot or generate an analysis/i)
  assert.match(ask, /Incident Copilot/)
  assert.match(ask, /No AI provider is assumed to be configured/)
  assert.doesNotMatch(ask, /<form|<input|Suggested action/i)
  assert.doesNotMatch(ask, />Citations</)
  assert.doesNotMatch(ask, fictionalEvidence)
  assert.match(copilot, /createIncidentCopilotSession/)
  assert.match(copilot, /copilotSession\.provider/)
})

test("live infrastructure uses tenant-scoped snapshots and truthful empty and error states", async () => {
  const originalFetch = globalThis.fetch
  const observedTenants = []
  let fail = false

  globalThis.fetch = async (_, init) => {
    observedTenants.push(init.headers.get("X-Topo-Tenant-ID"))
    if (fail) {
      return Response.json(
        { detail: "Snapshot service unavailable" },
        { status: 503 },
      )
    }
    return Response.json([])
  }

  try {
    selectApiTenant("tenant:empty")
    assert.deepEqual(await listSnapshots(), [])
    fail = true
    selectApiTenant("tenant:other")
    await assert.rejects(listSnapshots(), /Snapshot service unavailable/)
    assert.deepEqual(observedTenants, ["tenant:empty", "tenant:other"])
  } finally {
    selectApiTenant(null)
    globalThis.fetch = originalFetch
  }

  const liveCluster = await source("components/app/live-cluster-view.tsx")
  assert.match(liveCluster, /await listSnapshots\(\)/)
  assert.match(liveCluster, /Backend request failed/)
  assert.match(liveCluster, /No topology snapshots/)
  assert.match(liveCluster, /No collected infrastructure is available for this workspace/)
  assert.doesNotMatch(liveCluster, /backend-connected view|collector connected/i)
})

test("incident home remains persisted and tenant switching remounts workspace state", async () => {
  const [appPage, incidentHome, tenantBoundary] = await Promise.all([
    source("app/app/page.tsx"),
    source("components/app/incident-home.tsx"),
    source("components/auth/tenant-boundary.tsx"),
  ])

  assert.match(appPage, /<IncidentHome \/>/)
  assert.match(incidentHome, /listIncidentRecords/)
  assert.doesNotMatch(`${appPage}\n${incidentHome}`, /topo-data/)
  assert.match(tenantBoundary, /Fragment key=\{selected\}/)
})
