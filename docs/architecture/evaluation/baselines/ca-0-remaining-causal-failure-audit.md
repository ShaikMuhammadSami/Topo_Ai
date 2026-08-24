# CA-0 Remaining Causal Failure Audit

Measured: 2026-08-24 against `docker-desktop` at product commit
`107e734b5556bf7ea8fb8c0a79dce93e083107fd`.

## 1. CA-0 scope confirmation

CA-0 is a forensic audit only. No product repair, evaluator pass/fail change,
scenario expectation change, scoring change, candidate/relevance change, or
Truth Contract change was made. The product source roots remained untouched.

## 2. Fresh reproduction

The required pre-tooling reproductions used fresh isolated state:

| Scenario | Run | Result | Provider truth |
|---|---|---|---|
| blast-01 | `679336f6` | FAIL: causal Top-1/Top-3 only | established |
| blast-03 | `f2c832de` | FAIL: causal Top-1/Top-3 only | established |

After the evaluation-only SQLite capture was added, a second fresh pair
produced the review artifacts used below:

| Scenario | Run | Result | Forensic artifact |
|---|---|---|---|
| blast-01 | `70937c95` | FAIL: causal Top-1/Top-3 only | `blast-01-70937c95-causal-forensics.json` |
| blast-03 | `eaba976d` | FAIL: causal Top-1/Top-3 only | `blast-03-eaba976d-causal-forensics.json` |

The FAIL statuses are preserved accepted evaluator outcomes, not forensic
tooling outcomes. BR-1 blast assertions remained correct.

## 3. Root-cause semantic layers

| Level | blast-01 | blast-03 |
|---|---|---|
| Initiating mutation | Deployment `failing-app` image `nginx:1.27-alpine` → `registry.invalid/topo-eval/blast-01:70937c95` | Deployment `failed-backend` image `nginx:1.27-alpine` → `registry.invalid/topo-eval/blast-03:eaba976d` |
| Failure mechanism | `manifest_not_explicit`; provider response independently records that the image reference could not be pulled/resolved | `manifest_not_explicit`; provider response independently records that the image reference could not be pulled/resolved |
| Runtime manifestation | Manifest declares `ImagePullBackOff`; the captured provider state observed an unready Pending Pod with `ErrImagePull` | Manifest declares `ImagePullBackOff`; the captured provider state observed two unready Pending Pods with `ErrImagePull` |
| Operational impact | Failed Pod plus ownership roll-up; healthy unrelated Pod and Service remained ready, with one Ready endpoint | Two failed backend Pods, ownership roll-up, and root Service with zero Ready endpoints; unrelated Pod/Service remained healthy |

The manifest does not separately declare a mechanism sentence, so CA-0 does
not manufacture one from the runtime manifestation. Provider error details are
reported as independent observations.

## 4. Cause fingerprint contract

Version: `eval-cause-fingerprint-v1`.

Fields: `provider`, `entity_kind`, `canonical_entity_id`,
`provider_native_entity_id`, `mutation_family`, `changed_field`,
`before_value_ref`, `before_value_hash`, `after_value_ref`,
`after_value_hash`, `initiating_event_id`, `source_change_id`,
`scenario_logical_entity`, `scenario_logical_change`, `evidence_source`, and
`fingerprint_completeness`.

Expected truth uses only the manifest, execution receipt, and Kubernetes
provider verification. Each actual layer is fingerprinted independently;
missing upstream fields remain null. The explicit Kubernetes image-field
equivalence is provider API
`spec.template.spec.containers[0].image` ↔ graph diff `properties.images`.

## 5. Evaluation cause-match contract

Version: `eval-cause-match-v1`.

It compares provider, normalized kind, canonical/provider UID identity,
mutation family, explicit field equivalence, canonical before/after hashes,
and durable event/change IDs when both sides expose them. Results are `exact`,
`compatible_partial`, `entity_match_mutation_mismatch`,
`mutation_match_entity_mismatch`, `insufficient_structure`, or
`different_cause`.

Titles, fuzzy text, substrings, embeddings, LLMs, and display-name similarity
are not inputs. This comparator is forensic only and is not wired into EVAL-1
PASS/FAIL.

## 6. blast-01 forensic chain

- Manifest: expected root alias `root_deployment`, change
  `root_deployment_image_change`, affected alias `failed_pod`, and failure mode
  `ImagePullBackOff`. Its accepted display selector requires the root
  Deployment and tokens `deployment configuration changed`.
- Receipt: action `causal_bad_image` targeted Deployment `failing-app` in
  `topo-eval-blast-01-70937c95`; UID
  `50a4b35e-4d99-430a-8659-591026e43fc3`; generation 2 → 3; resourceVersion
  `553633`; executed `2026-08-24T01:51:16.709906+00:00`.
- Provider: image changed from `nginx:1.27-alpine` to the run-specific invalid
  image. The failed Pod was unready with `ErrImagePull`; the owner chain was
  valid; the unrelated healthy Pod was Ready and its Service retained one
  Ready endpoint. Intent, receipt, and provider match.
- NormalizedChange: `change:59527a6cba1c9febd49107a1772de21d`,
  `entity_updated`, category `scaling`, importance `high`, source
  `snapshot-diff`; exact Deployment canonical ID and UID; structured fields
  `properties.available_replicas` and `properties.images`; full before/after;
  fingerprint
  `9c942a90a018a64f3d2ff000eade25d0812c2753ff39b05cab18e5469440cd49`.
- ChangeRecord: the `changes` row preserved the complete normalized payload,
  fingerprint, entity, before/after, source IDs, snapshots, and TC-3 metadata.
  Structured cause match: `exact`.
- ChangeEvent: `change-event:8f4d3beef4cfaf8a408dc285211d0ef8`,
  origin change above, source `topology_diff`, title
  `KubernetesDeployment updated`. Its metadata preserves both changed fields,
  before/after, entity reference, normalized fingerprint, and lineage.
  Structured cause match: `exact`.
- IncidentChangeCandidate: same durable event; raw rank 11, raw score 55.20,
  directly linked to the exact Deployment. Candidate fingerprint: `exact`.
- `causal-candidate-v1`: role `observed_resource_mutation`, eligibility
  `primary_eligible`, eligible rank 1, selected for hypothesis.
- `causal-relevance-v1`: `semantic_path`, semantic
  `control_ownership`, topology component 0.65. The pinned path is Deployment
  --`owns/forward`→ ReplicaSet --`owns/forward`→ failed Pod, using
  `relationship:00e9c64ab370bd6658bd03a4` and
  `relationship:4fb9d9f280f6d5c565b0addf`.
- 13C: the expected event is the only primary-eligible winner and final rank 1
  at 60.33.
- TC-4: 9 supporting, 0 contradicting, 0 missing claims. Evidence covers the
  source change, exact identity/linkage, temporal precedence, runtime failure,
  two topology hops, and provenance for both hops.
- Root representation: analysis
  `causal-analysis:62662cab4eb3afd112a8f3aaefb86eb1` points to the exact
  event and Deployment root; the chain reaches affected Pod
  `k8s:docker-desktop:pod:ba9aa445-1cdf-41db-a36f-0e0cd4fa17f5` and the
  incident. Direct display title is generic, but the durable event reference
  dereferences to an `exact` cause fingerprint.
- Evaluator: entity alias matching succeeds; title tokens do not. It therefore
  reports Top-1 false and truth absent from Top-3 despite the exact structured
  root event.

## 7. blast-01 FIRST DIVERGENCE

`EVALUATOR_CAUSE_MATCH_DEFECT` at `evaluator_cause_match`.

Every earlier layer preserves the initiating mutation. The current evaluator
reduces the accepted cause to entity alias plus display-title tokens and does
not compare the structured `changed_fields`/before/after reached by
`root_event_id`.

## 8. blast-01 downstream consequences

The accepted EVAL-1 artifact records both `root_cause_top1_correct=false` and
`root_cause_top3_contains_truth=false`, producing overall FAIL. The prior
baseline consequently described this as product selection/ranking failure.
CA-0 demonstrates that no different candidate outranked the truth: the exact
truth event is rank 1. The generic title remains a product readability
limitation, but it is not the first loss of structured cause identity.

## 9. blast-03 forensic chain

- Manifest: expected root alias `root_deployment`, change
  `root_deployment_image_change`, affected alias `failed_pod_1`, and failure
  mode `ImagePullBackOff`; the accepted display selector again requires
  `deployment configuration changed`.
- Receipt: `causal_bad_image` targeted Deployment `failed-backend` in
  `topo-eval-blast-03-eaba976d`; UID
  `d0134b9e-f94f-4581-9cc4-e48966c666fb`; generation 2 → 3;
  resourceVersion `553866`; executed
  `2026-08-24T01:52:02.297881+00:00`.
- Provider: the image changed from `nginx:1.27-alpine` to the run-specific
  invalid image. Both selected Pods were unready with `ErrImagePull`; the
  owner chain was valid; the root Service had zero Ready endpoints; the
  unrelated Pod was Ready and unrelated Service had one Ready endpoint.
- NormalizedChange: `change:3c8a4acdc97fcf0c5c2b4fcd5850faa8`,
  `entity_updated`, category `scaling`, importance `high`, source
  `snapshot-diff`; correct Deployment identity; structured availability and
  image changes with full before/after; fingerprint
  `7388e6479e0938b3893df4e3d492e593c7d6f518417ee3a8ee891fc793e0bb56`.
- ChangeRecord: complete normalized payload and TC-3/source/snapshot metadata
  persisted. Structured cause match: `exact`.
- ChangeEvent: `change-event:9f95cfc9be3353c6d15bf91dd611639e`,
  source `topology_diff`, generic title `KubernetesDeployment updated`, exact
  structured mutation metadata and origin change. Match: `exact`.
- IncidentChangeCandidate: same event, raw rank 23, raw score 55.20. Candidate
  fingerprint: `exact`.
- `causal-candidate-v1`: `observed_resource_mutation`, `primary_eligible`,
  eligible rank 1, selected.
- `causal-relevance-v1`: `semantic_path`, `control_ownership`, topology 0.65;
  Deployment --`owns/forward`→ ReplicaSet --`owns/forward`→ affected Pod via
  `relationship:a8549c7d28d9c4eacf41c960` and
  `relationship:7db0e39e0bcc4ce097a584a4`.
- 13C: expected event wins final rank 1 at 60.33.
- TC-4: 9 supporting, 0 contradicting, 0 missing, with the same seven claim
  classes and two path/provenance items.
- Root representation: analysis
  `causal-analysis:f735c686c80297a75b0e108f777edb01` points to the exact
  event and Deployment; affected entity is
  `k8s:docker-desktop:pod:7ae4a654-e586-4341-95de-110e8e895322`.
  Dereferenced root match: `exact`; display title: generic.
- Evaluator: entity matching succeeds but required title tokens fail, so both
  Top-1 and Top-3 truth metrics are false.

## 10. blast-03 FIRST DIVERGENCE

`EVALUATOR_CAUSE_MATCH_DEFECT` at `evaluator_cause_match`.

No intent, orchestration, provider, normalization, persistence, event,
candidate, relevance, ranking, ledger, or structured root-reference divergence
precedes it.

## 11. blast-03 downstream consequences

Overall EVAL-1 remains FAIL on the two causal-match assertions even though the
exact initiating event is the winning hypothesis. This does not affect the
correct BR-1 blast result. The generic title can still be improved in a
separate product presentation block, but ranking or title changes are not the
repair boundary established by CA-0.

## 12. Shared-root analysis

`SHARED_ROOT_DEFECT = true`.

Both scenarios produce an exact image-field mutation in NormalizedChange,
ChangeRecord, ChangeEvent, candidate, and winning root event. Both then expose
the generic display title `KubernetesDeployment updated`. The evaluator uses
manifest title-token requirements (`deployment configuration changed`) plus
entity matching instead of the exact structured root event, so the same
abstraction mismatch rejects both.

## 13. Structured expected vs actual cause fingerprints

| Field | blast-01 expected / winning event | blast-03 expected / winning event |
|---|---|---|
| Provider | kubernetes / kubernetes | kubernetes / kubernetes |
| Kind | Deployment / Deployment | Deployment / Deployment |
| Provider UID | `50a4b35e…3fc3` / same | `d0134b9e…66fb` / same |
| Canonical ID | expected null / `k8s:docker-desktop:deployment:50a4b35e…3fc3` | expected null / `k8s:docker-desktop:deployment:d0134b9e…66fb` |
| Mutation | field_change / field_change | field_change / field_change |
| Field | provider image path / `properties.images` (explicit equivalent) | provider image path / `properties.images` (explicit equivalent) |
| Before | `nginx:1.27-alpine` / same | `nginx:1.27-alpine` / same |
| After | run-specific invalid image / same | run-specific invalid image / same |
| Event ID | expected null / `change-event:8f4d…0ef8` | expected null / `change-event:9f95…639e` |
| Source change | expected null / `change:5952…e21d` | expected null / `change:3c8a…faa8` |
| Match | `exact` | `exact` |

Expected canonical/event/change IDs remain null because independent provider
truth must not borrow Topo identifiers.

## 14. 13C component tables

| Scenario | Raw rank | Eligible rank | Candidate ×0.40 | Topology ×25 | Temporal ×15 | Kind prior ×10 | Lineage ×10 | Final/rank |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| blast-01 | 11 | 1 | 22.08 | 16.25 | 15.00 | 7.00 (`scaling` 0.70) | 0.00 | 60.33 / 1 |
| blast-03 | 23 | 1 | 22.08 | 16.25 | 15.00 | 7.00 (`scaling` 0.70) | 0.00 | 60.33 / 1 |

Formula, priors, weights, tie-breaking, and ranks were not modified.

## 15. TC-4 evidence comparison

Each winning/expected hypothesis is the same hypothesis and has:

| Claim type | Supporting count | Contradicting | Missing |
|---|---:|---:|---:|
| `entity_linkage` | 1 | 0 | 0 |
| `identity_resolution` | 1 | 0 | 0 |
| `relationship_provenance` | 2 | 0 | 0 |
| `runtime_failure` | 1 | 0 | 0 |
| `source_change` | 1 | 0 | 0 |
| `temporal_precedence` | 1 | 0 | 0 |
| `topology_path` | 2 | 0 | 0 |

`artifact_provenance` and `event_lineage` are not represented and are not
required by these manifests. No unsupported evidence was added.

## 16. Product-vs-evaluator determination

| Scenario | Primary owner | Determination |
|---|---|---|
| blast-01 | evaluator | Product selects and durably references the exact initiating mutation; current evaluator rejects its generic title. |
| blast-03 | evaluator | Same structured cause is rank 1; current title-token matcher rejects it. |

This does not claim that the generic product title is ideal. It determines the
first boundary responsible for the measured EVAL-1 failures.

## 17. Historical correctness verification

- blast-01 incident, analysis, and TC-4 ledger all reference pinned snapshot
  `snapshot:agent:592a53d978f7ce3d8ad5a100715eb5c4`.
- blast-03 incident, analysis, and TC-4 ledger all reference pinned snapshot
  `snapshot:agent:2634756be36373a4569f8a78c771e4a6`.
- Both winning ChangeEvents carry complete TC-3 effective, observed, recorded,
  and source-time metadata with `temporal_version=tc3.v1`.
- No latest/current topology fallback was used. The root path and ledger use
  the incident-pinned snapshot.

## 18. Pre-V1 compatibility handling

No migration, adapter, obsolete SQLite decoder, or legacy-product fallback was
added. Every forensic run created clean isolated current-model state. The
scenario truth and manifests remain the regression assets; disposable SQLite
state was deleted after bounded read-only capture.

## 19. Files created

- `evaluation/cause_fingerprint.py`
- `evaluation/causal_forensics.py`
- `evaluation/tests/test_causal_forensics.py`
- `docs/architecture/evaluation/cause-fingerprint-v1.md`
- `docs/architecture/evaluation/cause-forensic-bundle.schema.json`
- `docs/architecture/evaluation/baselines/ca-0-remaining-causal-failure-audit.md`

## 20. Files modified

- `evaluation/runner.py`: optional pre-cleanup read-only persistence capture
  and ignored bundle generation.
- `evaluation/__main__.py`: optional `--forensic-output-dir` argument.

Normal runner defaults and evaluator output are unchanged.

## 21. Product diff

No changes under `backend/app/`, `backend/tests/`, `agent/src/`, `frontend/`,
or `cli/src/`. No product model, persistence, API, reasoning, title, or policy
was changed.

## 22. Evaluation tests

26 CA-0 tests cover independent expected derivation; no downstream backfill;
exact field/value matching; field and entity mismatches; generic-title
insufficiency; partial structure; no fuzzy/title/LLM/embedding matching;
first-divergence ordering and downstream precedence; no-divergence behavior;
classification coverage; product and evaluation version serialization;
deterministic JSON; no product-service imports; manifest independence; no
scenario-specific outcomes; no old-artifact dependency; current-model SQLite
capture; generic title versus exact root reference; pinned topology/TC-3;
product-diff guard; contract-family separation; and machine-readable schema
plus runtime bundle validation.

## 23. Full regressions

- Backend compile: PASS.
- Backend pytest: **608 passed**, 1 existing Starlette deprecation warning,
  18.54s.
- Agent compile: PASS.
- Agent pytest: **15 passed**, 1.08s.
- Evaluation compile: PASS.
- Evaluation pytest: **96 passed** = 70 accepted + 26 CA-0, 5.00s.
- Frontend/CLI were not modified and were not run, per CA-0 scope.

## 24. Manifest hash verification

Pre- and post-CA-0 Git blob hashes are identical:

| Manifest | SHA-1 |
|---|---|
| sentinel-a | `599ba19827d5097fded3f52264cad8dd35abb839` |
| sentinel-b | `f404607eaca904baac362edb2365fa53652565fe` |
| sentinel-c | `9bb3c201b190708224770a30ec9c23939623f683` |
| sentinel-d | `e7e2a8f4e2cde066bee209191ec27304a41193f7` |
| blast-01 | `2f292f5ee1c116d2c2c832bc2165a61bc13dedc5` |
| blast-02 | `695d0feda176f26c7e601a57060f4ad0d29310a9` |
| blast-03 | `0f9974a4a5f4a08d6b01d2e02be319698175f6c1` |

## 25. Generated artifacts / cleanup

Ignored standard results include the pre-tooling and final forensic runs.
Ignored forensic bundles are under `evaluation/results/forensics/`:

- `blast-01-70937c95-causal-forensics.json`
- `blast-03-eaba976d-causal-forensics.json`

The bundles contain the product commit, version families, environment,
expected/actual layer fingerprints, persistence records, component breakdown,
TC-4 summary, root reference, evaluator outcome, and one first divergence.
The runner cleanup completed for both disposable Kubernetes namespaces; the
isolated databases were removed after read-only capture. No disposable
artifact is tracked.

## 26. Proposed NEXT repair boundary

Because the first divergence for both scenarios is
`EVALUATOR_CAUSE_MATCH_DEFECT`, the next separately scoped block should target
the evaluator cause-match contract. Architecture review should decide whether
`eval-cause-match-v1` (or a reviewed successor) replaces title-token matching
for Top-1/Top-3 metrics. It must remain independent of product reasoning and
must get permanent regressions. CA-0 does not implement that repair.

## 27. Questions requiring architect decision

No decision is required to identify the first divergence. A later evaluator
repair requires one explicit approval: whether exact structured provider/entity
/mutation/field/value agreement is the authoritative cause-match definition.
Product title enrichment is a separate presentation question and must not be
coupled to evaluator correctness.

## 28. Git status

Branch: `evaluation/remaining-causal-failure-audit-v1`.

Expected unstaged CA-0 files are the two modified evaluation runner files and
the six untracked evaluation/documentation files listed above. Nothing is
staged, committed, or pushed.

## 29. git diff --check

PASS. Git reports only Windows LF→CRLF notices for the two modified tracked
evaluation files; there are no whitespace errors.
