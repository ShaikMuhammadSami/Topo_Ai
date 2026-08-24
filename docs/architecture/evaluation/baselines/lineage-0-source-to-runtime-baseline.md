# LINEAGE-0 — Real Source-to-Runtime Lineage Baseline v1

## 1. LINEAGE-0 scope

This is a forensic baseline of the accepted product at Git commit `1224212491c04203ca81b7d4706bf9fd02dcd6ca`. It measures GitHub Repository → Commit → GitHub Actions → immutable image → Kubernetes Deployment → ReplicaSet → Pod → runtime failure. It performs no product repair and does not claim that lineage proves causality.

## 2. Existing product lineage implementation audit

- **Repository:** `github_graph.py` creates `GitRepository` using `github:{api-host}:repository:{provider repository ID}`.
- **Commit:** the same service creates `GitCommit` using `{repository canonical ID}:commit:{lowercase full SHA}` and stores Repository → `contains` → Commit with observed, complete TC-2 provenance and repository/commit source references.
- **Actions:** `github_actions_graph.py` creates `GitHubWorkflowRun` using `github:{api-host}:workflow-run:{provider run ID}`. It links the exact full `head_sha` as Commit → `triggers` → Run with observed, complete provenance.
- **Image:** Actions → Image is emitted only when Kubernetes workload annotations associate a successful workflow run with an image. The relationship is `produces`, origin `inferred`, with heuristic confidence. It is useful enrichment but is not independent registry/build-provider proof.
- **Deployment image:** `container_image_graph.py` parses declared digest references or derives runtime digests. The immutable artifact canonical ID is `artifact:container-image:sha256:...`. Product storage is Deployment/Pod → `uses` → ContainerImage; digest-backed relationships are derived and complete.
- **Deployment → ReplicaSet:** the direct collector uses exact ownerReference UID and stores `owns`, declared, complete.
- **ReplicaSet → Pod:** the direct collector uses exact ownerReference UID and stores the historically accepted `runs`, declared, complete. Agent inventory stores `owns`; both preserve the same owner UID semantic.
- **Failure:** `KubernetesEventCollector` emits structured `NormalizedSignal` records from provider reasons such as `BackOff`, resolves involved entities by exact object UID, and preserves TC-3 provider/observation time.

No product code was changed.

## 3. Provider prerequisite audit

| Prerequisite | Value | Non-secret reason |
|---|---:|---|
| `github_repo_available` | true | Read-only repository API request succeeded. |
| `github_authenticated` | true | Existing GitHub CLI authentication permitted read-only API requests. No credential was serialized. |
| `safe_actions_run_available` | false | A real H2 run exists, but it produced a CLI archive rather than a container digest. |
| `safe_workflow_dispatch_available` | false | The inspected dispatch workflow is bounded but does not build/publish a container; no relevant safe dispatch exists. |
| `immutable_image_digest_available` | true | Docker Hub supplied an independently inspectable immutable nginx index digest for H4–H7 only. |
| `registry_access_available` | true | Read-only OCI manifest inspection succeeded. |
| `kubernetes_available` | true | Docker Desktop Kubernetes executed the disposable namespace. |
| `topo_isolated_environment_available` | true | Current product collectors observed only the disposable namespace. |

`.github/workflows/topo-proof.yml` was not dispatched because it does not produce a container. `.github/workflows/topo-cli.yml` has no dispatch trigger and produces only CLI distribution files. No workflow, package, repository, or Git history was mutated.

## 4. Execution mode

**MODE C — PROVIDER PREREQUISITE BLOCKED.** H1/H2 were evaluated using an existing real GitHub chain. H4–H7 were evaluated independently using an immutable public image and a disposable local workload. H3 was not faked by associating those two unrelated chains.

## 5. Real provider run

- Evaluation run: `70a9d4af`, `2026-08-24T03:26:02Z` to `2026-08-24T03:26:23Z`.
- Repository: `ShaikMuhammadSami/Topo_Ai`, GitHub database ID `1278498159`.
- Commit: `36dd62e1a12010591b90f44ff9d7c8c60e821e9b`, committed `2026-08-23T10:24:10Z`.
- Actions run: `32633653931`; workflow `Topo CLI`, workflow ID `316261569`, run 28, attempt 1, push event, successful.
- Run times: created/started `2026-08-23T10:24:13Z`, completed observation `2026-08-23T10:25:51Z`.
- Run artifact: `topo-ai-cli-36dd62e1a12010591b90f44ff9d7c8c60e821e9b`, 226,582 bytes. It is not a container artifact.
- Independent H4–H7 image: `docker.io/library/nginx@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10`.
- Disposable namespace: `topo-eval-lineage-70a9d4af`, labeled `topo.ai/evaluation-run=70a9d4af`; deleted after capture.
- Runtime failure cause: `deployment_runtime_override` (`/bin/sh -c "exit 17"`). The provider event reason was `BackOff`.
- Topo snapshot observation: `snapshot:actions-enriched:20260824T032623Z:2eba7dd1` with 9 entities, 11 relationships, and 7 structured signals.
- No incident was produced, so incident-pinned evaluation was not applicable. No latest-snapshot claim was made for an incident.

## 6. Independent provider truth

GitHub supplied repository ID, full commit SHA, commit time, run ID, workflow ID, exact `head_sha`, run attempt, event, status, conclusion, timestamps, and artifact metadata. Docker registry inspection supplied the immutable digest. Kubernetes supplied exact Deployment/ReplicaSet/Pod UIDs, ownerReferences, creation timestamps, declared image reference, Event UID, object UID, reason, and failure time. These provider receipts were captured before comparison with Topo and sanitized before serialization.

## 7. eval-lineage-hop-v1 contract

The contract is documented in `lineage-hop-v1.md` and the aggregate result is constrained by `lineage-result.schema.json`. Each hop preserves independent provider identity/evidence, Topo observation, identity/predicate/direction/provenance/source-reference/time verdicts, strength, status, and reason. Matching is exact and deterministic; no LLM, embeddings, fuzzy names, or time-only association is used.

## 8. H1 Repo -> Commit

- **Provider truth:** commit SHA belongs to repository database ID `1278498159`.
- **Topo identity:** exact repository and full-SHA canonical IDs match.
- **Relationship:** `contains`, repository → commit.
- **Provenance:** `observed`; `backend.app.services.github_graph`; `github-commit-linker:v1`; complete; refs `github_repository_id`, `git_commit_sha`.
- **Time:** provider commit `2026-08-23T10:24:10Z`; Topo observation `2026-08-24T03:26:23Z`.
- **Status:** **PROVEN**.

## 9. H2 Commit -> Actions

- **Provider truth:** run `32633653931` has exact `head_sha = 36dd62e1...21e9b`; time proximity was not used.
- **Topo identity:** exact full-SHA commit and provider run ID match.
- **Relationship:** `triggers`, commit → workflow run.
- **Provenance:** `observed`; `backend.app.services.github_actions_graph`; `github-actions-trigger-linker:v1`; complete; refs `github_workflow_run_id`, `git_commit_sha`.
- **Time:** commit `10:24:10Z` → run `10:24:13Z`; Topo observation `2026-08-24T03:26:23Z`.
- **Status:** **PROVEN**.

## 10. H3 Actions -> Image Digest

- **Provider truth:** unavailable. The real run produced a CLI archive, not a container. No build output, registry version, OCI annotation, attestation, or log receipt defensibly links this run to a digest.
- **Topo truth:** no relevant image was associated with this run in the disposable workload. The unrelated nginx digest was not annotated as its output.
- **Status:** **PROVIDER_PREREQUISITE_BLOCKED**.
- **Reason:** no existing or safely dispatchable workflow provides the required real run-to-digest evidence.

## 11. H4 Image Digest -> Deployment

- **Provider truth:** Deployment UID `cc9e27a6-d8ef-4c5b-b5ab-ffa32efdfcd5` declares the exact nginx digest.
- **Topo identity:** exact digest canonical artifact and exact Deployment UID match.
- **Relationship:** accepted storage is Deployment → `uses` → ContainerImage.
- **Provenance:** `derived`; `backend.app.services.container_image_graph`; `container-image-linker:v1`; complete; refs `container_image_reference`, `container_image_digest`.
- **Time:** Deployment created `2026-08-24T03:26:06Z`; Topo observed `03:26:23Z`. Registry publication time was not available in the selected manifest receipt and was not invented.
- **Status:** **PROVEN**, independently of H3.

## 12. H5 Deployment -> ReplicaSet

- **Provider truth:** ReplicaSet ownerReference UID equals Deployment UID exactly.
- **Topo IDs:** Deployment `...:cc9e27a6-d8ef-4c5b-b5ab-ffa32efdfcd5`; ReplicaSet `...:b5655e49-d5c3-4053-89e7-02235c0d4a37`.
- **Relationship:** `owns`, Deployment → ReplicaSet.
- **Provenance:** `declared`; Kubernetes collector; `kubernetes-collector-linker:v1`; complete; owner UID source reference.
- **Time:** both provider objects created `2026-08-24T03:26:06Z`; Topo observed `03:26:23Z`.
- **Status:** **PROVEN**.

## 13. H6 ReplicaSet -> Pod

- **Provider truth:** Pod ownerReference UID equals ReplicaSet UID exactly.
- **Topo IDs:** ReplicaSet `...:b5655e49-d5c3-4053-89e7-02235c0d4a37`; Pod `...:779d72a6-b1f9-4ff3-b8dc-5f535cb66228`.
- **Relationship:** direct collector `runs`, ReplicaSet → Pod. Agent inventory's equivalent accepted predicate is `owns`.
- **Provenance:** `declared`; Kubernetes collector; `kubernetes-collector-linker:v1`; complete; owner UID source reference.
- **Time:** provider ReplicaSet/Pod `2026-08-24T03:26:06Z`; Topo observed `03:26:23Z`.
- **Status:** **PROVEN**.

## 14. H7 Pod -> Runtime Failure

- **Provider truth:** Event UID `8de56a9f-367d-4ae8-95f4-2ad18ad7a2b1` references exact Pod UID `779d72a6-b1f9-4ff3-b8dc-5f535cb66228` with structured reason `BackOff`.
- **Topo truth:** signal `signal:kubernetes-event:docker-desktop:8de56a9f-367d-4ae8-95f4-2ad18ad7a2b1` references the exact Pod entity and object UID.
- **Semantic:** `involved_entity`, Pod → failure signal in the evaluation projection.
- **Provenance:** provider-observed normalized signal; `kubernetes_event_collector`; `normalized-signal-v1`; exact event/object UID references.
- **Time:** Pod `2026-08-24T03:26:06Z` → event `03:26:08Z`; Topo collection `03:26:23Z`.
- **Status:** **PROVEN**.

## 15. Full hop matrix

| Hop | Provider truth | Topo entity IDs | Topo relationship | Provenance | Time | Status | Reason |
|---|---|---|---|---|---|---|---|
| H1 Repo→Commit | exact repo ID + SHA | exact/exact | `contains` forward | observed, complete | provider commit + Topo observed | PROVEN | identity, edge, refs agree |
| H2 Commit→Actions | exact `head_sha` + run ID | exact/exact | `triggers` forward | observed, complete | 3-second provider order | PROVEN | not time-inferred |
| H3 Actions→Image | no run-to-digest receipt | run/none | none | none | image time/link unavailable | PROVIDER_PREREQUISITE_BLOCKED | run produced CLI archive only |
| H4 Image→Deployment | exact declared digest + Deployment UID | exact/exact | Deployment `uses` Image | derived, complete | Deployment + Topo observed | PROVEN | immutable digest exact |
| H5 Deployment→RS | exact owner UID | exact/exact | `owns` forward | declared, complete | ordered/equal creation | PROVEN | ownerReference exact |
| H6 RS→Pod | exact owner UID | exact/exact | `runs` forward | declared, complete | ordered/equal creation | PROVEN | ownerReference exact |
| H7 Pod→Failure | Event UID + Pod UID + `BackOff` | exact/exact | structured involved entity | observed, complete | Pod before event | PROVEN | structured provider state |

## 16. First broken hop

```text
H1 Repo -> Commit           PROVEN
H2 Commit -> Actions        PROVEN
H3 Actions -> Image         PROVIDER_PREREQUISITE_BLOCKED
H4 Image -> Deployment      PROVEN
H5 Deployment -> ReplicaSet PROVEN
H6 ReplicaSet -> Pod        PROVEN
H7 Pod -> Runtime Failure   PROVEN

FIRST_BROKEN_HOP: PROVIDER_PREREQUISITE_BLOCKED
FIRST_BROKEN_HOP_ID: H3
REPAIR_CLASSIFICATION: H3_ACTIONS_IMAGE
```

## 17. Immutable artifact chain

**Incomplete.** H4 proves an immutable digest reaches the Deployment, but H3 does not prove that the selected Actions run produced that digest. Six hops are proven; one is provider-blocked. There are zero partial, missing, wrong, or inconclusive hop verdicts in this run.

## 18. Temporal ordering

H1/H2 and H4–H7 preserve provider-native times separately from Topo observation time. The observed provider order is commit ≤ run, Deployment ≤ ReplicaSet ≤ Pod ≤ failure. Image publication time and run-to-image time are absent, so the full temporal chain is not claimed. The evaluator tolerates at most five minutes of adjacent provider timestamp skew; it does not use proximity as relationship proof.

## 19. Relationship provenance analysis

H1/H2 are observed provider enrichments with complete exact provider refs. H4 is digest-backed derived provenance. H5/H6 are declared Kubernetes ownership evidence using owner UID. H7 is not a TC-2 graph relationship; its evaluation projection preserves the normalized signal's exact event UID/object UID evidence. H3 product capability, when annotations exist, is explicitly inferred/heuristic and is not silently promoted to provider proof.

## 20. Identity analysis

Repository database ID, full commit SHA, workflow run ID, container digest, and Kubernetes object UIDs all matched independently derived TC-1 canonical IDs for the six exercised hops. No display-name or fuzzy equality was accepted. Mutable tags are kept distinct from digest identity.

## 21. Lineage strength

Aggregate strength: **UNKNOWN**, because an essential provider hop was not executable. The six proven individual hops are strong. The aggregate is intentionally not a probability or percentage.

## 22. Lineage vs causal attribution

`source_change_causally_proven = not_tested`. The runtime failure came from the disposable Deployment command override. The nginx image is unrelated to the selected GitHub Actions run, and the commit is not claimed as the failure's root cause.

## 23. Product commercial proof status

| Claim | Result |
|---|---:|
| `repo_commit_proven` | true |
| `commit_ci_proven` | true |
| `ci_image_digest_proven` | false |
| `image_deployment_proven` | true |
| `deployment_runtime_proven` | true |
| `runtime_failure_proven` | true |
| `full_source_to_runtime_lineage_proven` | false |

## 24. Files created

- `evaluation/lineage_contracts.py`
- `evaluation/lineage_provider_truth.py`
- `evaluation/lineage_evaluator.py`
- `evaluation/lineage_runner.py`
- `evaluation/tests/test_lineage_baseline.py`
- `docs/architecture/evaluation/lineage-hop-v1.md`
- `docs/architecture/evaluation/lineage-result.schema.json`
- `docs/architecture/evaluation/baselines/lineage-0-source-to-runtime-baseline.md`

## 25. Files modified

None. All tracked LINEAGE-0 work is new and evaluation/documentation only.

## 26. Product diff

None under `backend/app/`, `backend/tests/`, `agent/src/`, `frontend/`, or `cli/src/`.

## 27. Evaluation tests

58 focused LINEAGE-0 tests cover structural provider identity, exact SHA/run association, immutable image rules, UID ownership, structured failure state, independent evidence, all hop statuses, earliest-break selection, provenance/source refs, direction, bounded time skew, incident pin enforcement, deterministic serialization, schema shape, secret redaction, product/scenario guards, H6 predicate compatibility, and cleanup guards.

Full evaluation result: **192 passed in 6.07s** (134 accepted baseline + 58 LINEAGE-0).

## 28. Full regressions

- Evaluation compile: pass.
- Evaluation tests: **192 passed in 6.07s**.
- Backend compile: pass.
- Backend tests: **608 passed, 1 warning in 19.01s**.
- Agent compile: pass.
- Agent tests: **15 passed in 1.69s**.
- JSON schema validation: `True` using PowerShell `Test-Json`.
- Frontend/CLI were not run because they were not touched.

## 29. Permanent manifest hashes

Git blob hashes remain unchanged:

| Manifest | Hash |
|---|---|
| `sentinel-a` | `599ba19827d5097fded3f52264cad8dd35abb839` |
| `sentinel-b` | `f404607eaca904baac362edb2365fa53652565fe` |
| `sentinel-c` | `9bb3c201b190708224770a30ec9c23939623f683` |
| `sentinel-d` | `e7e2a8f4e2cde066bee209191ec27304a41193f7` |
| `blast-01` | `2f292f5ee1c116d2c2c832bc2165a61bc13dedc5` |
| `blast-02` | `695d0feda176f26c7e601a57060f4ad0d29310a9` |
| `blast-03` | `0f9974a4a5f4a08d6b01d2e02be319698175f6c1` |

## 30. Generated artifacts / cleanup

Ignored bundle: `evaluation/results/lineage/lineage-70a9d4af.json`. It validated against `eval-lineage-result-v1`, contains sanitized receipts, and is ignored by `evaluation/results/.gitignore`. The exact disposable namespace and its label were verified before deletion. A post-run label query found no evaluation namespace. No images, registry artifacts, Actions runs, packages, DBs, or user workloads were deleted.

## 31. Provider prerequisites still missing

One already-pushed commit must be handled by an explicitly evaluation-safe workflow that builds a container, publishes it to an accessible registry, and preserves a provider-native link from the exact Actions run ID/head SHA to the immutable digest (for example build metadata, OCI provenance/attestation, or an emitted digest plus registry receipt). Credentials should remain configured locally; none should be pasted into chat or stored in evaluation output.

## 32. Proposed NEXT repair boundary

**H3 Actions → immutable image only.** A later architect-approved block should establish defensible provider evidence for the run-to-digest relationship and then re-run LINEAGE-0. It should not change H1/H2 or H4–H7 merely because H3 is blocked. No repair was implemented here.

## 33. Questions requiring architect decision

None for this baseline. A future H3 block will need an explicit decision on registry and provenance mechanism before it modifies product/workflow behavior.

## 34. Git status

Branch: `evaluation/source-to-runtime-lineage-baseline-v1`. Only the eight new evaluation/documentation files listed above are expected. The generated result is ignored. No files are staged.

## 35. git diff --check

Pass; no whitespace errors.
