# LINEAGE-1 Final Proven Source-to-Runtime Causal Baseline v1

Date: 2026-08-26

Branch: `evaluation/lineage-1-final-proven-causal-baseline-v1`

Accepted product commit: `42f68835333c71371d3e54033a9bcdd69c1de36d`

LINEAGE-1K verdict: **PROVEN**

First divergence: **`NO_DIVERGENCE`**

Currently failing causal layer: **none**

## 1. Checkpoint purpose

This document permanently preserves TopoAI's first accepted provider-backed,
source-level causal proof before adversarial expansion. It marks the end of the
single-scenario first-divergence repair loop under the current TopoAI truth and
evaluation contracts.

This is a documentation checkpoint only. It does not modify or reinterpret
product code, evaluator code, causal policy, provider state, Kubernetes state,
or the preserved experiment.

## 2. Claim boundary

This is the first accepted source-level causal proof under the current TopoAI
truth/evaluation contracts. It demonstrates **one deterministic controlled
Kubernetes scenario**.

It does not prove:

- generalized Kubernetes RCA;
- statistical reliability;
- calibrated causal probability;
- all source changes;
- all container build systems;
- all Kubernetes failure families;
- cloud RCA;
- Terraform causality;
- autonomous remediation; or
- enterprise readiness.

## 3. Independently established source truth

| Dimension | Accepted truth |
|---|---|
| Healthy parent | `f9b152133a8075428766dd48b3f752b255ec5270` |
| Failure commit | `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe` |
| Changed file | `evaluation/fixtures/lineage-image/runtime-mode.txt` |
| Before | `healthy` |
| After | `fail` |
| Before SHA-256 | `63745aef95742025c6d7a1b4fc0e7107e6f3c3eb2e0cb290f33c46f176e6740d` |
| After SHA-256 | `2056a28ea38a000f3a3328cb7fabe330638d3258affe1a869e3f92986222d997` |
| Source event | `change-event:20a8946c8c445153d85c90ee2166d487` |
| Source mutation | `source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633` |
| Source effective time | `2026-08-24T06:02:03Z` |

This truth was established independently of Topo.

## 4. Provider truth

| Dimension | Accepted truth |
|---|---|
| Repository | `ShaikMuhammadSami/Topo_Ai` |
| Repository ID | `1278498159` |
| GitHub Actions run | `32695735269` |
| Run attempt | `1` |
| Provider build artifact | `9508752475` |
| Provider receipt artifact | `9508751900` |
| Immutable OCI index | `sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed` |
| Executable linux/amd64 descriptor | `sha256:48d64298dd20b76cb12dbc351d457d136d11e7a465547d4e7f9f2b2d227ae9c7` |

## 5. Independent runtime truth

| Dimension | Accepted truth |
|---|---|
| Exit code | `42` |
| Restart count | `>= 1` |
| Runtime state | `CrashLoopBackOff / BackOff` |
| Termination reason | `Error` |
| Deployment desired | `1` |
| Deployment ready | `0` |
| Deployment available | `0` |

This runtime truth was established independently of Topo. Topo was not used to
construct the runtime receipt or expected failure truth.

## 6. Incident truth

| Dimension | Accepted observation |
|---|---|
| Failure signal | `signal:kubernetes-event:docker-desktop:ad733dcc-a026-424f-8984-6ed30108eec1` |
| Incident | `incident:docker-desktop:topo-eval-lineage-causal-32695735269:workload-lineage-causal-fixture:1afbac4ef76921c7aca2c3d3` |
| Incident boundary | `2026-08-26T05:09:49Z` |
| Pinned topology | `snapshot:actions-enriched:20260826T051031Z:2d8416d3` |
| Affected Pod | `k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168` |

The incident, causal analysis, and TC-4 evidence ledger all referenced the same
incident-pinned topology snapshot. No latest-topology fallback was used.

## 7. SC-1 result: provider-authentic source identity

SC-1: **PASS**

Provider-authentic source-file mutation identity remained exact. The repository,
parent and failure revisions, path, before/after blob identities, content hashes,
and bounded semantic values matched the independently established source truth.

`SOURCE_CHANGE_IDENTITY_WRONG` remains eliminated.

## 8. SC-3 result: requested-versus-runtime image identity

SC-3: **PASS**

Contract: `kubernetes-container-image-identity-v1`

Requested immutable identity:

```text
ghcr.io/shaikmuhammadsami/topo_ai-topo-lineage-eval@sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed
```

Runtime status image remained separately represented as:

```text
sha256:a3392fbeae192e861a3df42d25acf050c45a657c8e277a41258332baa9451f53
```

The requested image, runtime status image, and runtime image ID remained
semantically distinct. Deployment and Pod requested-artifact identities agreed.

`immutable_image_identity_incomplete` remains eliminated.

## 9. SC-2 result: exact immutable-lineage admission

SC-2: **PASS**

| Dimension | Accepted observation |
|---|---|
| Candidate policy | `causal-candidate-v1` |
| Admission policy | `causal-candidate-admission-v2` |
| Source-to-incident gap | `2827.77` minutes |
| Ordinary Path A | `180` minutes |
| Source inside Path A | no |
| Candidate count | `1` |
| Exact source occurrence | `1` |
| Admission basis | `exact_immutable_lineage` only |
| Admission state | `admitted` |
| Timestamp rewrite | none |
| Lineage ranking bonus | none |
| Canonical source candidates | one |
| Attached SC-1 mutation bundle | one complete mutation |

The original source effective time remained unchanged. Admission did not
fabricate a temporal basis or duplicate the candidate.

`CAUSAL_CANDIDATE_MISSING` remains eliminated.

## 10. SC-4 result: lineage-aware causal relevance

SC-4: **PASS**

| Dimension | Accepted observation |
|---|---|
| Relevance policy | `causal-relevance-v2` |
| Topology traversal sub-policy | `causal-relevance-v1` |
| `candidate_entity_id` | `null` |
| Resolution basis | `exact_immutable_lineage_anchor` |
| Relevance anchor | `artifact:container-image:sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed` |
| Anchor kind | `ContainerImage` |
| Bridge state | `valid` |
| Bridge score contribution | `0.0` |
| Bridge source revision | `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe` |
| Bridge producer run | `32695735269` |
| Bridge path | `lineage-path:b144dec40cb0d248bf46f387c989df97d67529fb` |
| Provider build evidence | `build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb` |

The null `candidate_entity_id` is correct. The candidate remains a source/change
domain event rather than being falsely represented as a topology entity. The
exact immutable ContainerImage is recorded separately as the relevance anchor.

The accepted incident-time topology path was:

```text
ContainerImage
    ->
affected Pod
```

| Path dimension | Accepted observation |
|---|---|
| Relationship | `rel:0548ac3e949f44b3569c` |
| Traversal | reverse traversal of Pod `uses` Image |
| Semantic | `artifact_lineage` |
| Hops | `1` |
| Topology component | `0.85` |

The exact anchor existed in the incident-pinned snapshot. SC-4 performed no
provider re-traversal and used no latest/current-topology fallback.

`CAUSAL_RELEVANCE_PATH_MISSING` remains eliminated.

## 11. Score semantics

| Dimension | Accepted value |
|---|---:|
| Candidate raw score | `9.8` |
| Current causal score | `30.17` |
| Bridge contribution | `0.0` |

The unchanged score formula was:

```text
candidate.score * 0.40
+ topology_component * 25
+ temporal_component * 15
+ kind_prior * 10
+ event_lineage_component * 10
```

There was no lineage bonus, bridge bonus, or forced Top1. The topology component
became non-zero because a legitimate relevance anchor made the existing topology
path semantics available. The ranking formula itself was not modified.

## 12. TC-5 confidence semantics

| Dimension | Accepted value |
|---|---|
| Reported heuristic confidence | `0.3017` |
| Classification | `low` |
| Calibration status | `not_calibrated` |

`0.3017` is a relative deterministic heuristic-ranking strength under the
current model. It is **not** a calibrated probability of causal correctness.

## 13. TC-4 evidence ledger

| Stance | Count |
|---|---:|
| Supporting | `5` |
| Contradicting | `0` |
| Missing | `0` |
| Unknown | `0` |

Observed claim types:

- `relationship_provenance`;
- `runtime_failure`;
- `source_change`;
- `temporal_precedence`; and
- `topology_path`.

No SC-4 bridge-specific causal claim type was added.

## 14. Final root cause

| Dimension | Accepted result |
|---|---|
| Top1 | exact controlled source mutation |
| Supported Top3 | one hypothesis: the exact controlled mutation |
| Semantic level | `INITIATING_MUTATION` |
| Structural source-cause match | exact `8/8` |
| Supported-hypothesis state | `supported` |
| Evidence completeness | `complete_for_current_model` |
| Evidence-chain state | `complete` |

## 15. Why this counts as accepted proof

The result is accepted because the complete chain satisfied all of the following:

- independently established source truth;
- provider-authentic source mutation identity;
- provider-backed build provenance;
- immutable artifact identity;
- incident-pinned topology;
- exact candidate admission;
- an exact cross-domain relevance anchor;
- an accepted runtime-topology path;
- TC-4 evidence with no contradiction or missing evidence under the current model;
- a supported hypothesis;
- initiating-mutation semantic level; and
- an exact structured source-cause match.

Correctness is not considered proven merely because Top1 happened to match. The
defensible source-to-runtime evidence chain is why the result is accepted.

## 16. Remaining downstream observations

These observations remain separate from the accepted LINEAGE-1K causal verdict:

| Dimension | Independent/durable truth | Compact Topo projection |
|---|---|---|
| Runtime exit code | `42` | `null` |
| Producer run | durable bridge run `32695735269` | compact Top1 `run_id=null` |

The runtime exit-code difference remains a queued observability/projection gap.
The compact Top1 run-ID difference is an audit/projection gap. Neither is the
current causal first divergence, and neither changes the `PROVEN` LINEAGE-1K
verdict.

## 17. Result identities

| Artifact | SHA-256 |
|---|---|
| Runtime receipt | `8EADC5078C10BCF550F80A81094B810390387F4D5CDEF66C7C0FF4D6B5DF14DF` |
| Topo observation | `0FBBFF1C82829F976C55096A64D2EE09AF89C1391A75CDEF9D7A91C4B86A8AD3` |
| Grade | `D550957E55140164CD89C66998F3B5DC278AA7C953FD8B4BF677512A4CEDF296` |
| Diagnostics | `0230F0DB5FF687194F5E1F082AE75D5E8CF91B77AC875BD80C96E18FC2B2E60B` |
| Product database | `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F` |
| Rendered fixture | `FF0967B2B5E92CE9553B48F15B26FC898CBA9C048618F8B47FCF2EC446B5689C` |

## 18. Historical result integrity

| Result family | Accepted tree SHA-256 |
|---|---|
| Pre-SC-1 | `7F1E12E2CDBFA6070E6277B5B6DF33A412214A6E6ED52D64372CFF2C8E7B01BD` |
| Post-SC-1 | `916F749240C6F80FA65902B71F93EE1513E403BBBAB191BEBBAEA58FC0B1FBD3` |
| Post-SC-2 | `078E0BA6C69712716CAAF6B80B5AADD5067CC4D64686C82C46F1CD8A717BC0C5` |
| Post-SC-3 | `E2F1CBCBC648542FCCD3E580FCE5DD1BEEEC7B1370281B4B35BBA6710DA4BDAA` |

## 19. First-divergence progression

The measured progression must remain explicit:

```text
SOURCE_CHANGE_IDENTITY_WRONG
    -> repaired by SC-1

CAUSAL_CANDIDATE_MISSING
    -> source identity fixed but temporal admission blocked

immutable_image_identity_incomplete
    -> repaired by SC-3

CAUSAL_CANDIDATE_MISSING
    -> repaired in the real path by SC-2

CAUSAL_RELEVANCE_PATH_MISSING
    -> repaired by SC-4

NO_DIVERGENCE
```

This history is not collapsed into the final passing result. Each repair was
authorized by the then-current measured first divergence.

## 20. Next engineering phase: adversarial evaluation

LINEAGE-1K authorizes no further product repair. The next phase is adversarial
evaluation, in this priority order:

1. Distractor source changes: `0 / 1 / 5 / 10 / 20 / 50`.
2. Broken immutable lineage:
   - missing Commit -> Actions;
   - missing Actions -> Image;
   - missing Image -> workload.
3. Multi-file source commits containing one causal and multiple irrelevant
   mutations.
4. Multiple builds from the same commit.
5. The same immutable digest used by multiple workloads.
6. Multiple source/provider provenance paths.
7. Repeated variants of the controlled failure.

Future evaluation should measure:

- Top1 flip rate;
- Top3 stability;
- false-supported candidates;
- safe abstention;
- ambiguity behavior;
- candidate deduplication;
- relevance stability; and
- evidence completeness.

No product repair should be authorized until an adversarial scenario exposes a
new measured first divergence.

## 21. Public claim boundary

Currently defensible language:

> TopoAI has demonstrated a provider-backed source-to-runtime causal RCA path
> in a controlled Kubernetes scenario with traceable evidence and safe
> identity/provenance semantics.

Unsupported language includes:

- "TopoAI proves all root causes";
- "generalized Kubernetes RCA";
- "99% accurate";
- "causal probability";
- "fully autonomous RCA"; and
- equivalent claims beyond the measured evidence.

## 22. Final checkpoint state

LINEAGE-1K is preserved as **PROVEN** with **`NO_DIVERGENCE`** under the current
contracts. This closes the single-scenario repair loop. The next work is
adversarial measurement, not an unmeasured product repair.
