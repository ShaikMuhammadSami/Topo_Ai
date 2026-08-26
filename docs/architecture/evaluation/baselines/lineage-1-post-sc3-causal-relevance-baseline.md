# LINEAGE-1 Post-SC-3 Causal Relevance Baseline v1

Date: 2026-08-26

Branch: `evaluation/lineage-1-post-sc3-baseline-v1`

Accepted product commit: `f5b4d673c3ace58536ae8cfe89bd2b00833e518d`

Final LINEAGE-1I verdict: **MISSING**

First divergence: **`CAUSAL_RELEVANCE_PATH_MISSING`**

SC-1 gate: **PASS**

SC-3 gate: **PASS**

SC-2 gate: **PASS**

## 1. Checkpoint purpose

This document permanently preserves the accepted LINEAGE-1I measurement before
SC-4 changes causal-relevance semantics. It is a documentation checkpoint only.
It does not modify or reinterpret product code, evaluators, causal policy,
provider state, Kubernetes state, or the frozen experiment.

LINEAGE-1I demonstrated that the provider-authentic source mutation remained
correct, requested-versus-runtime image identity survived the real
incident-pinned topology path, and exact immutable lineage admitted the source
candidate without changing time or rank. The next measured first divergence is
now causal relevance.

## 2. Accepted result

| Dimension | Accepted observation |
|---|---|
| Final verdict | `MISSING` |
| First divergence | `CAUSAL_RELEVANCE_PATH_MISSING` |
| SC-1 source-identity gate | `PASS` |
| SC-3 image-identity gate | `PASS` |
| SC-2 candidate-admission gate | `PASS` |
| Causal relevance | `FAIL` |
| Causal relevance status | `identity_unresolved` |
| Candidate topology component | `0.0` |
| Candidate entity ID | `null` |
| Path semantic | `unsupported_unknown` |
| Topology hops | `0` |
| Path relationship IDs | empty |

The exact product explanation was:

> Candidate or affected identity is not present in the incident-pinned
> topology; no latest-topology fallback was used.

## 3. SC-1 source mutation identity

SC-1 remained **PASS**. The exact provider-authentic mutation remained durable
and structurally correct:

| Dimension | Accepted observation |
|---|---|
| Source event | `change-event:20a8946c8c445153d85c90ee2166d487` |
| Mutation | `source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633` |
| Path | `evaluation/fixtures/lineage-image/runtime-mode.txt` |
| Before | `healthy` |
| After | `fail` |

## 4. SC-3 requested-versus-runtime image identity

SC-3 remained **PASS** under contract
`kubernetes-container-image-identity-v1`.

The requested immutable identity survived:

```text
Kubernetes collection
    -> normalization
    -> ContainerImage graph
    -> snapshot persistence
    -> fresh readback
    -> incident-pinned topology
```

Requested image:

```text
ghcr.io/shaikmuhammadsami/topo_ai-topo-lineage-eval@sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed
```

Pod `status.image`:

```text
sha256:a3392fbeae192e861a3df42d25acf050c45a657c8e277a41258332baa9451f53
```

The status image remained diagnostic and did not replace the requested
artifact. Pod `imageID` independently exposed the requested repository/digest
identity. The prior `immutable_image_identity_incomplete` reason disappeared.

## 5. SC-2 exact immutable-lineage admission

SC-2 became **PASS** under `causal-candidate-admission-v2`.

| Dimension | Accepted observation |
|---|---|
| Source-to-incident gap | `2283.78` minutes |
| Ordinary Path A lookback | `180` minutes |
| Source event inside Path A | no |
| Admission basis | `exact_immutable_lineage` only |
| Candidate count | `1` |
| Exact source occurrence count | `1` |
| Lineage state | `admitted` |
| Source effective time | `2026-08-24T06:02:03Z` |
| Timestamp rewrite | none |
| Lineage ranking bonus | none |
| Duplicate candidate | none |
| Attached mutation bundle | one complete SC-1 mutation |

`CAUSAL_CANDIDATE_MISSING` therefore disappeared.

## 6. Proven immutable provenance bridge

The incident-side path was:

```text
Pod
    -> ReplicaSet
    -> Deployment
    -> ContainerImage
```

The provider/source provenance was:

```text
Source revision
    -> Actions run
    -> immutable ContainerImage
```

Provider build evidence:

```text
build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb
```

The exact immutable artifact joins these two truth domains.

## 7. New first divergence

The admitted source-change candidate is a reasoning/change entity; it is not
itself a topology entity. SC-2 already carries exact immutable provenance
connecting the source change and revision to the producer run and image. The
incident-pinned topology independently connects the image to the Deployment,
ReplicaSet, and affected Pod.

`causal-relevance-v1` currently expects or resolves a topology
`candidate_entity_id`. The admitted source candidate has
`candidate_entity_id=null`, so the relevance policy does not consume the
already-established cross-domain identity/provenance bridge and returns no
accepted path.

This is a **relevance-resolution defect**. It is not:

- a source-identity defect;
- an image-identity defect;
- a candidate-admission defect; or
- a ranking defect.

## 8. Important non-conclusion

The current Top1 was the exact controlled source mutation at rank `1`, with
semantic level `INITIATING_MUTATION` and an exact `8/8` structural source-cause
match. This does **not** constitute accepted causal proof because the required
causal-relevance path remains unresolved.

The final verdict therefore remains **MISSING**.

## 9. TC-4 evidence ledger

| Stance | Count |
|---|---:|
| Supporting | `3` |
| Contradicting | `0` |
| Missing | `0` |
| Unknown | `0` |

Observed claim types were:

- `runtime_failure`;
- `source_change`; and
- `temporal_precedence`.

SC-2 admission metadata and SC-3 identity metadata were not promoted into new
causal claim types.

## 10. Approved next repair boundary

Approved next investigation and repair:

**SC-4 — Lineage-Aware Causal Relevance Path Resolution**

SC-4 should allow `causal-relevance-v1` to resolve an admitted canonical
source-change candidate through its already-proven immutable provenance bridge
into incident-pinned topology:

```text
source change
    -> source revision
    -> producer run
    -> immutable image
    -> incident-pinned workload
    -> affected Pod
```

Provenance alone must not make a candidate causally relevant. The relevance
policy must still evaluate allowed path semantics.

SC-4 must not solve `candidate_entity_id=null` by fabricating a topology entity
for the source change. It should prefer an explicit cross-domain relevance
anchor or path derived from exact durable provider provenance and
incident-pinned topology. This permits reasoning across the source/change and
runtime-topology domains without pretending every source change is a topology
node.

If any required provenance bridge is missing or ambiguous, causal relevance
must remain unresolved or incomplete. It must not fall back to latest topology
or fuzzy matching.

## 11. SC-4 non-goals

SC-4 does not authorize:

- candidate-admission changes;
- changing the 180-minute ordinary path;
- source timestamp rewriting;
- ranking changes;
- a lineage ranking bonus;
- TC-4 claim expansion without a separately measured need;
- forced Top1 selection;
- `SourceFile` topology entities;
- a `ChangeEvent` topology entity solely to bypass relevance;
- latest-topology fallback;
- fuzzy, LLM, or embedding-based identity resolution;
- runtime exit-code repair; or
- Deployment health-timing repair.

## 12. Downstream observations, not next repair targets

These measurements remain queued downstream findings:

| Dimension | Independent truth | Topo observation |
|---|---:|---:|
| Runtime exit code | `42` | `null` |
| Deployment impact | `1` desired / `0` ready / `0` available | `1` / `1` / `1` at later collection |

They are not the next repair targets because causal relevance is the earlier
divergence.

## 13. Result identities

| Artifact | SHA-256 |
|---|---|
| Runtime receipt | `8BD390565DD6B0B785BB72101DF5BBF2A3BA443C6AF2AC5E363BF58C1B486ABA` |
| Topo observation | `552F5E3FFA5DA87D86EE433C15ECEBA298D1C7A817A0E98A7793C032F24630F9` |
| Grade | `E4062D4CD58BA525944822F7BE2274F4C139C2E4B21187D4D5DF8AC35349F16C` |
| Product diagnostics | `DBBC33274514EE5B6E5AB45E875CC9D2F443FF62EDDA3B4AF088F9F649B0444A` |
| Product database | `9F380600C519C5CEF85386C92D7EEF04B492E0C6F22ACF936FDDB46BEDEC7423` |

## 14. Measurement limit

This remains one deterministic controlled scenario.

It proves:

- SC-1 real source-mutation identity;
- SC-3 real requested/runtime image-identity preservation;
- SC-2 real lineage-aware admission success;
- no source timestamp rewrite;
- no lineage score bonus; and
- a new first divergence at causal relevance.

It does not prove generalized Kubernetes RCA.
