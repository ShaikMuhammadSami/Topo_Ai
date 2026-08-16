import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import {
  TECHNICAL_SECTION_ORDER,
  affectedEntityLabel,
  buildIncidentWorkspaceModel,
  formatBriefingDuration,
  incidentElapsedSeconds,
  incidentTopologyHref,
  incidentWorkspaceHref,
  incidentWorkspaceMode,
  isActiveIncident,
  isMutationControlLabel,
  remediationActionTarget,
} from "../lib/incident-briefing.ts"
import {
  getIncidentBriefing,
} from "../lib/topo-api.ts"

const componentSource = (
  await Promise.all(
    [
      "incident-briefing-workspace.tsx",
      "incident-briefing-technical.tsx",
      "incident-briefing-response.tsx",
      "incident-briefing-business.tsx",
    ].map((fileName) =>
      readFile(
        new URL(
          `../components/app/${fileName}`,
          import.meta.url,
        ),
        "utf8",
      ),
    ),
  )
).join("\n")
const inboxSource = await readFile(
  new URL(
    "../components/app/incident-inbox.tsx",
    import.meta.url,
  ),
  "utf8",
)
const topologyPageSource = await readFile(
  new URL(
    "../app/app/topology/page.tsx",
    import.meta.url,
  ),
  "utf8",
)
const briefingPageSource = await readFile(
  new URL(
    "../app/app/incidents/[incidentId]/page.tsx",
    import.meta.url,
  ),
  "utf8",
)

function completeBriefing() {
  return {
    incident: {
      incident_id: "incident:checkout/1",
      title: "Checkout degradation",
      summary: "Checkout requests are failing.",
      status: "open",
      severity: "critical",
      cluster_name: "production",
      namespace: "payments",
      environment: "production",
      affected_entity_id: "entity:checkout",
      affected_object_kind: "KubernetesService",
      affected_object_name: "checkout-api",
      first_observed_at: "2026-08-16T10:00:00Z",
      last_observed_at: "2026-08-16T10:05:00Z",
      current_state: "Checkout is degraded.",
      recovery_status: null,
    },
    summary: {
      text: "Checkout degraded shortly after payment-api revision 42 was deployed.",
      evidence_references: ["evidence:summary"],
    },
    root_cause: {
      causal_analysis_id: "causal:1",
      topology_snapshot_id: "snapshot:incident-time",
      root_event_id: "event:commit",
      root_event_title: "Payment retry code change",
      root_event_source: "github",
      root_event_kind: "commit",
      root_entity_id: "entity:payments",
      causal_confidence: 0.87,
      confidence_level: "high",
      causal_change_event_id: "event:deploy",
      causal_change_title: "Deploy payment-api revision 42",
      causal_change_source: "github_actions",
      causal_change_type: "deployment",
      causal_change_occurred_at: "2026-08-16T09:56:00Z",
      summary: "The deployment preceded pod and checkout failures.",
      reasons: ["Temporal and topology evidence."],
      evidence_references: ["evidence:root"],
    },
    causal_evidence: [
      {
        evidence_id: "evidence:root",
        evidence_type: "temporal",
        source: "causal_rca",
        title: "Deployment timing",
        detail: "Deployment preceded the incident.",
        observed_at: "2026-08-16T09:56:00Z",
        event_id: "event:deploy",
        entity_id: "entity:payments",
        weight: 0.9,
      },
    ],
    recent_relevant_changes: [
      {
        event_id: "event:deploy",
        title: "Deploy payment-api revision 42",
        role: "target_change",
        source: "github_actions",
        change_type: "deployment",
        occurred_at: "2026-08-16T09:56:00Z",
        repository: "https://example.test/payments",
        commit_sha: "abc123",
        pipeline_name: "deploy-payments",
        release_version: "v42",
        minutes_before_incident: 4,
        evidence_references: ["evidence:root"],
      },
    ],
    dependency_path: [
      {
        order: 1,
        node_id: "event|event:deploy",
        node_type: "change_event",
        label: "Deploy payment-api revision 42",
        event_id: "event:deploy",
        entity_id: null,
        relation_from_previous: null,
        relation_confidence: null,
        topology_relationship_id: null,
        topology_relationship_type: null,
        topology_relationship_direction: null,
        evidence_references: ["evidence:root"],
      },
      {
        order: 2,
        node_id: "entity|entity:payments",
        node_type: "entity",
        label: "payment-api",
        event_id: null,
        entity_id: "entity:payments",
        relation_from_previous: "touches_entity",
        relation_confidence: 0.95,
        topology_relationship_id: "relationship:deploy-payments",
        topology_relationship_type: "deploys",
        topology_relationship_direction: "forward",
        evidence_references: ["evidence:root"],
      },
      {
        order: 3,
        node_id: "entity|entity:checkout",
        node_type: "entity",
        label: "checkout-api",
        event_id: null,
        entity_id: "entity:checkout",
        relation_from_previous: "topology_path",
        relation_confidence: 0.8,
        topology_relationship_id: "relationship:payments-checkout",
        topology_relationship_type: "depends_on",
        topology_relationship_direction: "forward",
        evidence_references: ["evidence:root"],
      },
    ],
    blast_radius: {
      topology_snapshot_id: "snapshot:incident-time",
      root_entity_id: "entity:payments",
      affected_entity_count: 12,
      returned_entity_count: 2,
      omitted_entity_count: 10,
      direct_impact_count: 3,
      indirect_impact_count: 7,
      potential_impact_count: 2,
      affected_services: ["payment-api", "checkout-api"],
      affected_dependency_types: ["depends_on"],
      affected_teams: ["Payments Platform", "Checkout Platform"],
      business_capabilities: ["Checkout"],
      important_affected_entities: [
        {
          entity_id: "entity:payments",
          entity_kind: "KubernetesDeployment",
          entity_name: "payment-api",
          impact: "direct",
          distance: 0,
          impact_score: 1,
          service_name: "payment-api",
          owner_team: "Payments Platform",
          business_capability: "Checkout",
          criticality: "tier_1",
        },
        {
          entity_id: "entity:checkout",
          entity_kind: "KubernetesService",
          entity_name: "checkout-api",
          impact: "indirect",
          distance: 1,
          impact_score: 0.8,
          service_name: "checkout-api",
          owner_team: "Checkout Platform",
          business_capability: "Checkout",
          criticality: "tier_1",
        },
      ],
      evidence_references: ["evidence:root"],
    },
    operational_context: {
      ownership: {
        resolved: true,
        entity_id: "entity:payments",
        owner_team: "Payments Platform",
        owner_email: "payments@example.test",
        oncall_contact: "payments-oncall",
        service_name: "payment-api",
        repository_url: "https://example.test/payments",
        business_capability: "Checkout",
        criticality: "tier_1",
        confidence: 0.95,
        evidence_references: ["evidence:ownership"],
      },
      business_impact: {
        business_impact_level: "critical",
        affected_entity_count: 12,
        resolved_entity_count: 10,
        unresolved_entity_count: 2,
        affected_team_count: 2,
        affected_capability_count: 1,
        highest_criticality: "tier_1",
        owner_teams: ["Payments Platform", "Checkout Platform"],
        business_capabilities: ["Checkout"],
        oncall_contacts: ["payments-oncall"],
        repositories: ["https://example.test/payments"],
        routing_recommendation: "Route to Payments Platform on-call.",
        evidence_references: ["evidence:ownership"],
      },
      escalation_targets: ["Payments Platform", "payments-oncall"],
    },
    remediation: {
      response_priority: "critical",
      response_priority_reason: "Tier-1 checkout is affected.",
      actions: [
        {
          action_id: "action:validate",
          rank: 1,
          category: "validate",
          semantics: "validation",
          family: "validate",
          priority: "critical",
          title: "Validate deployed revision",
          description: "Confirm the failing pods run revision 42.",
          reason: "The leading hypothesis identifies revision 42.",
          risk: "low",
          requires_human_approval: false,
          entity_ids: ["entity:payments"],
          evidence_event_ids: ["event:deploy"],
          evidence_references: ["evidence:root"],
          runbook_url: null,
          current_evidence_strength: "high",
          historical_support: {
            level: "supported",
            score: 0.8,
            similar_incident_count: 3,
            action_observed_count: 2,
            effective_count: 2,
            ineffective_count: 0,
            unknown_effect_count: 0,
            supporting_incident_ids: ["incident:old-1", "incident:old-2"],
            contradicting_incident_ids: [],
            support_reasons: ["Worked in confirmed regressions."],
            caution_reasons: ["History does not guarantee this result."],
          },
          combined_decision_support: "historically_supported",
        },
        {
          action_id: "action:rollback",
          rank: 2,
          category: "rollback_candidate",
          semantics: "mitigation",
          family: "rollback",
          priority: "high",
          title: "Consider rollback",
          description: "If revision 42 is causal, consider reverting it manually.",
          reason: "Rollback targets the suspected deployment change.",
          risk: "high",
          requires_human_approval: true,
          entity_ids: ["entity:payments"],
          evidence_event_ids: ["event:deploy"],
          evidence_references: ["evidence:root"],
          runbook_url: "https://example.test/runbook",
          current_evidence_strength: "high",
          historical_support: {
            level: "supported",
            score: 0.8,
            similar_incident_count: 3,
            action_observed_count: 2,
            effective_count: 2,
            ineffective_count: 0,
            unknown_effect_count: 0,
            supporting_incident_ids: ["incident:old-1", "incident:old-2"],
            contradicting_incident_ids: [],
            support_reasons: ["Worked in confirmed regressions."],
            caution_reasons: ["History does not guarantee this result."],
          },
          combined_decision_support: "historically_supported",
        },
      ],
      previews: [
        {
          action_id: "action:rollback",
          action_title: "Consider rollback",
          intended_effect: "If the suspected deployment is causal, reverting it would restore the previous deployment state.",
          affected_target: {
            entity_ids: ["entity:payments"],
            change_event_ids: ["event:deploy"],
          },
          potentially_impacted_entities: [
            {
              entity_id: "entity:checkout",
              entity_kind: "KubernetesService",
              entity_name: "checkout-api",
              impact: "indirect",
              distance: 1,
              impact_score: 0.8,
              service_name: "checkout-api",
              owner_team: "Checkout Platform",
              business_capability: "Checkout",
              criticality: "tier_1",
            },
          ],
          potential_impact_scope_note: "Connected checkout consumers may be affected while rollout stabilizes.",
          risk: "high",
          expected_observation_if_successful: "The previous revision is active and checkout errors recover.",
          possible_failure_modes: ["The suspected change may not be causal."],
          verification_steps: [],
          rollback_or_recovery_considerations: ["Keep the current revision available for recovery."],
          historical_observations: ["Two confirmed deployment regressions responded to rollback."],
          evidence_references: ["evidence:root"],
        },
      ],
      runbooks: [],
      overall_historical_support: "supported",
      read_only: true,
    },
    historical_context: {
      support_level: "moderate",
      similar_incident_count: 3,
      similar_incidents: [
        {
          incident_id: "incident:old-1",
          incident_title: "Earlier payment regression",
          similarity: 0.82,
          why_it_matches: ["Same service and change type."],
          important_differences: ["Occurred in staging."],
          rca_verdict: "confirmed",
          resolution_summary: "Rollback restored service.",
          primary_resolution_action: "Rollback deployment",
          primary_action_effectiveness: "effective",
          time_to_mitigation_seconds: 420,
          time_to_resolution_seconds: 780,
          evidence_references: ["evidence:history"],
        },
      ],
      resolution_patterns: [],
      summary: "Three similar incidents were found; rollback was effective in two confirmed regressions.",
    },
    verification_plan: [
      {
        step_id: "verify:revision",
        source_action_id: "action:rollback",
        title: "Confirm deployment revision",
        description: "Check that payment-api reports the expected revision.",
        expected_observation: "Previous revision is active.",
        entity_ids: ["entity:payments"],
        evidence_references: ["evidence:root"],
      },
    ],
    outcome: null,
    warnings: ["Ownership is incomplete for two affected entities."],
    ai_summary: "Checkout degraded after the payment-api deployment.",
    ai_status: "available",
    ai_provider: "openai",
    ai_model: "gpt-test",
  }
}

test("briefing request encodes the incident ID and AI query", async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), options })
    return new Response(
      JSON.stringify(completeBriefing()),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    )
  }

  try {
    await getIncidentBriefing("incident/a b", {
      includeAi: true,
    })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.equal(calls.length, 1)
  assert.match(
    calls[0].url,
    /\/api\/v1\/incidents\/incident%2Fa%20b\/briefing\?include_ai=true$/,
  )
})

test("main answer hierarchy precedes raw evidence", () => {
  assert.deepEqual(
    TECHNICAL_SECTION_ORDER.slice(0, 4),
    ["what-happened", "root-cause", "impact", "next-action"],
  )
  assert.ok(
    TECHNICAL_SECTION_ORDER.indexOf("next-action") <
      TECHNICAL_SECTION_ORDER.indexOf("evidence"),
  )
})

test("technical mode is the default", () => {
  assert.equal(incidentWorkspaceMode(null), "technical")
  assert.equal(incidentWorkspaceMode("unknown"), "technical")
})

test("business mode is selected explicitly", () => {
  assert.equal(incidentWorkspaceMode("business"), "business")
})

test("business and technical URLs point to one incident route", () => {
  assert.equal(
    incidentWorkspaceHref("incident/a", "technical"),
    "/app/incidents/incident%2Fa",
  )
  assert.equal(
    incidentWorkspaceHref("incident/a", "business"),
    "/app/incidents/incident%2Fa?view=business",
  )
})

test("dynamic route decodes an encoded ID exactly once", () => {
  assert.match(briefingPageSource, /decodeURIComponent\(value\)/)
  assert.match(briefingPageSource, /incidentId=\{incidentId\}/)
})

test("mode switching is local URL state and fetches one briefing source", () => {
  assert.match(componentSource, /searchParams\.get\("view"\)/)
  assert.match(componentSource, /getIncidentBriefing/)
  assert.doesNotMatch(componentSource, /getIncidentOwnershipImpact|getBlastRadius|getIncidentRecord/)
})

test("root cause comes directly from briefing data", () => {
  const model = buildIncidentWorkspaceModel(completeBriefing())
  assert.equal(model.immediate.rootCause, "Deploy payment-api revision 42")
  assert.equal(model.immediate.causalConfidence, 0.87)
})

test("what changed preserves briefing change data", () => {
  const model = buildIncidentWorkspaceModel(completeBriefing())
  assert.equal(model.technical.changes.length, 1)
  assert.equal(model.technical.changes[0].event_id, "event:deploy")
})

test("failure path preserves actual briefing order", () => {
  const model = buildIncidentWorkspaceModel(completeBriefing())
  assert.deepEqual(
    model.technical.dependencyPath.map((step) => step.label),
    ["Deploy payment-api revision 42", "payment-api", "checkout-api"],
  )
})

test("missing dependency path degrades cleanly", () => {
  const briefing = completeBriefing()
  briefing.dependency_path = []
  const model = buildIncidentWorkspaceModel(briefing)
  assert.equal(model.degraded.dependencyPathUnavailable, true)
})

test("topology drill-down uses the incident-time snapshot", () => {
  assert.equal(
    incidentTopologyHref(completeBriefing()),
    "/app/topology?snapshot_id=snapshot%3Aincident-time&entity_id=entity%3Apayments",
  )
})

test("missing pinned topology data removes drill-down", () => {
  const briefing = completeBriefing()
  briefing.root_cause.topology_snapshot_id = null
  assert.equal(incidentTopologyHref(briefing), null)
})

test("blast radius exposes bounded totals", () => {
  const model = buildIncidentWorkspaceModel(completeBriefing())
  assert.equal(model.technical.affectedCount, 12)
  assert.equal(model.technical.affectedEntities.length, 2)
})

test("missing blast radius is a degraded state", () => {
  const briefing = completeBriefing()
  briefing.blast_radius = null
  assert.equal(
    buildIncidentWorkspaceModel(briefing).degraded.blastRadiusUnavailable,
    true,
  )
})

test("resolved ownership is displayed from briefing", () => {
  const model = buildIncidentWorkspaceModel(completeBriefing())
  assert.equal(model.immediate.owner, "Payments Platform")
})

test("missing ownership never invents a team", () => {
  const briefing = completeBriefing()
  briefing.operational_context.ownership.resolved = false
  briefing.operational_context.ownership.owner_team = null
  const model = buildIncidentWorkspaceModel(briefing)
  assert.equal(model.immediate.owner, "Ownership unavailable")
  assert.equal(model.degraded.ownershipUnavailable, true)
})

test("response action order is preserved", () => {
  const briefing = completeBriefing()
  briefing.remediation.actions.reverse()
  const model = buildIncidentWorkspaceModel(briefing)
  assert.deepEqual(
    model.technical.actions.map((action) => action.action_id),
    ["action:rollback", "action:validate"],
  )
})

test("remediation preview keeps conditional language", () => {
  const preview = completeBriefing().remediation.previews[0]
  assert.match(preview.intended_effect, /^If /)
  assert.doesNotMatch(preview.intended_effect, /will (fix|resolve)/i)
})

test("remediation target resolves the actual entity", () => {
  const briefing = completeBriefing()
  assert.equal(
    remediationActionTarget(briefing, briefing.remediation.actions[0]),
    "payment-api",
  )
  assert.equal(
    affectedEntityLabel(briefing, "entity:checkout"),
    "checkout-api",
  )
})

test("verification plan preserves backend checks", () => {
  const briefing = completeBriefing()
  assert.equal(briefing.verification_plan[0].title, "Confirm deployment revision")
  assert.match(componentSource, /briefing\.verification_plan\.map/)
})

test("historical context keeps raw counts", () => {
  const model = buildIncidentWorkspaceModel(completeBriefing())
  assert.match(model.business.historicalSummary, /Three similar incidents/)
})

test("missing history renders as unavailable without failure", () => {
  const briefing = completeBriefing()
  briefing.historical_context.similar_incident_count = 0
  briefing.historical_context.similar_incidents = []
  const model = buildIncidentWorkspaceModel(briefing)
  assert.equal(model.degraded.historyUnavailable, true)
  assert.equal(model.business.historicalSummary, null)
})

test("active incident has an in-progress outcome", () => {
  const briefing = completeBriefing()
  assert.equal(isActiveIncident(briefing), true)
  assert.equal(buildIncidentWorkspaceModel(briefing).degraded.outcomeUnavailable, true)
})

test("resolved outcome supplies duration", () => {
  const briefing = completeBriefing()
  briefing.incident.status = "resolved"
  briefing.outcome = {
    outcome_id: "outcome:1",
    status: "resolved",
    mitigated_at: "2026-08-16T10:05:00Z",
    resolved_at: "2026-08-16T10:13:00Z",
    time_to_mitigation_seconds: 300,
    time_to_resolution_seconds: 780,
    final_rca_verdict: "confirmed",
    rca_confidence: 0.95,
    final_root_cause: "Revision 42 regression",
    primary_resolution_action: "Rolled back revision 42",
    resolution_summary: "Checkout recovered after manual rollback.",
    evidence_references: ["evidence:outcome"],
  }
  assert.equal(isActiveIncident(briefing), false)
  assert.equal(formatBriefingDuration(780), "13m")
  assert.equal(incidentElapsedSeconds(briefing), 780)
})

test("AI summary remains optional", () => {
  const briefing = completeBriefing()
  assert.equal(buildIncidentWorkspaceModel(briefing).degraded.aiUnavailable, false)
  briefing.ai_summary = null
  briefing.ai_status = "unavailable"
  assert.equal(buildIncidentWorkspaceModel(briefing).degraded.aiUnavailable, true)
  assert.match(
    componentSource,
    /NEXT_PUBLIC_TOPO_BRIEFING_AI/,
  )
})

test("loading state uses a useful skeleton", () => {
  assert.match(componentSource, /aria-label="Loading incident briefing"/)
  assert.match(componentSource, /animate-pulse/)
})

test("API failure has retry and incident-inbox recovery", () => {
  assert.match(componentSource, /Incident briefing unavailable/)
  assert.match(componentSource, /Retry briefing/)
  assert.match(componentSource, /Return to incident inbox/)
})

test("workspace has no infrastructure mutation controls", () => {
  for (const label of [
    "Execute",
    "Auto-fix",
    "Rollback now",
    "Restart now",
    "Approve and execute",
  ]) {
    assert.equal(isMutationControlLabel(label), true)
    assert.doesNotMatch(
      componentSource,
      new RegExp(`>\\s*${label}\\s*<`, "i"),
    )
  }
})

test("rollback remains guidance rather than a mutation control", () => {
  assert.equal(isMutationControlLabel("Consider rollback"), false)
  assert.match(componentSource, /Guidance only/)
})

test("workspace makes no 14F, 14G, or 14H requests", () => {
  assert.doesNotMatch(
    componentSource,
    /execution-readiness|approvals|execution-intents/,
  )
})

test("raw evidence is progressive disclosure", () => {
  assert.match(componentSource, /<details[\s\S]*View causal evidence/)
  assert.doesNotMatch(componentSource, /<details[^>]*open/)
})

test("existing inbox links to the unified workspace", () => {
  assert.match(inboxSource, /Open unified briefing/)
  assert.match(inboxSource, /incidentWorkspaceHref/)
})

test("existing topology page remains wired to its live view", () => {
  assert.match(topologyPageSource, /LiveTopologyView/)
  assert.match(topologyPageSource, /Topology · live snapshots/)
})

test("responsive structure avoids a fixed incident canvas", () => {
  assert.match(componentSource, /max-w-\[1540px\]/)
  assert.match(componentSource, /lg:grid-cols/)
  assert.doesNotMatch(componentSource, /min-w-\[1[5-9]\d{2}px\]/)
})
