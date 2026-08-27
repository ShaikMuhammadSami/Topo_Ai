# LINEAGE-3A0 — Terraform -> AWS Provider-Backed Causal Lineage Representability Audit v1

**Status: FORENSIC AUDIT COMPLETE — BLOCKED FOR MEASUREMENT**

Date: 2026-08-27

Branch: `evaluation/lineage-3-tf-aws-representability-audit-v1`

Accepted repository commit audited:
`59830a9bcac1a6e90a80cbe38c1b9a60e70619c0`

Accepted repository summary:
`59830a9 docs(evaluation): freeze missing image workload baseline (#58)`

## 1. Scope and governing question

This is a documentation and forensic representability audit. It does not add
product behavior, call AWS, run Terraform, provision infrastructure, create a
fixture, mutate an evaluation seed, execute causal measurement, create result
artifacts, or authorize a repair.

The governing future question is:

> Did this exact Terraform source mutation cause this exact AWS runtime
> incident?

The desired evidence chain is:

```text
GitHub repository
  -> exact commit and source-file mutation
  -> GitHub Actions run/attempt
  -> Terraform plan and apply
  -> exact Terraform resource address
  -> exact AWS role/session
  -> exact CloudTrail mutation
  -> exact AWS resource ARN
  -> exact runtime failure
  -> incident pinned to the relevant historical topology
```

Lineage alone cannot answer the causal question. A source-level
`INITIATING_MUTATION` conclusion must eventually require candidate-specific
continuity from the exact source mutation, through independently defensible
provider observations, to the exact affected runtime and its failure signal.

## 2. Verdict

**Verdict: `BLOCKED`.**

The preferred controlled fixture remains **A. AWS Lambda configuration
failure**, but the current accepted product cannot truthfully represent the
complete chain. The blocker is not AWS inventory identity: Lambda ARN identity
is already representable. The blockers are:

1. no typed Terraform plan/apply or resource-address evidence;
2. no exact GitHub Actions run -> Terraform apply -> AWS session bridge;
3. loss of the CloudTrail identity and request/resource fields needed for that
   bridge;
4. no Lambda/CloudWatch runtime-failure collector or AWS signal type;
5. a Kubernetes/cluster-shaped automatic incident lifecycle that cannot
   represent a cloud-native Lambda incident without overloading `cluster_name`;
6. no non-container exact-lineage admission/relevance path from a Terraform
   source mutation to an affected AWS entity.

Those gaps require separately reviewed product contracts and, especially for
cloud-native failure/incident handling, more than evaluator-only work. Building
or measuring the fixture now would force the evaluator to invent authority or
misuse Kubernetes semantics.

## 3. Accepted architectural constraints

This audit applies the accepted Truth Substrate and lineage baselines:

- TC-1 requires source-native, scoped, deterministic identity and permits
  unresolved or ambiguous results instead of fuzzy matching.
- TC-2 requires explicit assertion provenance on product graph relationships.
- TC-3 keeps source/effective, observed, and recorded time distinct and never
  uses arbitrary later topology for historical RCA.
- TC-4 keeps supporting, contradicting, and missing evidence separate;
  unknown or absent evidence is not contradiction.
- TC-5 treats causal scores as uncalibrated heuristic rankings, never
  probability.
- LINEAGE-1 proved one exact GitHub Actions/BuildKit/Kubernetes chain.
- LINEAGE-2A established robustness only for its frozen distractor matrix.
- LINEAGE-2B.2 and LINEAGE-2B.3 established that exact attribution did not
  cross missing Run -> Image or Image -> affected-workload boundaries.

The corresponding LINEAGE-3 rule is:

> Do not cross a missing Terraform apply, AWS session, provider mutation,
> resource identity, or runtime-failure boundary. Preserve independently
> established facts and abstain.

## 4. Current implementation inventory

| Capability | Current implementation | Current truth boundary | Classification |
|---|---|---|---|
| GitHub source mutation | Signed webhook plus provider REST enrichment persists `SourceFileMutationEvidence` under `ChangeEventRecord.metadata_json` | Exact repository ID, commit, parent, path, provider blob IDs and bounded content hashes; semantic text only under the bounded scalar policy | `ALREADY_SUPPORTED` |
| GitHub repository/commit graph | `github_graph.py` creates repository and commit entities | Provider repository database ID and repository-scoped commit SHA | `ALREADY_SUPPORTED` |
| GitHub Actions run graph | `github_actions_graph.py` creates `GitHubWorkflowRun`; observed Commit `triggers` Run | Provider run ID, attempt as a property, head SHA, workflow metadata | `ALREADY_SUPPORTED` with the known run-attempt identity limitation |
| Terraform Cloud webhook | HMAC SHA-512 verification and `normalize_terraform_cloud()` | Authenticated run/workspace notification, trigger, status, actor, run time | `ALREADY_SUPPORTED` only as change/run evidence |
| Terraform plan/state/HCL | No parser, collector, evidence model, graph entity, repository, or test exists | None | `NOT_REPRESENTABLE` today |
| AWS inventory | Agent plugin polls account/region, VPC, subnet, route, security, EC2, EKS, ELB, RDS, and Lambda inventory | Provider resource fields observed through the authenticated AWS SDK | `ALREADY_SUPPORTED` but connector maturity remains partial |
| Lambda topology | `aws_lambda_function` becomes `AWSLambdaFunction`; canonical identity uses account, region, resource type, and resource ID; ARN is retained as source-native identity | Function ARN/name, account, region, runtime, handler, role, memory, timeout, package type, architecture, VPC/security-group context | `ALREADY_SUPPORTED` for inventory identity, not configuration-change or runtime truth |
| AWS topology provenance | `agent_cloud_enrichment.py` creates TC-2 provenance for cloud scope and selected attachment/routing edges | Provider inventory references at snapshot collection time | `ALREADY_SUPPORTED` for existing edges; no Terraform edge |
| CloudTrail polling | `AwsCloudTrailChangePoller` calls `LookupEvents`, filters reads, and submits authenticated agent change events | Event ID, name, outer event time, configured region, account, basic resource references, request ID | `ALREADY_SUPPORTED` only as a partial mutation observation |
| CloudTrail durable event | Generic `ChangeEventRecord` can persist metadata/raw JSON and TC-3 time | The poller currently submits `raw_payload={}` and discards most provider fields | `MINIMAL_PRODUCT_GAP` |
| CloudWatch/Lambda runtime | No CloudWatch Logs, Lambda invocation, Lambda metrics, or AWS runtime-failure collector/model exists | None | `MAJOR_PRODUCT_EXPANSION` |
| Signals | `SignalType` contains only `kubernetes_event`; `NormalizedSignal.cluster_name` is required | Kubernetes object failures only | `MAJOR_PRODUCT_EXPANSION` for honest AWS-native incidents |
| Automatic incident lifecycle | Failure qualification, entity resolution, checkpoint pinning, and automatic RCA are Kubernetes/cluster-shaped | Exact Kubernetes entity in an incident-boundary snapshot | `MAJOR_PRODUCT_EXPANSION` for Lambda-only scope |
| Causal candidate admission | Terraform and CloudTrail events are primary-eligible source-native mutations | Eligibility only; it does not prove source-to-resource lineage | `ALREADY_SUPPORTED` but insufficient for the target claim |
| Exact lineage admission | `lineage_candidate_admission.py` implements only GitHub source -> Actions/BuildKit image -> Kubernetes workload | Exact immutable container image path | `NOT_REPRESENTABLE` for Terraform/AWS today |
| Causal relevance | A directly linked change can reach a pinned topology entity; the special cross-domain bridge is container-image-specific | Exact candidate entity or accepted immutable-image bridge | `MINIMAL_PRODUCT_GAP` for a separately contracted Terraform/AWS bridge |
| Historical topology | Immutable snapshots and incident pins; TC-3 forbids arbitrary latest/later fallback | Incident-pinned or safe at-or-before topology | `ALREADY_SUPPORTED` |

No current dependency or source scan found Terraform CLI execution, HCL parsing,
`terraform show -json`, plan/state parsing, CloudWatch Logs collection, Lambda
runtime signals, or a Terraform-to-AWS resource lineage model.

## 5. Three-layer authority map

The layers mean:

1. **Authoritative observation** — what a provider or authenticated collector
   directly reports.
2. **Derived claim** — deterministic interpretation joining exact observations.
3. **Causal use** — whether the current causal system may use that claim to
   support the target source-level hypothesis.

| Hop | Authoritative observation | Derived claim | Causal use today | Current state / gap |
|---|---|---|---|---|
| Repository -> Commit | GitHub repository database ID and commit SHA | Repository-scoped commit identity and observed `contains` edge | Supported as exact source identity | `ALREADY_SUPPORTED` |
| Commit -> Terraform source mutation | Signed push plus GitHub commit/file/blob APIs | Exact `SourceFileMutationEvidence` | Can support `source_change`; does not itself name a Terraform address | `ALREADY_SUPPORTED`, with HCL semantic mapping absent |
| Commit -> GitHub Actions Run | GitHub run ID/head SHA/run attempt | Observed Commit `triggers` Run | Can participate in provider-backed event/artifact lineage | `ALREADY_SUPPORTED` |
| Run -> Terraform plan | No current observation | None | None | `MINIMAL_PRODUCT_GAP` |
| Run -> Terraform apply | HCP Terraform can report its own run, but current data does not bind a GitHub Actions run to a local/remote apply | At most a temporal run association | Must not be used as exact lineage | `MINIMAL_PRODUCT_GAP` |
| Terraform source path -> resource address | GitHub proves a changed path; current product does not parse HCL or plan configuration | None | None | `MINIMAL_PRODUCT_GAP` |
| Terraform resource address -> applied AWS resource | State/plan/apply data is not collected; configured `entity_refs` are static hints | Generic entity link only when a caller already supplies a real provider ID | Static configuration is not apply proof | `MINIMAL_PRODUCT_GAP` |
| Actions Run -> AWS role/session | Future OIDC session naming is feasible; current workflow/collector does not persist it | None | None | `MINIMAL_PRODUCT_GAP` plus `PROVIDER_SEED_REQUIREMENT` |
| AWS role/session -> CloudTrail event | CloudTrail raw `userIdentity` could establish it; current poller discards it | Actor currently collapses to `LookupEvents.Username` | Not exact enough | `MINIMAL_PRODUCT_GAP` |
| CloudTrail event -> AWS resource ARN | `Events[].Resources` and raw event fields may expose identity | `ChangeEventEntityReference` can resolve a strong provider ID against a pinned snapshot | Direct relevance is possible only if exact resolution succeeds | `PARTIAL`; resource-kind and region normalization gaps remain |
| AWS resource -> runtime telemetry | No current Lambda/CloudWatch observation | None | None | `MAJOR_PRODUCT_EXPANSION` |
| Runtime telemetry -> incident | Current signal/lifecycle model accepts Kubernetes failure semantics | None for AWS | None | `MAJOR_PRODUCT_EXPANSION` |
| Source mutation -> affected AWS runtime relevance | The necessary source/apply/session/resource/runtime facts are not all represented | Current heuristic event-chain correlation is insufficient | Exact `INITIATING_MUTATION` must abstain | `NOT_REPRESENTABLE` today |

## 6. Identity representability map (TC-1)

| Identity | Minimum exact identity | Current support | Finding |
|---|---|---|---|
| Repository | GitHub host + provider repository database ID | Existing canonical repository identity | Exact |
| Commit | Canonical repository ID + lowercase full SHA | Existing canonical commit identity | Exact |
| Source mutation | Provider repository ID + commit/parent + exact path(s) + before/after blob IDs | Existing source-file mutation identity | Exact when enrichment is complete |
| Actions Run | GitHub host + provider run ID; attempt retained separately | Existing run identity | Exact run, but rerun attempt is not part of canonical entity ID |
| Terraform run | Provider + organization/workspace ID + run ID | Current event external ID uses workspace/run/trigger/index and metadata retains workspace ID/org | Partial; notification identity is not a reusable canonical Terraform identity |
| Terraform plan/apply receipt | Provider/run/attempt + plan/apply identity and provider artifact digest | No model | Missing |
| Terraform resource address | State lineage/workspace + module path + resource mode/type/name + instance key, expressed as the full absolute Terraform address | No model | Missing; an unscoped address is not globally unique |
| AWS account | Provider account ID | AWS account inventory and STS identity | Exact when collected |
| AWS region | Provider region | Entity properties and graph scope relationship | Exact when collected |
| AWS role/session | Role ARN + provider session/principal ID + exact session name; run/attempt must be independently bound | Agent has a configurable discovery session name but CloudTrail event identity is discarded | Missing for workload mutation provenance |
| CloudTrail event | AWS account + event ID, with event source/name/time/region retained independently | External ID contains `cloudtrail:{EventId}` | Event identity exact; evidence payload incomplete |
| Lambda resource | Unqualified Lambda function ARN, account, region, resource type, function name | Existing AWS canonical identity and ARN source-native ID | Exact for inventory |
| Runtime invocation/log event | Lambda ARN + invocation request ID and/or CloudWatch log group/stream/event ID | No model | Missing |
| Runtime signal | Source-specific stable signal ID over Lambda ARN, invocation/log event ID, and failure category | Signal model only supports Kubernetes | Missing |

Display names, function names without account/region, Terraform addresses without
workspace/state scope, session-name parsing without provider corroboration, and
CloudWatch log-group naming alone are not sufficient identity.

### Current CloudTrail-to-Lambda resolution limitation

The current poller forwards `Resources[].ResourceName` as
`provider_resource_id` and `ResourceType` as `kind`. Exact native ID resolution
can work when the value equals the stored Lambda ARN or resource ID and the kind
vocabulary agrees. It can fail when CloudTrail emits `AWS::Lambda::Function`
while topology stores `AWSLambdaFunction`. Region is present on the event but
is not currently an explicit filter in `resolve_snapshot_entity_identity()`;
function-name-only references can therefore become ambiguous across regions.
No fuzzy fallback is acceptable. This requires an explicit AWS resource-type
normalizer and region-aware exact scope matching.

## 7. Relationship and provenance map (TC-2)

| Conceptual relation | Current representation | Required provenance | Finding |
|---|---|---|---|
| Repository -> Commit | `contains`, observed | Repository provider ID + commit SHA + source component/version | Existing |
| Commit -> Actions Run | `triggers`, observed | Commit SHA + provider run ID/attempt | Existing; attempt limitation remains |
| Run -> Terraform plan/apply | No active graph predicate or typed evidence relationship | Provider artifact/run/attempt, Terraform version, receipt digest, exact plan/apply identity | Missing |
| Terraform source mutation -> resource address | No relationship | Source mutation ID plus deterministic HCL/config/plan mapping authority | Missing |
| Terraform apply/resource address -> AWS ARN | No relationship | Apply receipt, state-derived provider ID, CloudTrail corroboration, exact account/region/ARN | Missing |
| AWS Region -> Lambda | `contains`, declared inventory relationship | AWS scope/resource references, `aws-inventory-linker:v1` | Existing structural context only; `contains` is not causal dependency |
| CloudTrail change -> Lambda | `ChangeEntityLinkRecord`, not a topology relationship | Event ID, exact native resolution, snapshot ID and resolution strategy | Partially representable |
| Lambda -> runtime failure | Durable signal should name the Lambda entity; no topology edge is inherently required | Exact signal/provider references and TC-3 time | Missing |

The inactive enum predicates `deploys`, `emits`, `observes`, `affects`, and
`derived_from` must not be activated merely to make the diagram look complete.
`produces` is not semantically correct for Terraform mutating a long-lived AWS
resource. A narrow future implementation can keep plan/apply/resource lineage
as typed provider evidence and use the existing durable `entity_linkage` claim
to the real Lambda entity. A new graph predicate or Terraform graph entity
requires a separate TC-1/TC-2 contract and is not assumed by this audit.

## 8. Temporal representability map (TC-3)

| Fact | Authoritative/effective time | Observation time | Recorded time | Current support |
|---|---|---|---|---|
| Commit/source mutation | GitHub commit timestamp and provider commit/blob identity | Verified webhook/provider enrichment receipt | DB creation | Supported |
| Actions Run | Provider run start/update/completion fields | Connector/webhook receipt | DB/snapshot persistence | Supported |
| Terraform plan | Terraform CLI/provider plan creation time, if explicitly emitted | Workflow artifact observation | Evidence persistence | Missing |
| Terraform apply | Provider/apply start and completion time; success must be distinct from plan | Workflow/HCP notification receipt | Evidence persistence | Partial for HCP run time, absent for exact Actions-run apply |
| CloudTrail mutation | Raw `eventTime` | Authenticated agent poll time | Change-event persistence time | Source time supported; observation/record time supported |
| AWS resource state | AWS inventory collection time; it is not the exact mutation time | Same collection | Snapshot persistence | Supported as bounded observation only |
| Lambda runtime failure | CloudWatch log event time and invocation request time | Collector poll/receipt | Signal persistence | Missing |
| Incident boundary | Exact runtime signal effective time | Topo receipt | Incident creation | Missing for AWS; supported for Kubernetes |

CloudTrail `eventTime` and Lambda/CloudWatch event time must remain separate.
An AWS API mutation may precede effective configuration, invocation, and log
delivery. Inventory `collected_at` cannot be rewritten as exact mutation time,
and late CloudWatch delivery cannot rewrite the incident boundary. The pinned
snapshot must be the explicit incident-boundary snapshot or a scope-compatible
snapshot collected at or before that boundary; no latest or arbitrary later
snapshot is allowed.

## 9. Terraform evidence strategy

### 9.1 Current authority

The current Terraform Cloud webhook proves that HCP Terraform sent a signed
notification for a named run/workspace and status. It does not include or
prove:

- an exact GitHub Actions run/attempt;
- HCL source-to-resource mapping;
- plan resource changes;
- successful application of one exact resource action;
- provider-generated AWS ARN/ID;
- the AWS principal that performed the action; or
- the independently observed AWS API mutation.

Configured `entity_refs` can help correlate a known resource, but they are
configuration supplied in advance and cannot prove that a particular run
planned or applied that resource.

### 9.2 Future minimum portable receipt

A future controlled workflow should execute Terraform normally but export only
a sanitized, typed receipt. The minimum defensible receipt should contain:

- receipt schema/version and Terraform CLI version;
- GitHub repository ID/name, commit SHA, run ID, and run attempt;
- provider-managed GitHub artifact ID, URL, digest, and observation time;
- Terraform organization/workspace or backend/state-lineage scope;
- plan identity/hash and apply identity/status/times;
- full absolute resource address including module and instance key;
- provider source and resource type;
- plan actions (`create`, `update`, `delete`, or replacement sequence);
- exact changed attribute path needed by the controlled case;
- bounded non-sensitive before/after values or hashes under an explicit policy;
- post-apply provider ID/ARN extracted from state/provider output;
- state lineage/serial or equivalent scope needed to prevent address collision;
- completeness and explicit missing/conflict reasons; and
- hashes of source artifacts inspected without retaining unsafe raw content.

The receipt must be tied to the provider-managed Actions artifact endpoint and
the exact run/attempt, analogous to the accepted BuildKit evidence approach.
Workflow prose, console logs, a local filename, timestamps alone, and a
fixture-authored `terraform output` without independent provider corroboration
are insufficient.

### 9.3 Source path -> resource address

`terraform show -json plan` is authoritative for Terraform's planned resource
address and action. It is not necessarily authoritative for the source file and
source range that produced the configuration. A future extractor therefore
needs a deterministic HCL/configuration mapping that proves the exact changed
source path/attribute participates in the exact resource address. Matching only
the repository, run, value text, or a single-resource fixture is not enough.

For the proposed fixture, a narrow one-line non-sensitive variable input can
make before/after source identity auditable, while the plan receipt separately
records the Lambda environment attribute change at the exact resource address.
The equality of those provider-observed values is a deterministic derived
claim, not an independent provider observation by itself.

### 9.4 Resource address -> actual AWS identity

Post-apply Terraform state can report the provider-generated ARN/ID associated
with an exact resource address. State is Terraform's observation and can be
stale or incomplete; it must be independently corroborated by CloudTrail and
AWS inventory. The chain should require agreement among:

```text
Terraform resource address and post-apply ARN
    == CloudTrail mutated resource identity
    == incident-pinned AWSLambdaFunction ARN
```

Disagreement is contradiction or ambiguity according to the exact source;
absence remains missing evidence. No first-match or name-only selection is
allowed.

## 10. Terraform plan/state security assessment

Raw Terraform plan JSON, plan binaries, and state can contain passwords,
tokens, environment variables, database data, private keys, rendered user
data, and provider-specific sensitive values under arbitrary keys. The current
generic webhook key-name redactor cannot make them safe.

Therefore a future program must:

- never persist or commit raw `.tfstate`, plan binaries, or complete
  `terraform show -json` output;
- parse in an ephemeral controlled process;
- use an allowlist, not a denylist, for persisted fields;
- reject unknown/unbounded fields;
- honor Terraform sensitive markers and treat all unclassified values as
  sensitive;
- retain only the exact non-sensitive fixture attribute when its policy is
  explicit, otherwise retain a hash and typed presence/change state;
- exclude credentials, OIDC tokens, STS credentials, environment maps, backend
  configuration, provider secrets, and raw logs;
- record provider artifact/content hashes for integrity;
- redact paths only when they can expose local runner secrets; repository paths
  remain exact provider-controlled identities; and
- make the eventual seed and result family pass EAI-1 after all ordinary
  artifacts are finalized.

## 11. GitHub Actions -> AWS session feasibility

The future design is feasible but not implemented.

Preferred controlled setup:

```text
GitHub Actions OIDC
  + AWS role trust restricted to exact repository/ref/environment
  + explicit role-session-name containing github.run_id and run_attempt
  + CloudTrail STS observation
  + CloudTrail Lambda mutation under that same role/session
```

Minimum proof should include:

1. exact GitHub run ID/attempt/head SHA from the provider API;
2. exact configured role ARN and session-name policy from the controlled
   workflow/fixture contract;
3. a CloudTrail `AssumeRoleWithWebIdentity` observation where available,
   retaining the identity-provider/subject and requested session name under an
   allowlist;
4. the Lambda mutation event's `userIdentity` showing the same role/session or
   principal identifier; and
5. exact temporal ordering and account/region consistency.

Parsing a run ID out of a session name alone is not enough. The role trust,
provider run, STS event, and resource event must agree. The current agent
`aws_role_session_name` is only the Topo discovery session and is unrelated to
the future workload mutation session.

## 12. CloudTrail evidence strategy

### 12.1 Fields currently preserved

| CloudTrail field | Current state |
|---|---|
| `eventID` | Preserved inside `external_id=cloudtrail:{EventId}` |
| `eventName` | Preserved in title/metadata |
| `eventTime` | Preserved as `occurred_at` with TC-3 source hint |
| `eventSource` | Preserved in summary/metadata |
| `awsRegion` | Uses the configured poll region rather than explicitly retaining raw `awsRegion` |
| `recipientAccountId` | Preserved from raw event |
| `requestID` | Preserved in metadata |
| outer `Resources` | Partially preserved as provider resource references |
| `userIdentity` | Discarded |
| session issuer/session name | Discarded |
| `sourceIPAddress` | Discarded |
| `requestParameters` | Discarded |
| `responseElements` | Discarded |
| raw resources/ARN fields | Only the bounded outer lookup projection survives |
| complete raw event | Explicitly discarded; `raw_payload={}` |

### 12.2 Minimum future allowlist

The provider evidence needed for this controlled chain is:

- `eventID`, `eventVersion`, `eventSource`, `eventName`, `eventTime`,
  `awsRegion`, `recipientAccountId`, `readOnly`, and `requestID`;
- `userIdentity.type`, `principalId`, account, ARN, and bounded session context;
- session issuer ARN/name and exact session name;
- identity-provider and OIDC subject fields when available;
- exact resource ARN/type from `resources` or a typed request field;
- the Lambda function name/ARN and non-sensitive concurrency/version/revision
  identifiers relevant to the action;
- a raw-event content hash and collection/record times; and
- explicit completeness and source-field paths.

Full `requestParameters`, `responseElements`, `environment.variables`, source
IP addresses, user agents, credentials, or access tokens should not be stored
by default. A source IP is not needed for the target proof. Arbitrary request
parameters can contain secrets and must be reduced through an event-specific
allowlist.

CloudTrail proves that AWS recorded an API action by a principal against a
resource. It does not alone prove that the resulting configuration became
effective or caused a runtime failure.

## 13. Runtime-failure strategy

### 13.1 Current capability

The AWS plugin discovers Lambda configuration inventory but does not collect:

- Lambda invocations;
- invocation request IDs or `FunctionError` responses;
- CloudWatch Logs groups, streams, or log events;
- Lambda error metrics or dimensions;
- effective configuration revisions associated with a failure; or
- AWS-native `NormalizedSignal` records.

The Lambda inventory projection also omits provider fields such as
`LastModified` and `RevisionId` and deliberately does not collect environment
variables. A normal Terraform change to `RUNTIME_MODE` may therefore leave the
current material topology digest unchanged even though CloudTrail records a
configuration mutation.

### 13.2 Minimum future provider-backed proof

For the controlled fixture, use two independent runtime observations where
possible:

1. an AWS Lambda invocation response containing the provider request ID,
   executed version, status code, and `FunctionError`; and
2. a CloudWatch Logs event from the exact Lambda log group/stream with the same
   request ID, exact event timestamp/event ID, and a stable bounded failure
   marker emitted by the fixture.

The exact Lambda ARN is resolved from account/region/function identity and
must agree with the Terraform, CloudTrail, inventory, invocation, and log
observations. An aggregated `AWS/Lambda Errors` metric with a FunctionName
dimension can be supplementary evidence, but it is not sufficient to identify
one exact invocation or cause.

The product must normalize this into a durable AWS runtime signal with TC-3
time and exact involved entity identity. Raw application log bodies should not
be persisted; retain a bounded safe marker or content hash and the provider
event/request identifiers.

## 14. Incident and historical-topology strategy

Current incident and signal models require `cluster_name`, and the automatic
failure lifecycle recognizes Kubernetes semantics. Assigning a value such as
`aws-prod` to `cluster_name` would make the fixture run but would not make the
evidence truthful.

A future cloud-native incident contract needs an explicit operational scope,
at minimum:

- provider `aws`;
- account ID;
- region;
- environment where configured;
- exact affected AWS entity ID/ARN;
- primary AWS runtime signal ID; and
- an incident-time topology snapshot that contains the exact Lambda entity.

AWS inventory currently enters snapshots through an enrolled agent submission,
whose snapshot scope is still cluster-shaped. General cloud scope and snapshot
selection therefore require an architect-reviewed extension rather than a
fixture-specific fake cluster.

The historical selection rule remains unchanged in principle:

```text
explicit incident-boundary snapshot
    else scope-compatible snapshot collected at/before runtime failure
    else no topology
```

No latest, post-failure, or post-repair snapshot may be attached merely because
it contains the Lambda.

## 15. Causal representability and TC-4 claims

Terraform and CloudTrail events are already primary-eligible candidates, but
eligibility is not proof. Current 13C event lineage uses bounded heuristic
signals such as common commit, repository, pipeline, entity, scope, and time.
It cannot replace provider authority.

The existing exact-lineage admission path is hard-coded to:

```text
GitHub source mutation
  -> BuildArtifactEvidence
  -> immutable ContainerImage
  -> Kubernetes Deployment/Pod
```

It cannot admit an old Terraform source mutation through AWS lineage, and
`causal-relevance-v2` can use only its container-image-specific bridge or a
direct topology entity link.

The future Lambda chain can reuse existing TC-4 claim types without inventing
names solely for symmetry:

| Existing claim type | Future use |
|---|---|
| `source_change` | Exact Terraform input/source mutation |
| `event_lineage` | Commit -> Run -> plan/apply -> CloudTrail event |
| `identity_resolution` | Exact repository/run/address/session/ARN/signal identities |
| `entity_linkage` | Exact provider evidence and CloudTrail mutation linked to the pinned Lambda entity |
| `relationship_provenance` | Any real TC-2 topology edge used after the Lambda anchor |
| `temporal_precedence` | Source, run, apply, CloudTrail, runtime, and incident ordering |
| `runtime_failure` | Durable Lambda invocation/CloudWatch failure signal |
| `topology_path` | Pinned Lambda-to-affected-runtime path if a distinct runtime entity exists |

`artifact_provenance` should not be mislabeled as resource provenance. If the
existing types cannot express one required proof without semantic distortion,
that is a contract gap requiring architect review; this audit does not add a
new TC-4 type.

The future support gate must fail closed when any required boundary is missing,
ambiguous, conflicting, post-incident, or outside the pinned topology. TC-5
must continue to report an uncalibrated ranking, not a causal probability.

## 16. Candidate fixture comparison

| Dimension | A. Lambda configuration failure | B. Existing EC2/EKS/ALB-style alternative |
|---|---|---|
| Existing Topo entity | `AWSLambdaFunction` exists | EC2/EKS/ALB entities exist; ECS does not |
| Stable provider identity | Exact Lambda ARN/account/region | Exact provider IDs exist |
| Controlled mutation | One bounded environment/configuration value | Often node group, security, routing, or compute mutation with broader effects |
| Runtime determinism | One invocation can throw a stable marker | Runtime effect is slower, indirect, or dependent on Kubernetes/network behavior |
| Provider mutation evidence | Lambda CloudTrail API event can be narrowly scoped | EKS/EC2/network changes can emit several asynchronous events |
| Runtime observability | CloudWatch request/log identity is strong but missing from Topo | Existing Topo runtime signals are Kubernetes-only; AWS host/ALB telemetry is also missing |
| Blast radius | One disposable function; tightly bounded | EKS/EC2/network paths have larger operational blast radius |
| Cost | Low, short-lived invocation/log storage | Higher and less predictable |
| Seed reproducibility | High once receipt collectors exist | Lower because rollout/network/host state is more variable |
| Current relationship quality | Direct Lambda ARN can anchor topology | EKS-to-Kubernetes bridge is currently inferred by name; not suitable as positive proof |
| Product expansion | Significant but narrow and evidence-focused | Does not remove the core AWS signal/incident gap and adds indirect topology questions |

**Selected fixture: A. AWS Lambda configuration-failure fixture.**

The alternative would not materially reduce the missing product surface. It
would trade one clear Lambda runtime collector for weaker, more expensive, and
less deterministic cross-system runtime evidence. Lambda is preferred because
it maximizes evidence quality and minimizes cost and blast radius—not because
it is easy to simulate.

## 17. Atomicity and nonseparability analysis

The LINEAGE-2B atomicity doctrine applies. A future adversarial evaluator may
remove only independently representable authorities.

| Observation | Atomic/nonseparable unit | Separability rule |
|---|---|---|
| GitHub source-file mutation | One provider mutation record includes repository/commit/path/before/after identity | Individual file mutations are separable only when independently persisted; blob identity cannot remain as hidden proof after removing that mutation |
| Commit -> Actions Run | One observed trigger claim from provider run/head SHA | Run metadata may remain while the trigger relationship/evidence is removed only if the two are separately persisted and the counterfactual preserves the run without claiming the trigger |
| Terraform plan resource change | Address, action, changed attribute and plan identity form one plan observation | Do not remove the address while retaining a claim-specific attribute that uniquely reconstructs it |
| Terraform apply receipt | Apply status/time/resource result under one exact run/attempt | Plan and apply are independently observable and removable; plan success must not stand in for apply success |
| Terraform state address -> ARN | Address and provider-returned ID are one state observation | Removing this boundary requires removing every claim-specific copy/counter/reference that reconstructs the same mapping |
| AWS STS session | Role, session name, principal identity and provider time in one provider event | Session-name text alone is not an independent authority |
| CloudTrail resource mutation | Event ID/name/time/principal/resource/request identity belong to one provider event | Derived entity links and counters must be removed with the authoritative event in a broken-hop test |
| AWS inventory Lambda | ARN/configuration observed in one collection | Inventory is independent of CloudTrail and can be preserved when CloudTrail is removed |
| Invocation response | Request ID/status/FunctionError/executed version are one response | Independently separable from CloudWatch log observation |
| CloudWatch log event | Log group/stream/event ID/time/request ID/failure marker are one log observation | Independently separable from invocation response and metrics |
| Incident pin | Incident boundary, primary signal and snapshot association form the historical claim | The snapshot can exist independently, but an evaluator cannot keep a hidden equivalent pin after removing the pin claim |

Candidate future removable boundaries are:

1. Run -> Terraform apply;
2. Terraform source/plan -> resource address;
3. Terraform apply/state -> AWS ARN;
4. Actions Run -> AWS session;
5. AWS session -> CloudTrail mutation;
6. CloudTrail mutation -> Lambda entity;
7. Lambda entity -> runtime failure; and
8. runtime failure -> incident/pin.

No evaluator should be written until the accepted product representation makes
each proposed cut independently expressible.

## 18. Offline seed strategy

After the product can represent the chain, provider/network access should be
required only during one explicitly authorized seed-acquisition run.

The future acquisition would collect:

- GitHub repository/commit/source mutation and workflow run/attempt receipts;
- the sanitized Terraform plan/apply/resource receipt;
- OIDC/STS and CloudTrail mutation receipts;
- AWS Lambda inventory with exact ARN;
- invocation and CloudWatch failure receipts;
- the normalized AWS runtime signal, incident, and incident-boundary snapshot;
- the persisted causal analysis and TC-4 ledger; and
- independent expected-truth receipts that do not use Topo output.

The resulting product database and sanitized receipts can be copied into an
ignored evaluation seed. Later CONTROL/adversarial evaluation should run fully
offline against byte-identical isolated copies. It must not call GitHub, AWS,
Terraform Cloud, a registry, Kubernetes, an LLM, or current/latest topology.

EAI-1 must cover all ordinary result artifacts after finalization. Provider
credentials, Terraform state, plan binaries, raw CloudTrail payloads, raw log
bodies, and AWS resources are never evaluation artifacts.

## 19. Provider seed-acquisition requirements

A future controlled seed requires explicit, bounded authorization for:

- one disposable GitHub Actions workflow run and exact run attempt;
- GitHub OIDC to one least-privilege disposable AWS role;
- one dedicated AWS account or tightly scoped evaluation account/region;
- Terraform backend/state handling in an ephemeral or dedicated workspace;
- creating/updating and invoking one disposable Lambda function;
- reading the exact CloudTrail management events needed for the fixture;
- reading the dedicated Lambda CloudWatch log group/events;
- AWS inventory access for the function and its tags;
- deterministic cleanup of Lambda, IAM role/policy, log group, and Terraform
  workspace/state according to a separately reviewed guard; and
- capturing receipts before cleanup without storing credentials or raw state.

The existing discovery policy lacks `cloudtrail:LookupEvents` and CloudWatch
Logs permissions. It must not be broadened globally for a fixture; use a
fixture-specific, least-privilege acquisition role and a separately reviewed
policy.

## 20. Exact gap classification

| Missing or existing capability | Classification | Reason |
|---|---|---|
| Exact GitHub repository/commit/source mutation | `ALREADY_SUPPORTED` | Accepted source evidence contract and LINEAGE-1 proof |
| Exact GitHub Commit -> Actions Run | `ALREADY_SUPPORTED` | TC-1/TC-2 provider run/head-SHA representation |
| Terraform Cloud signed run notification | `ALREADY_SUPPORTED` | HMAC verification and durable change event |
| Terraform plan/apply artifact ingestion | `MINIMAL_PRODUCT_GAP` | Narrow typed evidence model/parser and persistence needed |
| HCL source path/attribute -> resource address | `MINIMAL_PRODUCT_GAP` | Deterministic source/config mapper required |
| Terraform resource address scoped identity | `MINIMAL_PRODUCT_GAP` | Typed evidence identity required; graph entity not assumed |
| Terraform state/provider ID sanitization | `MINIMAL_PRODUCT_GAP` | Allowlisted local extraction required |
| Run -> Terraform apply authority | `MINIMAL_PRODUCT_GAP` | Provider artifact/run/attempt linkage required |
| GitHub Run -> AWS OIDC session | `MINIMAL_PRODUCT_GAP` plus `PROVIDER_SEED_REQUIREMENT` | Session and provider evidence can be modeled narrowly |
| CloudTrail identity/session/resource preservation | `MINIMAL_PRODUCT_GAP` | Existing poller discards needed fields |
| AWS resource-type normalization and region-scoped resolution | `MINIMAL_PRODUCT_GAP` | Exact deterministic mapper/resolver extension |
| Lambda inventory ARN identity | `ALREADY_SUPPORTED` | Existing TC-1 AWS entity |
| Lambda effective configuration revision observation | `MINIMAL_PRODUCT_GAP` | Current projection omits revision/update fields; secrets must remain excluded |
| Lambda invocation/CloudWatch runtime collector | `MAJOR_PRODUCT_EXPANSION` | Entire runtime source is absent |
| AWS runtime signal type | `MAJOR_PRODUCT_EXPANSION` | Signal enum and ingestion are Kubernetes-only |
| Cloud-native incident/snapshot scope | `MAJOR_PRODUCT_EXPANSION` | Current lifecycle and persistence require cluster semantics |
| Terraform/AWS exact-lineage admission/relevance | `MINIMAL_PRODUCT_GAP` after evidence exists | Narrow provider bridge can reuse existing candidate/relevance architecture |
| Offline evaluator, grading, determinism and adversarial cuts | `EVALUATOR_ONLY_NEEDED` after product representability | Harness work must follow, not precede, authority |
| One real provider-backed seed | `PROVIDER_SEED_REQUIREMENT` | Cannot be fabricated offline |
| End-to-end source mutation -> AWS runtime proof today | `NOT_REPRESENTABLE` | Required boundaries are absent |

The major-expansion risk is not Terraform parsing by itself. It is introducing
general AWS telemetry and cloud-native incident lifecycle semantics without a
separate architecture contract. That work must not be smuggled into an
evaluation fixture.

## 21. Minimum implementation sequence before measurement

This is a recommended sequence, not authorization to implement it here.

1. **Cloud scope contract:** define provider/account/region snapshot, signal,
   incident, correlation, and historical-selection semantics without faking a
   Kubernetes cluster.
2. **Terraform evidence contract:** define a sanitized, versioned
   plan/apply/resource receipt and deterministic identities, bounds, and
   sensitive-data policy.
3. **Provider artifact ingestion:** bind the receipt to exact GitHub repository,
   commit, run ID, run attempt, and provider-managed artifact digest.
4. **Source/config mapper:** establish exact source mutation -> Terraform
   address under a bounded HCL/config contract.
5. **CloudTrail preservation:** retain the minimum allowlisted session,
   resource, request, and temporal fields; normalize AWS resource types and
   region scope exactly.
6. **AWS runtime signal:** collect one exact Lambda invocation/CloudWatch
   failure and persist it under the cloud scope contract.
7. **Incident-boundary pinning:** automatically create/correlate the AWS
   incident and pin only a historically valid AWS topology snapshot.
8. **Terraform/AWS causal bridge:** admit the exact source candidate only when
   the full persisted provider chain is complete; reuse existing ranking and
   support-gate principles without bonuses or forced Top1.
9. **Controlled seed contract and authorization:** freeze independent source,
   provider, runtime, cleanup, and security receipts before calling AWS.
10. **Offline evaluator:** build CONTROL first, then adversarial cuts only at
    independently representable boundaries.

Each product step requires focused tests and architect review. No score,
lookback, confidence, or candidate-cap change is justified by this audit.

## 22. Positive-proof acceptance criteria

The future controlled measurement may claim the exact Terraform mutation as
`INITIATING_MUTATION` only when all of the following are true:

1. independent expected truth identifies the exact repository, parent/failure
   commit, source path, and before/after mutation;
2. provider-authentic GitHub evidence agrees with that truth;
3. the exact commit triggers the exact Actions run/attempt;
4. a provider-scoped artifact proves that run produced the exact Terraform
   plan and successful apply receipt;
5. deterministic configuration evidence maps the exact source mutation to one
   exact Terraform resource address;
6. post-apply provider evidence maps that address to one exact Lambda ARN;
7. OIDC/STS evidence binds the exact Actions run/attempt to the AWS role/session;
8. CloudTrail independently records the expected Lambda mutation by that same
   role/session and exact resource;
9. AWS inventory observes the same Lambda ARN in the incident-time scope;
10. an exact invocation/CloudWatch observation proves the deterministic
    runtime failure on that function;
11. the incident's primary signal resolves to that Lambda in the immutable
    incident-boundary snapshot;
12. all source, plan, apply, CloudTrail, runtime, and incident times are
    ordered under TC-3 without timestamp rewriting;
13. TC-4 exposes source, event lineage, identity, entity linkage, temporal,
    relationship/path where applicable, and runtime-failure evidence with no
    required proof silently missing;
14. the supported hypothesis reaches `INITIATING_MUTATION` without heuristic
    score manipulation, lineage bonus, latest-topology fallback, LLM input, or
    expected-answer leakage; and
15. the result is deterministic on byte-identical offline seed copies and EAI
    validates the finalized result tree.

Top1 equality by itself is not proof. CloudTrail plus temporal proximity is not
proof. Terraform state plus a Lambda error is not proof. Every required
boundary must be present and candidate-specific.

## 23. Future adversarial boundaries

After a positive CONTROL is accepted, later separately contracted scenarios
should test, in first-divergence order:

- missing Run -> Terraform apply receipt;
- missing source/config -> resource address mapping;
- missing Terraform address -> AWS ARN mapping;
- missing Actions Run -> AWS session authority;
- missing AWS session -> CloudTrail mutation authority;
- missing CloudTrail mutation -> Lambda entity linkage;
- missing Lambda -> invocation/log failure linkage;
- plan present but apply failed or was cancelled;
- apply present but CloudTrail resource identity conflicts;
- CloudTrail event occurs after the runtime failure;
- same Terraform address in another workspace/state lineage;
- same function name in another account or region;
- same role used by another Actions run/session;
- multiple resources in one plan with one causal mutation;
- multiple applies from the same commit;
- delayed CloudWatch delivery with earlier source event time;
- inventory snapshot after the incident but no safe incident-time snapshot;
- aggregated error metric without exact invocation evidence; and
- distractor Terraform and CloudTrail changes with no affected-runtime path.

Each cut must preserve all unrelated authoritative observations and remove all
co-referent copies of the severed claim. Expected behavior is reduced
specificity or abstention, never reconstructed provenance.

## 24. Recommended controlled fixture

Choose **A. AWS Lambda configuration-failure fixture**.

Proposed future controlled mutation:

```text
RUNTIME_MODE = "healthy"
    ->
RUNTIME_MODE = "fail"
```

Proposed future runtime behavior:

```text
one exact Lambda invocation
    -> stable bounded failure marker
    -> FunctionError
    -> matching CloudWatch request/log identity
```

The function, role, log group, Terraform workspace/state, and evaluation
artifacts must be disposable and guarded. The mutation should affect no shared
resource and should require no broad network or Kubernetes dependency.

This selection is a fixture recommendation only. Because the verdict is
`BLOCKED`, it is not authorization to build, provision, or measure it.

## 25. Final audit state

| Dimension | Result |
|---|---|
| Current end-to-end representability | `NOT_REPRESENTABLE` |
| Preferred fixture | `A. AWS Lambda configuration-failure fixture` |
| Provider-authentic source identity | Available |
| Terraform plan/apply/resource authority | Missing |
| GitHub Run -> AWS session authority | Feasible later; missing now |
| CloudTrail event identity | Partial |
| CloudTrail session/resource evidence | Missing/partial |
| Lambda topology identity | Available |
| Lambda runtime failure evidence | Missing |
| AWS-native incident lifecycle | Missing |
| Offline evaluation after seed | Feasible after product representation exists |
| Product changes in this audit | None |
| Evaluator changes in this audit | None |
| AWS/Terraform/provider execution | None |
| Final verdict | `BLOCKED` |

## 26. Proposed next block

```text
LINEAGE-3A1 — Cloud Incident Scope + Terraform/AWS Evidence Contract Review
```

That next block should remain architecture/contract work. It should decide
whether the cloud-scope and AWS runtime-signal expansion is justified for the
product before any fixture, provider call, evaluator, or repair is created.

