# LINEAGE-2B.3 — Final Missing Image -> Workload Provenance Baseline

**Status: ACCEPTED MEASUREMENT CANDIDATE**

Date: 2026-08-27

Branch: `evaluation/lineage-2b3-final-baseline-v1`

Accepted repository commit before this documentation checkpoint:
`6530e46c6a1e531c9e0b5edc6d0e3410a1a53527`

Accepted repository summary:
`6530e46 test(evaluation): add missing image workload lineage scenario (#57)`

This documentation-only checkpoint freezes the completed and merged
LINEAGE-2B.3 measurement. It records the existing finalized result family; it
does not rerun the experiment, modify the evaluator or product, regenerate
EAI, rewrite result artifacts, start another broken-lineage scenario, create a
repair, or grant final architecture acceptance.

## 1. Frozen status

| Dimension | Result |
|---|---|
| Scenario | LINEAGE-2B.3 — Missing Immutable Image -> Affected Workload Provenance |
| Construction validity | PASS |
| CONTROL reproduction | PASS |
| Protected truth preservation | PASS |
| Determinism | PASS — 3/3 |
| EAI-1 | PASS / VALID |
| Taxonomy | `NO_DIVERGENCE` |
| First divergence | `NO_DIVERGENCE` |
| Overall verdict | `ROBUST_IN_MEASURED_MATRIX` |

## 2. Governing measured result

When all workload-specific authoritative evidence connecting the exact golden
immutable image to the affected Deployment and Pod was removed, while exact
Commit -> Run -> Image and exact Deployment -> ReplicaSet -> Pod -> failure
truth remained intact, TopoAI did not infer or fabricate the missing Image ->
affected-workload bridge. It did not support exact source-level
`INITIATING_MUTATION` causality.

The measured counterfactual was:

```text
CONTROL

Commit -> Run -> Image -> Affected workload -> Failure

B3

Commit -> Run -> Image
                     X
                     Affected workload -> Failure
```

The frozen post-mutation truth was:

| Boundary or fact | State |
|---|---|
| Commit -> Run | PRESENT / exact |
| Run -> Image | PRESENT / exact / provider-authoritative |
| Image -> affected workload | ABSENT / UNKNOWN |
| Workload identity | PRESENT / exact |
| Runtime failure | PRESENT / exact |
| Incident and pin | PRESENT / exact |

## 3. Counterfactual semantic interpretation

B3 did not model a Kubernetes Pod that literally had no image. It modeled a
retained-evidence world in which Topo no longer possessed workload-specific
image observations sufficient to prove that the golden image was requested or
used by the affected workload.

The real artifact still existed, its source/build provenance still existed,
the workload still existed, and the workload still failed. Only the
evidentiary association between the artifact and affected runtime was
unavailable. No alternate image, placeholder, partial provider observation,
synthetic relationship, or replacement Evidence was created.

## 4. Frozen seed and isolation

| Field | Frozen value |
|---|---|
| Seed | `evaluation/results/lineage/post-sc4/topo-product-32695735269.db` |
| SHA-256 | `9f3918a027c6d9a7bbd679495c48b387c9a1ac8c86141f85cf8b4495cd00b69f` |
| SQLite `quick_check` | `ok` |
| SQLite `integrity_check` | `ok` |
| Source access | `mode=ro&immutable=1`; `PRAGMA query_only=ON` |
| Source seed SHA after measurement | unchanged |

One CONTROL and three B3 copies began byte-identical to the frozen seed. All
writes were confined to isolated temporary copies.

## 5. Snapshot identity and historical correctness

The measured snapshot identity model is a historical observation-record ID
using the observation timestamp plus a random suffix. It is not
content-addressed, so retaining the same observation-record identity while
modeling incomplete retained evidence was compatible with the current
snapshot contract.

| Field | Result |
|---|---|
| Snapshot ID content-addressed | NO |
| Construction blocker | NO |
| Pinned snapshot | `snapshot:actions-enriched:20260826T051031Z:2d8416d3` |
| Replacement snapshot minted | NO |
| Latest-topology fallback | NO |

The snapshot ID, collection time, scope, incident boundary, incident pin,
owner chain, and unrelated metadata remained unchanged.

## 6. Frozen identities

| Identity | Frozen value |
|---|---|
| Repository | `1278498159 / ShaikMuhammadSami/Topo_Ai` |
| Commit | `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe` |
| Source event | `change-event:20a8946c8c445153d85c90ee2166d487` |
| Source mutation | `source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633` |
| Actions Run | `32695735269` |
| Run attempt | `1` |
| BuildArtifactEvidence E1 | `build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb` |
| Run -> Image | `rel:63f5cd5dfce59d148ae5` |
| Run -> Image Evidence | `evidence:github-actions-build:c9b6d53cf66facfb444c8ae0` |
| Golden image | `artifact:container-image:sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed` |
| Deployment | `k8s:docker-desktop:deployment:bd4cfb7a-d32a-43bf-bf82-366e3fd8841a` |
| ReplicaSet | `k8s:docker-desktop:replicaset:200703db-a601-44f0-90ff-63c64cb17162` |
| Affected Pod | `k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168` |
| Original Deployment -> Image | `rel:496906e3e345259910c9` |
| Original Pod -> Image | `rel:0548ac3e949f44b3569c` |
| Shared image Evidence | `evidence:container-images:1d88e6b0-6706-44d7-80d4-5aaa4c4d1d56` |
| Deployment -> ReplicaSet | `rel:57555e411f2db29864c2` |
| ReplicaSet -> Pod | `rel:9c8db862d53bac71327f` |
| Failure signal | `signal:kubernetes-event:docker-desktop:ad733dcc-a026-424f-8984-6ed30108eec1` |
| Incident boundary | `2026-08-26T05:09:49Z` |

## 7. Symmetric fresh-analysis reset

No explicit product force-recompute mechanism was available. CONTROL and all
three B3 repetitions received the same evaluation-only isolated-copy reset:

- delete the incident's `causal_analyses` records;
- delete matching legacy `incident_analyses` records;
- clear `latest_analysis_id`;
- clear `top_hypothesis_title`; and
- clear `top_hypothesis_score`.

CONTROL deleted one causal analysis and zero legacy analyses. The other copies
had identical reset results. No authoritative evidence was deleted by the
reset.

Reset semantic hash for all four copies:
`8758c963faa3449201e192197b34b3881441ce908b43a69d23cf010ad9ae05d2`.

Reset symmetry: **PASS**.

## 8. Exact B3 mutation

### Deployment

- cleared the affected container's requested-image compatibility value;
- cleared `image_id` and `runtime_status_image` compatibility values in the
  measured evaluator projection;
- changed nested SC-3 requested/runtime observations to the existing
  `missing` representation;
- cleared resolved artifact identity and basis; and
- cleared relevant image Evidence references.

### Deployment annotation

The evaluator parsed
`kubectl.kubernetes.io/last-applied-configuration` structurally, located the
affected container by exact name, and removed only:

```text
spec.template.spec.containers[name=fixture].image
```

Canonical JSON serialization was used. All unrelated annotation semantics
remained unchanged. Their before/after semantic fingerprint was:

```text
a6470793daf6dee399020e42d82e2e3723ea16e263f4aceda4b5285c933804c9
```

### Pod

- cleared the requested image and changed the nested requested observation to
  `missing`;
- cleared runtime imageID and changed its nested observation to `missing`;
- cleared runtime-status image and changed its nested observation to
  `missing`;
- cleared resolved artifact identity and basis; and
- cleared relevant image Evidence references.

### Derived claims and Evidence

Removed relationships:

- `rel:496906e3e345259910c9` — Deployment -> Image;
- `rel:0548ac3e949f44b3569c` — Pod -> Image.

The shared container-image Evidence
`evidence:container-images:1d88e6b0-6706-44d7-80d4-5aaa4c4d1d56` was removed
because it supported only those two removed claims. No synthetic replacement
Evidence was created.

## 9. Snapshot consistency

| Counter | Before | After |
|---|---:|---:|
| Entities | 9 | 9 |
| Relationships | 12 | 10 |
| Evidence | 5 | 4 |
| `container_image_artifacts.count` | 1 | 1 |
| `container_image_artifacts.relationships` | 2 | 0 |

Only structural counters whose old meanings became false were updated. The
golden ContainerImage remained.

## 10. Recursive co-reference and construction proof

The recursive scan was deliberately workload-specific. Its scope comprised:

- the affected Deployment;
- the affected Pod;
- their image relationships;
- relevant image Evidence;
- image metadata; and
- cached causal state.

| Audit | Result |
|---|---:|
| Pre-mutation semantic matches | 106 |
| Post-mutation semantic matches | 0 |
| Workload-specific golden image authority remaining | 0 |
| Alternative Image -> workload authority | 0 relationships |
| Broken-hop proof | PASS |
| Construction blocker | NO |

The golden digest was not required to disappear globally. It remained
legitimately in BuildArtifactEvidence E1, the exact Run -> Image claim, and the
standalone ContainerImage.

## 11. Protected source/build and runtime truth

After the B3 cut, the exact source/build chain remained:

```text
Commit -> Run -> Image
```

The following survived unchanged:

- source-file mutation;
- exact provider-native Commit -> Run;
- BuildArtifactEvidence E1;
- exact Run -> Image and provider Evidence;
- golden ContainerImage;
- Deployment, ReplicaSet, and Pod identities;
- Deployment -> ReplicaSet -> Pod UID owner chain;
- non-image workload/runtime fields;
- runtime failure;
- incident, boundary, primary signal, and historical topology pin.

The workload identity, owner chain, failure, incident, and historical scope
were not removed to make the scenario pass.

## 12. Protected fingerprints

Every protected before/after projection was equal:

| Protected truth | SHA-256 |
|---|---|
| Source mutation | `a8a4eba0ab5a43feba9472827445cfd7341686ae09118eb606f4a66df0338d54` |
| Commit -> Run | `0f016ee67aee0b452319080ba8c22a9874ff92fa0f942db8399bb2e0c3e2903e` |
| BuildArtifactEvidence E1 | `f54c56fa1941949f1cfa7bfa73dcfb55f7083ece6bebcb7ce56116b820ad7c65` |
| Run -> Image | `4ceabe476da97f76175b911c32c5948f283a235a70ae26d9c8855c7de105f05a` |
| ContainerImage | `8d912d191959d894b043a83fb606371b149d72559459f272f8e4f6f951e0de5e` |
| Deployment protected projection | `8421805a9c6b385dbb54c35b19849e204999d32f925258975bc2829cca44a361` |
| ReplicaSet | `39a34188d5d9639c80ce3c94783b3baa809965230a3b4f945c3bf8f2b4a06241` |
| Pod protected projection | `938974f0739283f1ad4736163a46ed7dcc11340608361efd82678521a3e87ece` |
| Owner chain | `5cbcb2c519596c628f1467a3f3df1d5e9fce10506acd99cab6aff16f5d70fc91` |
| Runtime failure | `a86f1241e0bf2c3e02c26bf02116d5b4ec025a43656ffa9142ac322e011f8c28` |
| Incident/pin | `008c80918c262e1687c630ce47a6513eb17acef314088338de1389834efe3f4c` |
| Annotation unrelated semantics | `a6470793daf6dee399020e42d82e2e3723ea16e263f4aceda4b5285c933804c9` |

Protected-truth preservation: **PASS**. The changed protected-fingerprint list
was empty.

## 13. CONTROL result

| Dimension | CONTROL result |
|---|---|
| Fresh analysis | `causal-analysis:9da0b88a484768cc36d93e28a3756989` |
| Old analysis reused | NO |
| Golden source admission | YES |
| Path A | not admitted; source age approximately 2827.77 minutes |
| Path B | admitted |
| SC-2 | admitted / `exact_immutable_lineage` |
| SC-4 | `exact_immutable_lineage_anchor` |
| Provider bridge | valid |
| Relevance anchor | golden ContainerImage |
| TC-4 supporting | 5 |
| TC-4 contradicting | 0 |
| TC-4 missing | 0 |
| TC-4 unknown | 0 |
| AR-2 | `supported_under_current_model` |
| Diagnostic projection | `causal-hypothesis:2ac8304fd400995d86bff0b3750fd436` |
| Supported projection | same hypothesis |
| Supported Top1 | golden source hypothesis |
| Semantic level | `INITIATING_MUTATION` |
| Raw score | 9.8 |
| Final score | 30.17 |
| Legacy confidence | 0.3017 |
| Calibration | `not_calibrated` |
| Reproduction | PASS |

The five TC-4 claim types were `relationship_provenance`, `runtime_failure`,
`source_change`, `temporal_precedence`, and `topology_path`.

## 14. B3 result

All three B3 repetitions produced fresh analysis:

```text
causal-analysis:85fdb84639362caecb97bcdbde926eee
```

The old analysis was not reused.

| Dimension | B3 result |
|---|---|
| Raw golden source discovery | NO |
| Path A | not admitted |
| Path B | not admitted |
| SC-2 | incomplete / `immutable_image_missing` |
| Runtime image resolution | no authoritative immutable image for affected workload |
| Persisted lineage context | incomplete audit; no canonical change, container scope, lineage path, or mutation set |
| SC-4 | not evaluated |
| Relevance anchor | null |
| Topology path | none |
| Candidate-specific TC-4 ledger | absent |
| TC-4 supporting | 0 |
| TC-4 contradicting | 0 |
| TC-4 missing | 0 |
| AR-2 | not evaluated |
| AR-2 reason | candidate admission stopped safely at `immutable_image_missing` |
| Diagnostic projection | empty |
| `top_hypothesis` | null |
| Supported projection | empty |
| Supported Top1 | null |
| Most-specific supported semantic level | `NONE` |
| Golden `INITIATING_MUTATION` supported | NO |
| Raw score | null |
| Final score | null |
| Confidence | null |
| Calibration | null |

Missing or unknown evidence was not converted into contradiction. Because no
candidate-specific source hypothesis existed, no candidate-specific ledger was
produced. The evaluator did not invent a missing claim to satisfy adversarial
ground truth.

## 15. Fabrication and unsafe specificity

| Audit | Result |
|---|---|
| Fabricated Image -> workload provenance count | 0 |
| Fabrication surfaces | none |
| Unsafe exact-source specificity count | 0 |
| Unsafe surfaces | none |
| Evidence semantics | PRESERVED |

Topo did not reconstruct victim-artifact linkage using source/build
provenance, namespace, workload names, timestamps, score, latest topology,
provider or registry fallback, Kubernetes queries, an LLM, embeddings, fuzzy
matching, or stale analysis.

## 16. Forensic explanation

CONTROL had the complete Commit -> Run -> Image -> affected-runtime path and
supported the exact source mutation at `INITIATING_MUTATION`.

B3 retained Commit -> Run -> Image and separately retained Deployment ->
ReplicaSet -> Pod -> failure, but removed every persisted authoritative
surface proving Image -> affected Deployment/Pod. SC-2 could therefore not
resolve an authoritative immutable image for the affected runtime and recorded
`incomplete / immutable_image_missing`.

The source candidate was not admitted. SC-4 did not construct a
source/image/runtime relevance path, no candidate reached AR-2 support, and no
diagnostic or supported source hypothesis survived. Topo did not fabricate the
missing relationship. The most-specific supported level safely moved from
`INITIATING_MUTATION` to `NONE` while unrelated source, build, workload,
ownership, failure, incident, and historical-topology truth remained exact.

## 17. Determinism

| Dimension | Frozen value |
|---|---|
| Repetitions | 3 |
| Fresh byte-identical copies | YES |
| Volatile fields normalized | `generated_at`, temporary copy path |
| Normalized semantic hash, repetition 1 | `920573096bbfb0a62bc24349b9ecedcef4fc05ea70d75e05cf677af0f9db5963` |
| Normalized semantic hash, repetition 2 | `920573096bbfb0a62bc24349b9ecedcef4fc05ea70d75e05cf677af0f9db5963` |
| Normalized semantic hash, repetition 3 | `920573096bbfb0a62bc24349b9ecedcef4fc05ea70d75e05cf677af0f9db5963` |
| Result | PASS — 3/3 |

Semantic mutation, construction, evidence, candidate, relationship, support,
score, projection, and protected-truth fields remained inside the normalized
identity.

## 18. EAI-1 result identity

| Dimension | Frozen value |
|---|---|
| Result root | `evaluation/results/lineage/adversarial/lineage-2b-missing-image-workload/` |
| Total files | 25 |
| EAI-covered ordinary files | 24 |
| `artifact-hashes.json` SHA-256 | `e3f4f96e68a34879ab9ef3ff623a3fe8e5b11d681d5819bc59fe6b929cdf9baf` |
| EAI contract | `evaluation-artifact-integrity-v1` |
| EAI `tree_sha256` | `4fad555ab1bb251b7883737d24c0249e25caaba074217f1b0ad7cdb2f640d106` |
| Verification | VALID / PASS |
| SQLite transient files | none |
| EAI generated after ordinary artifacts | YES |

This documentation checkpoint does not regenerate EAI or modify the finalized
result family.

## 19. Frozen test and regression results

These are the completed measurement results; they were not rerun for this
documentation-only checkpoint.

| Check | Frozen result |
|---|---|
| Focused B3 | 94 passed |
| Evaluation | 912 passed, 3 skipped |
| Evaluation skip reason | accepted Windows EAI symlink-permission cases |
| Backend | 976 passed, 1 accepted deprecation warning |
| Agent | 15 passed |
| Evaluation compile | PASS |
| `backend/app` compile | PASS |
| `agent/src` compile | PASS |
| Measurement `git diff --check` | PASS |

## 20. Product and policy freeze

No product repair was required. The measurement changed no product behavior.

| Scope | Diff |
|---|---|
| Product / `backend/app` | none |
| `backend/tests` | none |
| SC-1 through SC-4 | none |
| AR-1 through AR-3 | none |
| TC-1 through TC-5 | none |
| Candidate or causal ranking | none |
| Lookback | none |
| Confidence or calibration | none |
| Topology traversal or policy | none |
| Agent | none |
| Frontend | none |
| CLI | none |
| Workflow | none |

## 21. Frozen taxonomy and verdict

The exact ordered B3 taxonomy is:

1. `BROKEN_HOP_STILL_PRESENT`
2. `FABRICATED_IMAGE_WORKLOAD_PROVENANCE`
3. `SOURCE_CAUSE_FALSELY_SUPPORTED`
4. `UNSAFE_SOURCE_SPECIFICITY_PRESERVED`
5. `VALID_PRESERVED_EVIDENCE_CORRUPTED`
6. `EVIDENCE_SEMANTICS_DEGRADED`
7. `NONDETERMINISTIC_RESULT`
8. `NO_DIVERGENCE`

Measured taxonomy: `NO_DIVERGENCE`.

First divergence: `NO_DIVERGENCE`.

Final verdict: `ROBUST_IN_MEASURED_MATRIX`.

## 22. Narrow claim boundary

Approved narrow claim:

> In one controlled offline GitHub Actions/BuildKit/Kubernetes lineage
> scenario, TopoAI withheld exact source-level causal attribution when
> authoritative immutable-image-to-affected-workload evidence was removed,
> while preserving exact source/build provenance, workload identity,
> ownership, runtime failure, and incident-pinned historical topology.

This baseline does not claim:

- all deployment-lineage correctness;
- correctness for every Kubernetes workload or image-provenance gap;
- B1 correctness;
- correctness for all B2/B3-like cases;
- B4, B5, or B6 correctness;
- correctness for all providers;
- statistical robustness;
- 100% RCA accuracy;
- production behavior; or
- calibrated causal probability.

## 23. B2 and B3 internal architectural observation

This is an internal observation, not a generalized product claim.

B2 established that exact source attribution did not cross a missing Run ->
Image provider-provenance boundary. B3 established that it did not cross a
missing Image -> affected-workload runtime/deployment-provenance boundary.

Together, in this controlled lineage family, supported source attribution
required continuity across both artifact-production provenance and
artifact-to-affected-runtime provenance. This observation must not be
generalized beyond the measured scenario family.

## 24. Broken-lineage family state

| Scenario | Frozen state |
|---|---|
| B1 | `EXPERIMENT_CONSTRUCTION_BLOCKED`; reason `evidence_model_nonseparable`; measurement `NOT EXECUTED` |
| B2 | `ROBUST_IN_MEASURED_MATRIX`; `NO_DIVERGENCE`; CLOSED |
| B3 | `ROBUST_IN_MEASURED_MATRIX`; `NO_DIVERGENCE`; candidate for CLOSED after baseline review |
| B4 | DEFERRED |
| B5 | NEEDS_REAL_SEED |
| B6 | DEFERRED |

B1 remains construction-blocked and unmeasured; it is not converted into PASS
or FAIL.

## 25. Result immutability and checkpoint boundary

This baseline references the existing finalized B3 result family exactly. It
does not modify or regenerate:

- B3 result artifacts or EAI;
- `artifact-hashes.json`;
- the B3 evaluator or tests;
- the B3 contract;
- the B2 result family or baseline;
- any historical baseline;
- product, backend tests, agent, frontend, CLI, or workflow code; or
- SC, AR, TC, ranking, confidence, lookback, or topology policies.

No B4, B5, B6, AR-4, or causal repair work is authorized by this baseline.
The proposed next action is:

```text
ARCHITECT REVIEW / MERGE B3 FINAL BASELINE
```

