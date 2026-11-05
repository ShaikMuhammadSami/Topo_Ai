import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import {
  resolutionSuccessHref,
  submitIncidentStatus,
} from "../lib/incident-resolution.ts"
import {
  checkIncidentResolution,
  getIncidentResolutionPlan,
} from "../lib/topo-api.ts"

function incident(status = "resolved") {
  return {
    incident_id: "incident:payment/1",
    fingerprint: "fingerprint:one",
    status,
    severity: "error",
    title: "Payment failure",
    summary: "Payment workload is unhealthy.",
    cluster_name: "docker-desktop",
    namespace: "topo-live-test",
    primary_signal_id: "signal:one",
    latest_signal_id: "signal:one",
    topology_snapshot_id: "snapshot:one",
    affected_entity_id: "pod:one",
    affected_object_kind: "KubernetesPod",
    affected_object_name: "payment-service-abc",
    first_observed_at: "2026-11-05T10:00:00Z",
    last_observed_at: "2026-11-05T10:01:00Z",
    latest_analysis_id: "analysis:one",
    top_hypothesis_title: "Deployment image changed",
    top_hypothesis_score: 0.9,
    recommendation_count: 1,
    latest_recommendation_id: "recommendation:one",
    recovery_status: null,
    latest_recovery_verification_id: null,
    occurrence_count: 1,
    created_at: "2026-11-05T10:00:00Z",
    updated_at: "2026-11-05T10:02:00Z",
    status_note: "Verified by the operator.",
  }
}

test("resolved status success verifies response and navigates", async () => {
  const gate = { current: false }
  const calls = []
  const navigations = []

  const result = await submitIncidentStatus({
    incidentId: "incident:payment/1",
    status: "resolved",
    note: "Verified by the operator.",
    gate,
    updateStatus: async (incidentId, request) => {
      calls.push({ incidentId, request })
      return incident()
    },
    navigate: (href) => navigations.push(href),
  })

  assert.equal(result.outcome, "saved")
  assert.deepEqual(calls, [
    {
      incidentId: "incident:payment/1",
      request: {
        status: "resolved",
        note: "Verified by the operator.",
      },
    },
  ])
  assert.deepEqual(navigations, [
    "/app?resolved_incident=incident%3Apayment%2F1",
  ])
  assert.equal(gate.current, false)
})

test("failed save preserves navigation and releases the guard", async () => {
  const gate = { current: false }
  const navigations = []

  await assert.rejects(
    submitIncidentStatus({
      incidentId: "incident:payment/1",
      status: "resolved",
      note: null,
      gate,
      updateStatus: async () => {
        throw new Error("status API unavailable")
      },
      navigate: (href) => navigations.push(href),
    }),
    /status API unavailable/,
  )

  assert.deepEqual(navigations, [])
  assert.equal(gate.current, false)
})

test("duplicate click is ignored while a request is pending", async () => {
  let release
  const gate = { current: false }
  let updateCalls = 0
  const navigations = []

  const first = submitIncidentStatus({
    incidentId: "incident:payment/1",
    status: "resolved",
    note: null,
    gate,
    updateStatus: async () => {
      updateCalls += 1
      await new Promise((resolve) => {
        release = resolve
      })
      return incident()
    },
    navigate: (href) => navigations.push(href),
  })

  const duplicate = await submitIncidentStatus({
    incidentId: "incident:payment/1",
    status: "resolved",
    note: null,
    gate,
    updateStatus: async () => {
      updateCalls += 1
      return incident()
    },
    navigate: (href) => navigations.push(href),
  })

  assert.deepEqual(duplicate, { outcome: "duplicate" })
  assert.equal(updateCalls, 1)
  assert.deepEqual(navigations, [])

  release()
  await first
  assert.equal(updateCalls, 1)
  assert.equal(navigations.length, 1)
})

test("mismatched status response is treated as failure", async () => {
  const gate = { current: false }
  const navigations = []

  await assert.rejects(
    submitIncidentStatus({
      incidentId: "incident:payment/1",
      status: "resolved",
      note: null,
      gate,
      updateStatus: async () => incident("open"),
      navigate: (href) => navigations.push(href),
    }),
    /not saved as resolved/,
  )

  assert.deepEqual(navigations, [])
})

test("success destination is encoded and inbox exposes confirmation", async () => {
  assert.equal(
    resolutionSuccessHref("incident/a b"),
    "/app?resolved_incident=incident%2Fa%20b",
  )

  const homeSource = await readFile(
    new URL(
      "../components/app/incident-home.tsx",
      import.meta.url,
    ),
    "utf8",
  )
  assert.match(homeSource, /Incident marked resolved/)
  assert.match(homeSource, /role="status"/)
})

test("resolution check API encodes the incident and pins the displayed snapshot", async () => {
  const originalFetch = globalThis.fetch
  const requests = []
  globalThis.fetch = async (input, init = {}) => {
    requests.push({ input, init })
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })
  }

  try {
    await getIncidentResolutionPlan("incident/a b")
    await checkIncidentResolution(
      "incident/a b",
      "snapshot:current/1",
    )
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(
    requests[0].input,
    "/api/v1/incident-records/incident%2Fa%20b/resolution-check",
  )
  assert.equal(requests[0].init.method, undefined)
  assert.equal(
    requests[1].input,
    "/api/v1/incident-records/incident%2Fa%20b/resolution-check",
  )
  assert.equal(requests[1].init.method, "POST")
  assert.deepEqual(JSON.parse(requests[1].init.body), {
    snapshot_id: "snapshot:current/1",
  })
})

test("Check and Resolve discloses persisted evidence and requires final confirmation", async () => {
  const source = await readFile(
    new URL(
      "../components/app/incident-check-resolve.tsx",
      import.meta.url,
    ),
    "utf8",
  )

  assert.match(source, /already collected topology evidence/)
  assert.match(source, /It will not run kubectl/)
  assert.match(source, /Topo does not execute these commands/)
  assert.match(source, /Confirm and run read-only checks/)
  assert.match(source, /result\.eligible_to_resolve/)
  assert.match(source, /Confirm mark resolved/)
  assert.match(source, /label="Tenant"/)
  assert.match(source, /plan\.target\.tenant_id/)
  assert.match(
    source,
    /const revalidated =\s*await checkIncidentResolution/,
  )
  assert.match(source, /!revalidated\.eligible_to_resolve/)
  assert.doesNotMatch(source, /fetch\([^)]*kube/i)
})
