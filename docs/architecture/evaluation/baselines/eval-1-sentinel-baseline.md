# EVAL-1 Sentinel baseline

Date: 2026-08-23  
Topo commit under test: `36dd62e1a12010591b90f44ff9d7c8c60e821e9b`  
Environment: Docker Desktop Kubernetes `v1.34.3`, context `docker-desktop`  
Harness: `eval-1.v1`

This is an engineering baseline, not marketing. All four scenarios established
provider-native truth and all four exposed product failures. No product repair
was made during EVAL-1.

## Sentinel A — obvious bad image

- Run: `da16e65f`
- Intent: mutate `sentinel-a-app` from `nginx:1.27-alpine` to the receipted
  nonexistent image `registry.invalid/topo-eval/sentinel-a:da16e65f`.
- Provider truth: Deployment UID
  `6f4e4bf2-ee3f-4cdf-a194-2f71be8e5950` owned ReplicaSet UID
  `b46bbcb8-af49-4ccd-9806-d4197f6c48ed`, which owned failing Pod UID
  `595b4b81-09ff-456a-bc44-9bc6f6bf136b`; Pod reason was `ErrImagePull`.
  The Service retained one ready provider endpoint and was explicitly
  unaffected.
- Topo incident:
  `incident:docker-desktop:topo-eval-a-da16e65f:workload-sentinel-a-app:217471d20584a6234105a22c`.
- Pinned snapshot: `snapshot:agent:e90b4c4be153028e3d2881443291c4fc`.
- Affected entity:
  `k8s:docker-desktop:pod:595b4b81-09ff-456a-bc44-9bc6f6bf136b` — correct.
- Analysis: `causal-analysis:cec26b204be39ec240739797b41c4725`.
- Top-1: `selects relationship added`, score 83.5,
  `supported_under_current_model`.
- Top-3: `selects relationship added`, `routes_to relationship added`,
  `owns relationship added`. The real Deployment image/configuration mutation
  was absent.
- Required owner path: 2/2 required hops found; ledger-backed edge precision
  0.75.
- Evidence: explicit non-cause support 0; unsupported critical claims under the
  bounded EVAL-1 definition 0; TC-5 probability-null invariant passed.
- Blast: TP 3, FP 1 (the still-serving Service), FN 0; precision 0.75, recall 1.0.
- Latency from receipted causal action: incident 4.499 s; persisted RCA 3.418 s;
  useful briefing 4.694 s. Briefing HTTP 200.
- **FAIL:** the obvious source mutation was neither Top-1 nor Top-3, and blast
  included a provider-proven still-serving Service.

## Sentinel B — attractive nearby non-cause

- Run: `214925d1`.
- Distractor truth: healthy `distractor-app` Deployment UID
  `58f185fc-8181-43b2-b0d1-54671a3e0f76` changed from
  `nginx:1.27-alpine` to `nginx:1.26-alpine` at
  `2026-08-23T11:13:22.659389Z`; it retained one available replica and its
  Service retained one ready endpoint.
- Victim truth: `victim-app` Deployment UID
  `55067f5c-d10b-49cf-a980-a80570891d70` received the independent bad image at
  `2026-08-23T11:13:23.360996Z`. It owned ReplicaSet UID
  `9fa17f75-06d7-49a3-9c7d-03212da6702e`, which owned failing Pod UID
  `5196fde8-8577-4533-a218-c134e45b74f2`; reason `ErrImagePull`.
- Incident:
  `incident:docker-desktop:topo-eval-b-214925d1:workload-victim-app:710cb28d906e1bed78092c3d`.
- Pinned snapshot: `snapshot:agent:1d69296222a5c8319eff32acfd72e878`.
- Affected entity:
  `k8s:docker-desktop:pod:5196fde8-8577-4533-a218-c134e45b74f2` — correct.
- Analysis: `causal-analysis:2077d990311b60ed0e4b4486d59af092`.
- Top-1: `selects relationship added`, score 83.5. Top-3 added
  `routes_to` and `owns`; the real victim Deployment mutation was absent.
- Distractor result: it did not become Top-1 and received zero supporting
  critical claims, so the deliberate non-cause check passed. The test still
  failed because a different class of derived topology noise displaced truth.
- Required path: 2/2; edge precision 0.75.
- Blast: TP 3, FP 3 (still-serving victim Service, healthy distractor
  Deployment, healthy distractor Service), FN 0; precision 0.50, recall 1.0.
- Latency: incident 5.085 s; persisted RCA 3.773 s; useful briefing 5.250 s.
  Briefing HTTP 200.
- **FAIL:** actual victim cause absent Top-3; three provider-proven unaffected
  logical objects included in blast.

## Sentinel C — topology-diff ranking noise

- Run: `f1a448e9`.
- Source mutation: Deployment UID
  `7116ba39-00ed-465c-a125-11af0c4c9ba5`, image
  `nginx:1.27-alpine` → `registry.invalid/topo-eval/sentinel-c:f1a448e9` at
  `2026-08-23T11:13:58.407846Z`.
- Provider chain: Deployment → ReplicaSet UID
  `c7a1bbd5-e50b-41b2-84cc-9c55e8512de8` → failing Pod UID
  `83bb46ea-ac15-4822-953a-617ad7cc450a`; `ErrImagePull`. The Service retained
  one ready endpoint.
- Incident:
  `incident:docker-desktop:topo-eval-c-f1a448e9:workload-sentinel-c-app:b27ea6420aeba67aaad4b32e`.
- Pinned snapshot: `snapshot:agent:10e02d82c55b5f5d0638dfeb3683ed7d`.
- Affected entity:
  `k8s:docker-desktop:pod:83bb46ea-ac15-4822-953a-617ad7cc450a` — correct.
- Analysis: `causal-analysis:704bae11f693c88b2aeb271a650ba0b9`.
- Source event: `Deployment configuration changed`, event
  `change-event:9830297d54cfaf8152f2fed323828a88`, occurred
  `2026-08-23T11:14:02.336869Z`; incident-change score 55.2, candidate rank 11,
  durable event risk score 80, excluded from the five hypotheses.
- Derived event: `selects relationship added`, event
  `change-event:b9d7d0778b75afcd871ca9a7e0626b4e`, same checkpoint time;
  incident-change score 87.5/rank 1 and 13C score 83.5/hypothesis rank 1,
  evidence state `supported_under_current_model`.
- Other derived events: `routes_to relationship added` scored 87.5/rank 2
  (13C 83.5/rank 2); an `owns relationship added` scored 84.8/rank 3
  (13C 80.42/rank 3).
- Required path: 2/2; edge precision 0.75. TC-5 invariant passed.
- Blast: TP 3, FP 1, FN 0; precision 0.75, recall 1.0.
- Latency: incident 4.254 s; persisted RCA 4.153 s; useful briefing 4.406 s.
  Briefing HTTP 200.
- `KNOWN_FAILURE_REPRODUCED = true`.
- **FAIL:** derived topology consequences outranked the independently receipted
  source mutation; truth was not in Top-3.

## Sentinel D — blast-radius overreach

- Run: `c1c01ade`.
- Provider affected set: failing victim Pod UID
  `c650a7c4-66a9-4109-a38a-11cc9a3e5059`, owner ReplicaSet UID
  `1b40efa1-69a5-4afe-ae87-eeff4c58ed60`, and victim Deployment UID
  `c329347a-22a1-4ccf-8968-00c34704c7d3`.
- Provider unaffected set: still-serving victim Service UID
  `d2434d16-d1da-4e30-9058-4c98610d68d0`, healthy independent Deployment UID
  `f1c41e99-85ac-44c1-8ea7-89583d8e8c1b`, and its Service UID
  `d1179dac-2a7f-4066-aec9-9b7a419a7908`. Each Service had one ready endpoint;
  the independent Deployment had one available replica.
- Incident:
  `incident:docker-desktop:topo-eval-d-c1c01ade:workload-victim-app:7341182d9221f96c25d18633`.
- Pinned snapshot: `snapshot:agent:850c9c9b2e431a86f8cbff72ede6f3e1`.
- Affected entity:
  `k8s:docker-desktop:pod:c650a7c4-66a9-4109-a38a-11cc9a3e5059` — correct.
- Analysis: `causal-analysis:b403a0d15c06718196552933825f28d1`;
  briefing HTTP 200.
- Top-1/Top-3: the same `selects`, `routes_to`, `owns` topology-diff sequence;
  the actual Deployment mutation was absent.
- Topo blast included all three explicitly unaffected objects. The direct
  still-serving Service was reached by the undirected `selects` edge. The
  independent Deployment and Service were reached through reverse/forward
  namespace `contains` traversal (`victim Pod ← namespace → independent
  object`).
- TP 3, FP 3, FN 0; precision 0.50, recall 1.0.
- Required path: 2/2; edge precision 0.75.
- Latency: incident 4.451 s; persisted RCA 2.932 s; useful briefing 4.553 s.
- **FAIL:** blast overreach is measured and attributable to undirected,
  all-predicate structural traversal; source cause also absent Top-3.

## Tiny-sample summary — NOT STATISTICALLY MEANINGFUL

- 4 real scenarios; 4 provider truth chains established; 4 incidents correctly
  correlated; 4 affected provider identities correct; 4 pinned snapshots and
  durable analyses; 4 briefings returned HTTP 200.
- Top-1 correct: 0/4. Top-3 contains truth: 0/4.
- Required owner path complete: 4/4. TC-5 probability-null invariant: 4/4.
- Explicit deliberate non-causes receiving supporting critical evidence: 0.
- Unsupported critical claims under the bounded manifest-conflict rule: 0.
- False certainty: 0 under the deliberately narrow EVAL-1 definition (none of
  these four manifests required abstention).
- Blast precision/recall by run: A 0.75/1.00; B 0.50/1.00; C 0.75/1.00;
  D 0.50/1.00.
- Product status: A FAIL, B FAIL, C FAIL, D FAIL.

These counts do not support an accuracy percentage or any statistical product
claim. They establish reproducible architecture findings for review.
