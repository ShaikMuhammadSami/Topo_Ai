# Adversarial Evaluation v1

## Purpose and boundary

EVAL-1 begins measured correctness. It evaluates the frozen TopoAI Truth
Substrate v1 against evidence declared and captured independently of Topo. It
does not tune causal ranking, modify candidate eligibility, repair blast
traversal, change identity semantics, or add product instrumentation.

The implementation lives at repository root in `evaluation/`. It is a
black-box consumer of existing HTTP APIs and provider-native Kubernetes data.
It deliberately does not import `backend/app` or `agent/src`.

## Four independent layers

```text
predeclared scenario manifest
        ↓
fault/change orchestration + execution receipt
        ↓
Kubernetes provider-native verification
        ↓
read-only Topo observation → deterministic comparison
```

1. The versioned manifest defines logical objects, causal intent, distractors,
   non-causes, path and impact expectations before Topo is queried.
2. The orchestrator performs exact mutations and records provider UIDs,
   resource versions, images, generations, and action times.
3. Provider verification independently reads Deployment, ReplicaSet, Pod, and
   Service state through `kubectl -o json`, including owner UIDs and failure
   reasons.
4. The evaluator reads incident, pinned snapshot, causal analysis, evidence
   ledger, briefing, blast radius, changes, and signals from Topo APIs. It maps
   logical aliases through provider UIDs to Topo canonical entities and then
   compares observations with the immutable manifest.

Topo output is never copied into expected truth. OpenAI and all other LLMs are
absent from scenario decisions and grading.

## Ground-truth hierarchy

The authored causal intent establishes what the experiment introduces. The
execution receipt proves the actual mutation. Provider-native confirmation
establishes the resulting object identity, ownership chain, selector state,
and failure. If action execution or provider verification cannot establish
truth, Topo is not graded: the run is `HARNESS_ERROR` or `INCONCLUSIVE`.

Display names are not sufficient identity when a Kubernetes UID is available.
Manifest aliases are resolved only after execution:

```text
logical alias → provider UID → Topo external/native identity → canonical ID
```

## Versioned contracts

- Manifest: `eval-1.scenario.v1`, schema `scenario-manifest.schema.json`.
- Execution receipt: `eval-1.execution.v1`.
- Provider verification: `eval-1.provider.v1`.
- Topo observation: `eval-1.topo-observation.v1`.
- Result: `eval-1.result.v1`, schema `evaluation-result.schema.json`.
- Harness: `eval-1.v1`.

The result contains `ground_truth`, `execution_receipt`,
`provider_verification`, and `topo_observation` as separate sibling objects.
No credentials, agent tokens, enrollment tokens, kubeconfig data, or large raw
cluster dumps are retained.

## Scenario manifest

Each JSON manifest declares environment requirements, stable logical aliases,
root change/entity, affected entity, failure mode, distractors, explicit
non-causes, required/optional/forbidden path hops, incident count/scope,
required affected and explicitly unaffected objects, evidence expectations,
TC-5 invariants, and abstention behavior. Ephemeral UIDs never appear in a
manifest.

## Execution and provider verification

Every action records its type, logical target, provider UID, time, before and
after state, and a bounded provider receipt such as `resourceVersion`.
Verification records contain only scenario-relevant fields: kind, namespace,
name, UID, selected spec/status facts, owner UID, labels, selectors, and
observation time. The failing Pod must be owned by the captured ReplicaSet and
that ReplicaSet by the expected Deployment; the waiting reason must be
`ErrImagePull` or `ImagePullBackOff`.

## Topo observation

The observation captures all incident candidates in scope, the selected full
incident record, related signals, its immutable pinned snapshot, the durable
latest causal analysis, briefing, blast-radius result, relevant change events,
HTTP statuses, and first-observed timestamps. These are system-under-test
facts, never expected facts.

## Status semantics

- `PASS`: provider truth is established and every mandatory product assertion
  agrees with it.
- `FAIL`: provider truth is established but Topo disagrees, omits a required
  output within the bounded wait, supports an explicit non-cause, overreaches
  the declared blast set, or violates TC-5.
- `INCONCLUSIVE`: provider state exists but required identity or expected truth
  cannot be established safely.
- `HARNESS_ERROR`: prerequisites, orchestration, provider verification, or
  cleanup integrity failed. It is never reported as a Topo product failure.

## Metric definitions

- `root_cause_top1_correct`: rank 1 matches an accepted manifest selector and
  its provider-mapped logical entity.
- `root_cause_top3_contains_truth`: at least one of ranks 1–3 matches.
- `identity_resolved`: incident has an affected canonical entity ID.
- `identity_correct`: that canonical entity maps to the affected provider UID.
- `causal_path_required_hops_present`: every required semantic
  alias/predicate hop is backed by snapshot relationships referenced by the
  leading evidence ledger.
- `causal_path_edge_precision`: relevant required/optional hops divided by
  observed ledger-backed semantic hops; zero-output behavior is explicit.
- `explicit_non_cause_supported_count`: supporting critical ledger claims that
  reference provider-mapped explicit non-causes.
- `unsupported_critical_claim_count`: critical supporting claims conflicting
  with non-cause truth (the bounded EVAL-1 definition).
- blast TP: required affected aliases returned by Topo; FP: explicitly
  unaffected aliases returned; FN: required affected aliases absent.
- blast precision: `TP/(TP+FP)`; recall: `TP/(TP+FN)`; undefined denominators
  serialize as `null`.
- `false_certainty`: the manifest requires abstention or declares intentional
  missing evidence, yet Topo supplies a ranked conclusion labeled
  `supported_under_current_model`.
- `abstention_correct`: an abstention-required scenario has no hypotheses or an
  insufficient/incomplete/contested-with-gaps evidence state.
- time metrics: seconds from the independently receipted causal fault action to
  first incident observation, durable RCA generation, and useful briefing.

Every run also enforces TC-5: `score_type=heuristic_ranking`,
`calibration_status=not_calibrated`, and `calibrated_probability=null`.
Ranking scores are never interpreted as probabilities.

## Causal path and blast comparison

Paths compare logical objects, predicates, and provider-native identity rather
than volatile relationship IDs. Exact serialization and valid extra optional
hops are not required. Actual relationship IDs remain in the Topo observation
for inspection. Blast evaluation counts only independently declared scenario
members; it does not claim the four scenarios exhaust every possible impact.

## Bounded waiting

Backend startup, initial snapshot, workload readiness, provider failure,
incident, and durable RCA waits all have explicit deadlines. A provider failure
followed by no Topo incident/RCA is a product `FAIL`. Inability to create or
verify the provider scenario is `HARNESS_ERROR`. There is no infinite polling.

## Isolation, safety, and cleanup

Every run uses a temporary SQLite backend database and temporary agent home.
The enrolled agent is namespace-scoped. Namespaces must match
`^topo-eval-[abcd]-[a-z0-9]{6,12}$` and carry
`topo.ai/evaluation-run=<run-id>`. Cleanup re-reads and validates both name and
label before requesting deletion. Processes are terminated before temporary
state is removed. Results are written to ignored `evaluation/results/`.

## Replay and retention

Generated results are diagnostic evidence and are ignored by Git. Baseline
reports quote the minimal facts needed for architecture review. A confirmed
product defect retains its predeclared manifest permanently; raw cluster dumps
and credentials do not become fixtures.

**EVERY TIME TOPO IS WRONG, PRESERVE THE SCENARIO FOREVER.**

## Four EVAL-1 Sentinels

- A: an obvious Deployment bad-image mutation.
- B: a nearby healthy distractor mutation followed by an independent victim
  bad-image mutation.
- C: the known source-mutation versus derived topology-diff ranking weakness.
- D: one failing and one structurally nearby but operationally independent
  workload, measuring current blast overreach without repairing it.

## Future release gates

These targets are **FUTURE RELEASE GATES**, not results validated by the
four-sentinel EVAL-1 sample:

- identity precision 100% in golden scenarios; incorrect ambiguity resolution 0;
- critical path provenance 100%; unsupported critical claims 0%;
- Top-1 at least 90%; Top-3 at least 98%; canonical golden incidents 100% Top-1;
- blast precision at least 95%; blast recall at least 90%; critical impact recall 100%;
- false incident merge below 1%; fragmentation below 1%;
- critical evidence provenance 100%; causal edge precision at least 98%;
- required-hop completeness at least 95%; unsupported owner attribution 0;
- false certainty approximately 0;
- p95 useful briefing below 60 seconds after usable evidence exists.

Four runs are not statistically meaningful and must never be advertised as a
product accuracy percentage.

## Known EVAL-1 limitations

The harness currently supports Kubernetes, one active namespace per isolated
agent, and the four sentinel families. It uses `kubectl` rather than a direct
Python Kubernetes client, measures observation time with bounded polling, and
evaluates unsupported critical claims only where the manifest provides an
explicit conflict. It does not simulate application traffic, prove business
impact, validate cloud providers, or claim statistical calibration.
