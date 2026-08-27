# TopoAI V1 Evidence Boundary & Production Hardening Transition v1

Status: **ARCHITECTURE DECISION CANDIDATE**

Date: 2026-08-27

Branch: `architecture/v1-evidence-boundary-production-hardening-v1`

Accepted repository commit reviewed:
`7c4752b497a42a782e8b561e82efb19cdcdd339d`

Accepted repository summary:
`7c4752b docs(evaluation): audit terraform aws representability (#59)`

## 1. Executive decision

TopoAI has established enough evidence-backed causal behavior to define a
defensible first V1 boundary. Broad causal-evidence-family expansion is now
closed for V1, and production hardening becomes the primary engineering
program.

The strongest accepted causal domain is:

```text
GitHub
  -> GitHub Actions
  -> provider-backed BuildKit evidence
  -> immutable container image
  -> Kubernetes workload
  -> runtime failure
  -> incident
  -> incident-pinned topology
  -> evidence-backed RCA
```

This is a deliberately narrow, evidence-bounded claim. It is not a universal
RCA claim, a statistical accuracy claim, a causal-probability claim, or proof
for every Kubernetes, cloud, source, build, or incident family.

LINEAGE-3A0 established that Terraform source -> AWS provider mutation ->
cloud-native runtime failure -> cloud-native incident is not currently
representable without material product expansion. That family is therefore
**deferred for V1**. The `BLOCKED` verdict records disciplined refusal to
fabricate authority; it is not a failed product measurement.

The program transition is:

```text
Past primary question:
Can TopoAI reason about incidents defensibly?

Accepted answer:
Yes, within the explicitly proven Kubernetes lineage family, including safe
specificity reduction when required provenance boundaries are absent.

Current primary question:
Can real teams safely connect TopoAI to a supported environment and operate it
reliably?
```

Production persistence, customer-data isolation, authentication, operational
safety, installation, and design-partner usability now take priority over new
causal families.

## 2. Scope and non-goals

This checkpoint is an architecture decision only. It does not:

- modify product, evaluator, agent, frontend, CLI, workflow, or database code;
- implement Postgres or install/configure Alembic;
- create a schema migration;
- provision AWS, EKS, Kubernetes, or any other infrastructure;
- run Terraform;
- create or run CLOUD-V1-1;
- start LINEAGE-3A1 or another causal scenario;
- create evaluation results, seeds, fixtures, or EAI artifacts;
- alter TC-1 through TC-5, ranking, confidence, or support policy;
- activate 14F, 14G, or 14H in the V1 customer path; or
- authorize autonomous remediation.

## 3. Governing accepted evidence state

### 3.1 Truth Substrate

TC-1 through TC-5 are accepted and remain the governing substrate:

| Contract | Frozen responsibility |
|---|---|
| TC-1 | Source-native canonical identity, deterministic scoped resolution, ambiguity instead of guessing, immutable historical snapshots |
| TC-2 | Explicit observed/declared/derived/inferred relationship provenance and bounded source references |
| TC-3 | Separation of source/effective, observation, and recorded time; incident pin or safe at-or-before topology; no arbitrary latest fallback |
| TC-4 | Per-hypothesis supporting, contradicting, and defensibly missing evidence; unknown is not contradiction |
| TC-5 | Causal values are deterministic heuristic ranking semantics, not calibrated probability |

Correctness regressions remain permanent under the Truth Substrate rule:
real defect -> reproducible scenario -> reviewed repair -> permanent
regression protection.

### 3.2 Accepted evaluation checkpoints

| Checkpoint | Frozen state | Meaning |
|---|---|---|
| LINEAGE-1 | `PROVEN`; `NO_DIVERGENCE` | One controlled provider-backed GitHub Actions/BuildKit/immutable-image/Kubernetes source-to-runtime causal chain was proven |
| LINEAGE-2A | `ROBUST_IN_MEASURED_MATRIX`; `NO_DIVERGENCE`; closed | The accepted causal path remained supported through the frozen temporal-distractor matrix, while false-supported distractors remained zero |
| LINEAGE-2B.1 / B1 | `EXPERIMENT_CONSTRUCTION_BLOCKED`; reason `evidence_model_nonseparable`; measurement `NOT EXECUTED` | Removing Commit -> Run while retaining Run -> Image would have fabricated separability because the atomic build observation also authorized Run -> Image |
| LINEAGE-2B.2 / B2 | `ROBUST_IN_MEASURED_MATRIX`; `NO_DIVERGENCE`; closed | Exact source attribution did not cross a removed Run -> Image provider-provenance boundary |
| LINEAGE-2B.3 / B3 | `ROBUST_IN_MEASURED_MATRIX`; `NO_DIVERGENCE`; closed | Exact source attribution did not cross a removed Image -> affected-workload boundary |
| LINEAGE-3A0 | `BLOCKED FOR MEASUREMENT` | The Terraform/AWS/cloud-runtime chain cannot be represented truthfully without material product architecture |
| EAI-1 | `CONTRACT IMPLEMENTED / VERIFIED` | New finalized evaluation families require deterministic all-regular-file result-tree integrity verification |

The B1 result is neither PASS nor FAIL. Product RCA was not measured because
the proposed counterfactual could not preserve independent truth.

The B2 and B3 results are narrow controlled measurements. Together they show
only that the measured lineage family safely reduced specificity rather than
crossing those two missing boundaries. They do not establish general broken-
lineage correctness.

## 4. Interpretation of LINEAGE-3A0

LINEAGE-3A0 asked whether the product could represent an exact chain from a
Terraform source mutation through a GitHub Actions/Terraform apply and AWS
session/CloudTrail mutation to an exact cloud runtime failure and incident.

The audit found:

- GitHub source mutation and Actions-run identity are representable;
- limited signed Terraform Cloud change/run notification ingestion exists;
- AWS inventory can represent exact Lambda ARN identity;
- CloudTrail polling retains only partial mutation identity;
- typed Terraform plan/apply/resource-address authority is absent;
- GitHub Actions run -> AWS OIDC/STS session authority is absent;
- CloudTrail session and bounded request/resource evidence is not retained;
- Lambda/CloudWatch runtime-failure evidence is absent;
- the signal and automatic incident lifecycle are Kubernetes/cluster-shaped;
- no exact non-container Terraform/AWS causal admission/relevance path exists.

Therefore `BLOCKED` means:

> Measurement was deliberately not attempted because doing so would require
> synthetic authority, a fake Kubernetes cluster scope, or several unreviewed
> product expansions.

It does not mean Topo incorrectly analyzed a supported Terraform/AWS incident.
No such experiment was executed. AWS Lambda remains a preferred future fixture
only if customer evidence later justifies reopening this family.

## 5. V1 causal-evidence expansion state

The following state is frozen:

```text
Truth Substrate TC-1 through TC-5: ACCEPTED
LINEAGE-1: PROVEN
LINEAGE-2A: ROBUST_IN_MEASURED_MATRIX / NO_DIVERGENCE / CLOSED
LINEAGE-2B.1: EXPERIMENT_CONSTRUCTION_BLOCKED / NOT EXECUTED
LINEAGE-2B.2: ROBUST_IN_MEASURED_MATRIX / NO_DIVERGENCE / CLOSED
LINEAGE-2B.3: ROBUST_IN_MEASURED_MATRIX / NO_DIVERGENCE / CLOSED
LINEAGE-3A0: BLOCKED FOR MEASUREMENT
Terraform/AWS causal family: DEFERRED FOR V1
Broad V1 causal-evidence expansion: CLOSED
```

Closed means that the main engineering program will not continue adding
evidence families merely because another connector, cloud, or scenario is
numerically next. It does not stop product development, regression evaluation,
AWS/EKS validation, or future customer-driven reconsideration.

Do not start before design-partner evidence justifies it:

- LINEAGE-3A1 causal product expansion;
- B4, B5, or B6 merely because they remain in the taxonomy;
- Azure or GCP causal parity;
- a generic cloud or Terraform causal engine;
- probability calibration or a large statistical RCA benchmark;
- a graph-database or event-store rewrite;
- a generalized claim-dependency graph; or
- autonomous remediation.

## 6. Supported and defensible V1 product boundary

### 6.1 Strongest proven domain

The strongest currently proven causal domain is:

```text
GitHub source mutation
  -> exact GitHub Actions run/attempt
  -> provider-backed BuildKit evidence
  -> exact immutable OCI image identity
  -> Kubernetes Deployment/Pod image linkage
  -> Kubernetes UID owner chain
  -> durable runtime failure signal
  -> canonical incident
  -> immutable incident-time topology pin
  -> evidence-backed RCA and evidence ledger
```

Within the controlled family, Topo also demonstrated that it abstains from
exact source attribution when independently required Run -> Image or Image ->
workload evidence is removed.

### 6.2 Commercial environment direction

The first commercial optimization direction is:

```text
GitHub
+ GitHub Actions
+ AWS-hosted infrastructure
+ EKS / Kubernetes
+ TopoAI
```

Terraform is common and preferred for creating the disposable environment and
is already accepted as limited change/run evidence. Terraform is not required
for every supported V1 RCA claim and is not part of the causal chain unless a
future reviewed evidence family proves it.

### 6.3 Explicit unsupported claims

V1 must not claim:

- Terraform source mutation -> AWS resource mutation -> runtime incident;
- all Kubernetes environments or failure modes;
- all AWS resources or AWS-native incidents;
- all clouds or cloud causal parity;
- all source-control, CI/CD, build, registry, or deployment systems;
- universal automated RCA;
- guaranteed root-cause discovery;
- calibrated causal probability or a published accuracy percentage;
- confirmed impact for every graph node returned by blast-radius traversal;
- generic on-prem infrastructure support; or
- autonomous or approval-driven remediation execution.

Unsupported breadth must not be inferred from the existence of partial AWS,
Azure, GCP, Terraform, GitLab, Jenkins, or Azure DevOps connectors.

## 7. CLOUD-V1-1 — Real AWS/EKS Golden Environment Validation

### 7.1 Purpose

CLOUD-V1-1 is the next bounded cloud validation program, not another causal-
research program. Its purpose is to prove that the already accepted GitHub ->
Actions -> immutable image -> Kubernetes causal path operates against a real,
disposable AWS EKS environment rather than only the local Docker Desktop
evaluation environment.

It must validate, at minimum:

- real EKS enrollment and connectivity;
- canonical EKS/Kubernetes entity identity;
- automatic topology capture and immutable checkpoints;
- exact GitHub -> Actions -> immutable-image provenance;
- exact image -> Deployment/Pod linkage;
- real runtime-failure detection;
- automatic incident creation;
- immutable incident-time topology pinning;
- existing 13C/TC-4 RCA behavior;
- no latest-topology fallback; and
- deterministic cleanup of disposable AWS infrastructure.

### 7.2 Causal chain under validation

```text
GitHub source mutation
  -> GitHub Actions
  -> immutable image
  -> Deployment on EKS
  -> ReplicaSet
  -> Pod
  -> runtime failure
  -> incident
  -> pinned EKS topology
  -> evidence-backed RCA
```

### 7.3 Terraform role

Terraform may provision and destroy the disposable AWS/EKS environment:

```text
Terraform -> AWS -> EKS
```

That is an environment-management branch, not an initiating causal branch.
Do not invent:

```text
Image -> Terraform -> AWS -> EKS
```

merely because image build/deployment and environment provisioning occur in
the same repository or workflow.

### 7.4 Prohibited expansion

CLOUD-V1-1 must not introduce:

- new causal semantics or ranking;
- a new Truth Contract;
- Terraform causal attribution;
- a CloudTrail causal bridge;
- a Lambda runtime model;
- generic AWS-native incidents;
- Azure/GCP parity; or
- broad connector redesign.

If real EKS exposes a portability or reliability defect in already-supported
Kubernetes behavior, a minimal repair may be separately reviewed and preserved
as a regression. CLOUD-V1-1 implementation is not authorized by PH-0.

## 8. Current production-readiness baseline

The current accepted source still uses:

- SQLAlchemy with `TOPO_DATABASE_URL`;
- SQLite at `backend/data/topo.db` by default;
- `Base.metadata.create_all()` during FastAPI startup;
- 38 current ORM table declarations, including
  `build_artifact_evidence` added after the earlier 37-table post-15D audit;
- zero declared SQLAlchemy foreign keys;
- application-enforced string references across incidents, snapshots,
  analyses, signals, evidence, ownership, and control-plane records;
- many rich immutable/domain payloads serialized as JSON text; and
- no Alembic configuration, versions directory, or migration history.

Authentication currently has a tested bearer-token middleware but remains
disabled by default. Disabled authentication supplies a development
admin/operator principal. The browser API client sends no bearer token or
session credential. General incident, topology, agent, connector, and evidence
records have no tenant identity boundary. Roles primarily protect the dormant
approval/execution mutation surfaces rather than the complete customer API.

These facts support local development and controlled evaluation. They do not
support secure multi-customer production operation.

The earlier post-15D persistence inventory remains useful historical evidence,
but its 37-table count is no longer a complete current schema inventory. PH-1A
must inspect current source and accepted database state afresh rather than
copying that inventory or blindly autogenerating from metadata.

## 9. Production-hardening sequence

The primary engineering sequence is frozen as:

1. **PH-1 — Postgres + Alembic foundation**
2. **PH-2 — Authentication default-on**
3. **PH-3 — Tenant identity + tenant-scoped persistence**
4. **PH-4 — Secrets / credential / provider-access boundary**
5. **PH-5 — Minimum RBAC**
6. **PH-6 — Network + customer-data boundary**
7. **PH-7 — Retention + deletion**
8. **PH-8 — Backup + restore**
9. **PH-9 — Install / upgrade / rollback**
10. **PH-10 — Operational observability + concurrency + capacity**
11. **PH-11 — Onboarding + integration health + Incident Cockpit production polish**
12. **PH-12 — Controlled SRE / Platform Engineering design partner**

Blocks may later be split into smaller reviewable units, but this architectural
dependency order should remain. For example, tenancy must attach to a stable
production schema foundation, and a design partner must not connect customer
infrastructure before the minimum persistence/security/data gates exist.

## 10. PH-1 — Postgres and Alembic foundation

### 10.1 Why PH-1 is next

SQLite remains appropriate for controlled single-process use. It is no longer
the intended persistence boundary for:

- real customer data;
- multi-tenancy;
- multiple backend workers;
- concurrent agent/change/signal ingestion;
- production transaction and locking semantics;
- production backup and restore;
- high availability; or
- safely versioned schema upgrades and rollback.

PH-1 therefore establishes a portable production persistence path using:

```text
SQLAlchemy + Postgres + Alembic
```

It does not mean replacing SQLite everywhere immediately.

### 10.2 SQLite retained uses

SQLite remains supported where appropriate for:

- local developer workflows;
- deterministic offline evaluation;
- isolated byte-identical evaluation seeds/copies;
- unit and focused integration tests; and
- explicitly single-process fixtures and demonstrations.

### 10.3 Migration principles

The following principles are frozen before implementation:

1. Product models and repositories remain SQLAlchemy-portable.
2. Postgres-specific behavior is introduced only when required and isolated
   explicitly.
3. SQLite evaluation/developer compatibility is preserved.
4. Alembic becomes the authoritative production schema-evolution mechanism.
5. The complete accepted persistent schema is inventoried before the first
   migration is written.
6. The initial migration is not blindly autogenerated from current metadata;
   it must be reconciled with real accepted schema and data.
7. Upgrade and downgrade/rollback behavior is tested.
8. Existing historical incident truth remains semantically intact.
9. `CausalAnalysisRecord`, `GraphSnapshot`, signals, incidents, evidence,
   changes, build provenance, ownership/business impact, memory/history,
   outcomes, auth-related data, and dormant control-plane data are audited
   explicitly.
10. Broad cleanup, renaming, normalization, or referential redesign is not
    mixed into the first migration merely because an old schema name is
    inconvenient.

### 10.4 PH-1 entry criteria

PH-1 implementation begins only after this PH-0 decision is reviewed and
merged. Its first block must be architecture/inventory, not schema mutation.

The exact next block is:

```text
PH-1A — Production Persistence Inventory + Postgres/Alembic Migration Contract
```

PH-1A must inventory every current ORM model, table, column, index, unique
constraint, reference-shaped field, JSON payload, timestamp representation,
SQLite-specific assumption, repository transaction boundary, initialization
path, test fixture, evaluation seed dependency, and persistence entry point.
It must compare current metadata with accepted database reality and define the
initial migration/rollback contract before Alembic files are created.

## 11. Customer-data boundary

After causal correctness, the largest enterprise risk is customer-data
boundary plus production-persistence maturity.

Before a design partner connects real infrastructure, TopoAI must explicitly
answer:

- What data leaves the customer environment?
- Is source code or bounded source-mutation content ingested?
- Which before/after source values or hashes are persisted?
- Is Terraform state or plan content ever stored?
- Which AWS and Kubernetes metadata is retained?
- Are raw logs, payloads, environment variables, or secrets stored?
- Where are provider credentials, webhook secrets, API tokens, OAuth tokens,
  OIDC material, and short-lived cloud credentials held?
- How is tenant identity attached to every persisted record and request?
- Can one tenant ever read, correlate, mutate, export, or infer another
  tenant's entities, changes, incidents, evidence, history, or control state?
- Which roles may access incident and provider data?
- What are the retention, deletion, archival, and legal-hold semantics?
- How are backups encrypted, isolated, restored, and deletion-consistent?
- What happens to customer truth during upgrade, downgrade, and rollback?

These are product architecture requirements, not deployment documentation
details. PH-2 through PH-9 must make their answers enforceable and testable.

## 12. Terraform security boundary

TopoAI must not become a Terraform-state warehouse.

V1 must not persist raw:

- `terraform.tfstate` or backup state;
- Terraform plan binaries;
- complete `terraform show -json` output;
- provider/OIDC tokens;
- STS credentials;
- arbitrary CloudTrail request/response payloads; or
- raw unbounded application logs.

Current limited Terraform change/run ingestion may remain. It is not evidence
for an exact Terraform source -> AWS resource -> runtime causal claim.

If that family is later reopened, it must use bounded, typed, allowlisted proof
receipts with explicit schema versions, source references, completeness,
sensitive-data policy, and artifact hashes. Raw state and plans remain
ephemeral inputs, not durable product records.

## 13. AWS, EKS, other clouds, and on-prem direction

### 13.1 AWS and EKS

AWS remains the first cloud target. Existing AWS inventory/topology support is
preserved. EKS is the preferred real V1 cloud-hosted Kubernetes environment.

AWS V1 claims remain bounded:

- real EKS validation is required for the accepted Kubernetes causal family;
- partial AWS inventory support does not imply generic AWS causal support;
- generic AWS-native incident handling is deferred;
- Lambda causal lineage is deferred; and
- Lambda remains only the preferred future Terraform/AWS fixture if customer
  evidence later reopens the family.

### 13.2 Azure, GCP, and on-prem

Azure/GCP causal parity is deferred. Existing connectors are not removed only
because they are outside the first commercial optimization target.

Generic on-prem support is not a V1 promise. The provider-neutral Kubernetes
Truth Substrate may later support bare metal, VMware, OpenStack, or on-prem
Kubernetes when suitable collectors and evidence authorities exist. That
future possibility is not current support.

## 14. Product UX boundary

The product retains two primary user questions over the same truth substrate:

```text
Infrastructure Explorer:
What exists and how is it connected?

Incident Cockpit:
What happened, why, what is affected, and what should I do?
```

The Incident Cockpit remains the canonical incident-intelligence experience.
It consumes the unified briefing and lifecycle status, including controlled
pending/no-supported-hypothesis states, and must not independently recreate
RCA, ownership, history, response, or outcome truth.

Infrastructure Explorer remains a read-only view over persisted topology and
relationships. Display reconstruction must not upgrade inferred or partial
relationships into provider proof.

Production hardening must not become a major navigation or design-system
rewrite. Product polish should focus on:

- safe installation and onboarding;
- integration and collector health;
- evidence/trust drill-down;
- incident usability and pending/failure states;
- authenticated and tenant-aware access;
- operator diagnostics; and
- clear separation of live, advanced, dormant, and demo surfaces.

## 15. User-facing RCA language

Internal semantic levels remain unchanged:

| Internal semantic | Preferred V1 customer wording |
|---|---|
| `INITIATING_MUTATION` | Triggering change |
| `FAILURE_MECHANISM` | Failure mechanism |
| `RUNTIME_MANIFESTATION` | Runtime manifestation |
| `OPERATIONAL_IMPACT` | Impact |

The complete auditable chain is the **root-cause explanation**.

Do not change internal semantics merely to improve copy. Preserve TC-5:
heuristic ranking strength is not probability. When evidence is insufficient,
the customer experience should say that Topo has not identified a supported
root cause rather than inventing one.

## 16. Remediation and execution boundary

Read-only incident intelligence is the V1 product.

Allowed V1 behavior includes:

- prioritized investigation and mitigation guidance;
- cautious remediation previews;
- expected observations and verification checks;
- rollback/recovery considerations; and
- historical action evidence with raw counts and limitations.

Guidance remains conditional. It must not promise that a rollback or other
mutation will fix an incident.

Blocks 14F, 14G, and 14H remain preserved as dormant future safety
foundations:

- 14F evaluates execution readiness and persists no independent table;
- 14G provides durable human approval state and append-preserving audit
  events; and
- 14H provides execution-intent and internal claim/release primitives.

They are not required by incident creation, RCA, briefing, or cockpit. There
is no infrastructure executor, public worker claim path, Kubernetes/Terraform/
cloud mutation worker, or automatic rollback engine. Do not activate an
autonomous-remediation pilot before substantial real evidence exists for
causal correctness, recommendation correctness, verification, rollback,
blast containment, approval safety, and transaction safety.

## 17. Design-partner boundary

The primary first design-partner persona is:

```text
SRE / Platform Engineer
```

Preferred environment:

```text
GitHub
GitHub Actions
AWS
EKS / Kubernetes
Terraform common/preferred but not required for every supported RCA claim
```

User discovery may begin earlier. A design partner must not connect real
infrastructure until the minimum production persistence, authentication,
tenant isolation, secret handling, RBAC, customer-data, retention, backup, and
upgrade/rollback gates are complete enough for the agreed deployment model.

## 18. Private beta and open-source position

TopoAI proceeds private-beta first. Do not open-source the complete product
before design-partner learning.

Possible later open-core candidates include:

- Topo Agent;
- integration/collector SDK;
- CLI;
- Helm chart;
- local demo environment; and
- selected schemas/protocols.

Keep proprietary initially:

- causal reasoning engine;
- evaluation corpus and harness;
- truth-policy implementation;
- hosted control plane;
- multi-tenant/security implementation; and
- enterprise incident intelligence.

This is a reversible staging decision, not an irreversible commercial model.

## 19. Product positioning

Preferred positioning:

> **Evidence-backed incident intelligence with auditable causal RCA.**

Supporting message:

> Topo shows what changed, how it reached the failing system, what is affected,
> and why it believes the conclusion. When the evidence is insufficient, it
> says so.

Avoid claims such as:

- always finds root cause;
- universal RCA;
- calibrated causal probability;
- all-cloud support; or
- all-Kubernetes support.

## 20. Evaluation after the transition

Evaluation remains mandatory regression protection. Continue:

- accepted LINEAGE regression suites;
- TC-1 through TC-5 regression suites;
- blast-radius precision/recall tests;
- distractor tests;
- broken-boundary tests; and
- EAI-1 for every new finalized evaluation family where applicable.

Do not treat each connector or environment as justification for another
multi-block causal-research program. A broader statistical program should wait
until Topo has:

- several real incident families;
- at least one real cloud-hosted operational environment;
- positive causal cases;
- safe-abstention cases;
- realistic noise/distractor cases; and
- design-partner feedback.

CLOUD-V1-1 is portability/operational validation of the accepted causal path,
not expansion of causal semantics.

## 21. Governing stop rule

If a pre-design-partner task begins requiring any of the following, stop:

- a new global Truth Contract;
- generic cloud causal architecture;
- an event-store or graph-database rewrite;
- a large causal-ranking redesign;
- broad Terraform semantic analysis;
- Azure/GCP causal parity;
- autonomous remediation; or
- probability calibration.

Ask:

> Does this directly improve the safety or usability of the first supported
> SRE/Platform design-partner environment?

If the answer is no, defer the work. If the answer may be yes but materially
expands product authority, create a separate architecture decision and require
customer evidence before implementation.

## 22. Decision summary

| Decision area | Frozen V1 decision |
|---|---|
| Broad causal expansion | Closed |
| Strongest causal proof | GitHub -> Actions/BuildKit -> immutable image -> Kubernetes runtime incident |
| LINEAGE-3A0 | Blocked before measurement; Terraform/AWS causal family deferred |
| First commercial direction | GitHub + GitHub Actions + AWS + EKS/Kubernetes + TopoAI |
| Terraform | Environment provisioning and limited change/run ingestion; no V1 Terraform-to-AWS causal claim |
| AWS | First cloud target; real EKS validation required; generic AWS-native causal incidents deferred |
| EKS | Preferred real V1 Kubernetes environment |
| CLOUD-V1-1 | Bounded portability/golden validation of existing causal semantics |
| Primary program | Production hardening PH-1 through PH-12 |
| Next implementation program | Postgres + Alembic foundation, beginning with architecture inventory |
| SQLite | Retained for development, tests, fixtures, and deterministic evaluation |
| Customer data | Top architecture risk with production persistence maturity |
| Terraform data | Never a raw state/plan warehouse |
| UX | Preserve Explorer/Cockpit questions; polish, do not rewrite navigation |
| RCA terminology | Triggering change, failure mechanism, runtime manifestation, impact |
| Remediation | Read-only guidance; 14F/G/H dormant; no executor |
| Design partner | SRE / Platform Engineer in GitHub/Actions/AWS/EKS environment |
| Release posture | Private beta first; open-core options evaluated later |
| Positioning | Evidence-backed incident intelligence with auditable causal RCA |
| Evaluation | Permanent regression gate, no automatic new research family |

## 23. Exact next block and transition state

After architect review and merge of PH-0, proceed to exactly:

```text
PH-1A — Production Persistence Inventory + Postgres/Alembic Migration Contract
```

PH-1A is architecture and inventory before database modification. It must not
jump directly to autogenerated Alembic migrations.

Proposed next action for this checkpoint:

```text
ARCHITECT REVIEW / MERGE PH-0
```

No CLOUD-V1-1 implementation, LINEAGE-3A1, migration, Postgres installation,
AWS/EKS provisioning, Terraform execution, product repair, staging, commit, or
push is authorized by this document.
