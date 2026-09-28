# CX-0A.G0 Golden Evaluation Contract Freeze v1

Status: source and offline-contract freeze.

Pre-G0 source authority:

- HEAD: `0e2e6b2588c7eef67315a726dbb1ee80d7562f9d`
- tree: `cdda46c8eace68d54607cf458f4e7c07f6fcfba6`

`EVALUATION_FREEZE_IS_NOT_PRODUCT_CORRECTNESS_PROOF`.

G0 proves only that the measuring instrument, mandatory scenario identities,
expected truth, output contract, and safety boundary are frozen before any new
golden scenario executes. G1 through G6 measure product behavior.

## Scope and mutation boundary

G0 performs repository inspection, source changes, schema validation, and
offline deterministic tests only. It does not run a live golden scenario and
does not mutate AWS, Kubernetes, a database, Terraform, DNS, ECR, or the
golden environment.

`topo-system` is the `PROTECTED_CONTROL_PLANE`. Future live synthetic assets
must be isolated in the dedicated `topo-eval` namespace (or an explicitly
reviewed equivalent); G0 does not create it. A scenario may never manufacture
a failure by breaking Topo backend, frontend, observer, RDS, ALB/WAF, DNS,
ACM, the EKS control plane, Terraform authority, or SecretStore authority.
The obscurity of a provider-generated endpoint is not a safety boundary.

## Repository-wide evaluation inventory

The inventory was verified against current source, tests, schemas, fixtures,
and accepted baselines rather than inferred from historical documents alone.

### REUSE

| Authority | Current source | Frozen use |
|---|---|---|
| Independent evaluation harness | `evaluation/__main__.py`, `evaluation/runner.py`, `evaluation/evaluator.py`; `HARNESS_VERSION = eval-1.v1` | Existing black-box HTTP/provider observation harness and deterministic evaluator entry points remain authoritative. |
| Existing scenario manifests | `evaluation/manifests/sentinel-*.json`, `evaluation/manifests/blast-*.json`; `eval-1.scenario.v1` | Reference implementations for authored-before-run logical aliases, causal intent, affected/unaffected sets, paths, evidence, and abstention. |
| Existing result contract | `docs/architecture/evaluation/evaluation-result.schema.json`; `eval-1.result.v1` | Existing EVAL-1 artifacts remain valid and unchanged. |
| Independent causal truth | `evaluation/source_mutation_truth.py`, `evaluation/causal_ground_truth.py`, `docs/architecture/evaluation/causal-ground-truth.schema.json` | Source/provider truth remains independent from Topo output. |
| Structured causal comparison | `evaluation/source_cause_match.py`, `evaluation/structured_cause_match.py`, `evaluation/cause_fingerprint.py` | Exact structured comparison; no title-token, fuzzy, embedding, or LLM ground truth. |
| Source-to-runtime lineage | `evaluation/lineage_contracts.py`, `evaluation/lineage_evaluator.py`, runtime causal receipt schemas | Canonical repository/commit/run/image/workload/runtime evidence chain. |
| Non-cause evidence semantics | `evaluation/evidence_semantics.py`; `non-cause-evidence-v1` | Candidate facts remain distinct from causal connectivity and effect evidence. |
| Distractor robustness | `evaluation/lineage_distractor_robustness.py`; LINEAGE-2A tests and final baseline | Unsupported high-ranked distractors consume zero supported projection capacity. |
| Broken-lineage behavior | `evaluation/lineage_broken_run_image.py`, `evaluation/lineage_broken_image_workload.py`; LINEAGE-2B contracts/baselines | Missing immutable lineage reduces specificity or produces abstention; it never permits fabrication. |
| Artifact integrity | `evaluation/artifact_integrity.py`; `evaluation-artifact-integrity-v1` | Final result trees use canonical sorted UTF-8 JSON, relative POSIX/NFC paths, SHA-256 file identities, and an EAI-1 tree digest. |
| Production support gate | `backend/app/services/causal_support_gate.py`; `causal-support-gate-v1` | Categorical evidence qualification remains authoritative and is not changed by G0. |
| Production projections | `backend/app/services/causal_hypothesis_projection.py`; `causal-hypothesis-projection-v1` | Diagnostic and supported projections remain separate views over one evaluated set. |
| Determinism | manifest-authored logical aliases, provider UIDs, canonical ordering, deterministic IDs/seeds in current evaluation modules, repeated-order LINEAGE tests | G0 preserves existing deterministic controls and adds no randomized truth. |

The accepted historical evidence referenced by this freeze includes:

- `lineage-1-final-proven-source-to-runtime-causal-baseline.md`;
- `lineage-2a-final-clean-distractor-robustness-baseline.md`;
- `lineage-2b2-missing-run-image-final-baseline.md`;
- `lineage-2b3-missing-image-workload-final-baseline.md`;
- the SC-1 through SC-4 and AR-1 through AR-3 repair baselines.

Those records are evidence about measured scenarios, not generalized product
accuracy claims.

Current deterministic assets include the authored Sentinel and BR-0 JSON
manifests under `evaluation/manifests/`, the source/runtime fixture under
`evaluation/fixtures/lineage-image/`, the Kubernetes lineage manifest under
`evaluation/fixtures/lineage-causal/`, and provider receipt schemas under
`docs/architecture/evaluation/`. LINEAGE-2A fixes the distractor-count matrix
at `0, 1, 5, 10, 20, 50`, evaluates deterministic storage orders, and protects
the accepted post-SC4 seed by SHA-256. LINEAGE-2B constructs byte-identical
isolated copies, fingerprints protected truth before and after the cut, and
repeats valid constructions three times. G0 references those controls; it
does not regenerate their historical live evidence.

### EXTEND

G0 adds four versioned authorities without replacing the existing harness:

1. `evaluation/golden/cx0/golden_evaluation_authority_v1.json` binds the
   accepted pre-G0 source, harness, corpus, truth, result schema, projection
   policies, mandatory scenarios, and deferred families.
2. `evaluation/golden/cx0/golden_scenario_corpus_v1.json` freezes nine
   mandatory scenario contracts as `cx0-golden-scenario-corpus-v1`.
3. `evaluation/golden/cx0/golden_ground_truth_v1.json` freezes independent
   truth as `cx0-golden-ground-truth-v1`.
4. `cx0-golden-scenario-receipt-v1.schema.json` defines the receipt produced
   by future G1-G6 adapters. It references ground truth; it does not contain
   the sole truth authority.

### RETIRE / LEGACY

Nothing is deleted. The following remain supported historical formats but are
not the authority for new CX-0 golden receipts:

- `eval-1.result.v1` status values `INCONCLUSIVE` and `HARNESS_ERROR` remain
  valid for old EVAL-1 runs. CX-0 receipts instead use exactly `PASS`, `FAIL`,
  `CONSTRUCTION_BLOCKED`, and `INCOMPLETE`.
- EVAL-1 result artifacts embed a ground-truth snapshot as a sibling of
  observations. For CX-0, an output artifact may reference but cannot become
  the independent ground-truth authority.
- historical pre-EAI result trees are not rewritten or backfilled.
- Sentinel and BR-0 namespace formats remain valid for their old runners;
  future CX-0 live scenarios use the separately frozen `topo-eval` boundary.

### MISSING after G0

G0 deliberately does not implement or execute:

- live adapters for G-POS-1, G-EPH-1 through G-EPH-3, G-TIME-1, or G-REC-1;
- a `topo-eval` namespace or any scenario workload;
- provider receipts for the future golden AWS/EKS environment;
- an aggregate G1-G6 runner or release decision artifact;
- broad cloud, Terraform, security-group, DNS, pressure, secret/config,
  parity, statistical, or performance scenario families.

These are future measured work, not blockers to freezing the instrument.

## Frozen authorities

| Authority | Version | Path |
|---|---|---|
| Harness | `eval-1.v1` | `evaluation/` |
| Golden corpus | `cx0-golden-scenario-corpus-v1` | `evaluation/golden/cx0/golden_scenario_corpus_v1.json` |
| Golden ground truth | `cx0-golden-ground-truth-v1` | `evaluation/golden/cx0/golden_ground_truth_v1.json` |
| Golden receipt | `cx0-golden-scenario-receipt-v1` | `docs/architecture/evaluation/cx0-golden-scenario-receipt-v1.schema.json` |
| Authority manifest | `cx0-golden-evaluation-authority-v1` | `evaluation/golden/cx0/golden_evaluation_authority_v1.json` |
| Artifact integrity | `evaluation-artifact-integrity-v1` | `evaluation/artifact_integrity.py` |

The authority manifest records the accepted pre-G0 commit/tree, not its own
future commit identity. The resulting G0 commit/tree is reported externally,
avoiding a self-referential manifest hash.

## Mandatory corpus

The mandatory pre-CX0B corpus has exactly nine scenarios:

| Scenario | Family | Execution class | Frozen outcome |
|---|---|---|---|
| `G-POS-1` | canonical source-to-runtime recovery | `LIVE_GOLDEN_SYNTHETIC_MUTATION` | expected source mutation at Supported Top1 |
| `G-EPH-1` | Pod replacement under unchanged workload | `LIVE_GOLDEN_SYNTHETIC_MUTATION` | abstain; replacement alone is not an incident/cause |
| `G-EPH-2` | rolling Deployment/new ReplicaSet | `LIVE_GOLDEN_SYNTHETIC_MUTATION` | failing revision at Supported Top1 |
| `G-EPH-3` | same name/new UID | `LIVE_GOLDEN_SYNTHETIC_MUTATION` | recreated failing authority at Supported Top1 |
| `G-TIME-1` | topology advances after incident | `LIVE_GOLDEN_SYNTHETIC_MUTATION` | incident-time cause/path; no latest-topology fallback |
| `G-TIME-2` | delayed/out-of-order evidence | `OFFLINE_FIXTURE` | immutable-lineage cause remains supported independent of arrival order |
| `G-ADV-1` | nearby non-causal distractor | `OFFLINE_FIXTURE` | golden cause at Supported Top1; distractor capacity is zero |
| `G-ADV-2` | missing critical immutable lineage | `OFFLINE_FIXTURE` | empty supported projection/abstention, or construction-blocked before grading |
| `G-REC-1` | human recovery and Topo verification | `LIVE_GOLDEN_SYNTHETIC_MUTATION` | original cause supported; manual recovery verified |

`LIVE_GOLDEN` and `FUTURE_EPHEMERAL_CLOUD` are valid execution classes in the
contract, but none of the nine G0 scenarios requires ephemeral-cloud
reconstruction. No ground truth may be revised after observing Topo output.

## Causal and projection invariants

Raw/diagnostic ranking is not evidence-supported causality:

```text
evaluated hypotheses
       +---- causal-order diagnostic projection
       |
       +---- support-qualified supported projection
```

A positive canonical scenario passes only when Supported Top1 equals the
frozen expected cause. Raw or diagnostic Top1 need not equal it. Unsupported
high-ranked distractors consume zero supported projection capacity. An
uncertainty scenario may correctly have an empty supported projection or an
equivalent bounded insufficient-evidence state.

G0 changes no causal coefficients, temporal weight, candidate discovery,
admission, evaluation budget, relevance policy, support gate, ranking,
projection, confidence, calibration, or topology traversal.

## Construction-blocked semantics

`CONSTRUCTION_BLOCKED` is valid only when the intended counterfactual cannot
be truthfully represented by the evidence ontology without fabricating
authority or corrupting protected truth. Its receipt must include a non-empty
`construction_blocked_reason`.

It never means that the harness is missing, the test is inconvenient, the
scenario or infrastructure failed, or Topo returned an unexpected result.
Those conditions are `INCOMPLETE` or `FAIL` according to the established
truth state. A construction-blocked scenario is not a product PASS or FAIL.

The constructor must not fabricate provider evidence, intentionally preserve
stale derived edges, delete half of an atomic authoritative observation, or
weaken identity semantics. The accepted LINEAGE-2B.1
`evidence_model_nonseparable` finding is the reference case.

## Ground truth and result separation

Ground truth is authored before execution and identifies the initiating
mutation, expected cause or abstention, exact identity chain, required hops,
affected and unaffected entities, optional impact/owner, and recovery
condition. Topo is always the system under test and cannot write expected
truth.

Every receipt references a ground-truth ID, version, and authority path.
Receipts contain actual supported and actual diagnostic hypotheses in separate
fields. They may not redefine expected truth. Nullable impact, ownership, and
recovery values are permitted when the fixture has no independent authority.

## Receipt, storage, and integrity

The v1 receipt binds source commit/tree, all three immutable image digests,
database migration, infrastructure fingerprint, scenario interval,
precondition, authorized mutation, expectation references, actual incident and
snapshot, both projections, evidence/path, impact/ownership/guidance/recovery,
cleanup, post-cleanup fingerprint, status, construction blocker, and
limitations.

Future result artifacts remain under ignored `evaluation/results/`. Finalized
result families must generate and verify `artifact-integrity-v1.json` after
ordinary files are quiescent. EAI-1 hashes every scoped regular file and a
canonical tree material; credentials, tokens, cookies, database URLs,
SecretStore values, kubeconfig material, and customer data are forbidden.

## Deferred non-blocking families

The following do not block CX-0B unless already present and essentially free:

- broad Terraform/cloud faults;
- generic security-group and DNS faults;
- generic node/resource-pressure faults;
- broad Secret/config faults;
- statistical multi-incident or large-corpus percentage claims;
- all-provider parity; and
- performance/SLO corpora.

Four, nine, or any other small controlled set is not statistically meaningful
and must not be advertised as generalized accuracy.

## G1-G6 sequence

1. **G1 — canonical positive:** execute G-POS-1 inside the protected golden
   boundary and finalize its provider/evaluator receipt.
2. **G2 — ephemeral identity:** execute G-EPH-1 through G-EPH-3 and prove UID
   identity across replacement, rollout, and same-name recreation.
3. **G3 — temporal correctness:** execute G-TIME-1 and the offline G-TIME-2;
   prove pinned history and order-independent immutable evidence.
4. **G4 — adversarial evidence:** execute offline G-ADV-1 and G-ADV-2; preserve
   supported/diagnostic separation, abstention, and construction validity.
5. **G5 — recovery:** execute G-REC-1 with a receipted human action and Topo
   verification; no automatic remediation is authorized.
6. **G6 — closure:** validate every receipt, EAI-1 identity, cleanup and
   postcondition fingerprint, then issue the separate product-behavior gate.

CX-0B teardown is not authorized by G0. The contract freeze must be combined
with future G1-G6 results and all other CX-0 closure authorities.
