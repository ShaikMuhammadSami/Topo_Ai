# TC-3 — Temporal semantics

Status: implemented on `architecture/truth-contract-temporal-semantics`.

TC-3 is an additive interpretation contract for the existing snapshot,
signal, change, incident, and causal-analysis stores. It is not event
sourcing, a temporal database, or a replacement for immutable topology
snapshots.

## Contract

Every new RCA-relevant fact may carry `TemporalMetadata` (`tc3.v1`):

| Concept | Field | Meaning |
|---|---|---|
| Effective time | `effective_at` | The timestamp selected by TC-3 for causal ordering. Its origin and quality must be read with it. |
| Source/valid time | `source_event_at` | An aware provider/runtime timestamp for when the customer-system event occurred. It is authoritative only when `source_time_authoritative=true`. |
| Observation time | `observed_at` | When Topo or its authenticated agent/collector observed or received the fact. |
| System time | `recorded_at` | When the backend first durably recorded the fact. |
| Validity interval | `valid_from`, `valid_to` | Optional interval only when a producer can defend it. TC-3 does not infer intervals from snapshot observation time. |

`occurred_at`, `first_observed_at`, `collected_at`, and `detected_at` remain
for API and storage compatibility. New detailed payloads add `temporal` to
make their interpretation explicit.

## Origin and quality

Origins are `source_reported`, `runtime_observed`, `topo_observed`,
`derived`, `ingestion_fallback`, and `legacy_unknown`. Qualities are
`exact`, `bounded`, `fallback`, and `unknown`; these are deterministic labels,
not numeric confidence scores.

An aware timestamp received through an already authenticated provider or
agent path may be source-authoritative. An arbitrary timestamp submitted to
the general Change Events API is preserved as an untrusted source claim, but
its backend observation time becomes `effective_at` with
`ingestion_fallback/fallback`. A missing, malformed, or timezone-less source
time follows the same fallback rule. TC-3 never silently interprets an
unknown local timezone as authoritative UTC.

## Incident boundary

The operational boundary is the primary failure signal's TC-3
`effective_at`. For a Kubernetes/runtime signal this is the earliest
defensible source/runtime observation. If the primary signal is legacy, the
existing incident `first_observed_at` is retained and interpreted
conservatively as legacy UTC when timezone-less. Backend incident
`created_at` is system knowledge time, not the customer failure boundary.

Late evidence does not modify `IncidentRecord.first_observed_at`, the
incident ID, or its pinned `topology_snapshot_id`.

## Snapshot time and selection

`GraphSnapshot.collected_at` is the inventory observation/completion time.
`SnapshotRecord.created_at` and `GraphSnapshot.temporal.recorded_at` are
backend persistence time. Snapshot, entity, relationship, and evidence
temporal metadata describe observations; `observed_at` is not promoted to an
exact `valid_from`.

Incident/RCA selection order is:

1. the explicit immutable incident-boundary snapshot;
2. otherwise, a cluster/namespace-compatible snapshot whose parsed UTC
   `collected_at` is at or before the operational incident boundary;
3. no snapshot when neither is available.

There is no arbitrary latest or later-topology fallback. Exact incident
boundary signal associations from 15D retain priority. ISO timestamps are
parsed as datetimes before comparison so offsets cannot reorder history.

## Causal ordering and late evidence

13C candidate windows, distance, and event-chain ordering use TC-3
`effective_at`: trusted source time first, otherwise the explicitly labeled
observation/ingestion fallback. All non-temporal candidate and RCA weights,
graph distance, priors, and `13c-causal-v1` remain unchanged.

Thus an event that happened at 10:01, an incident at 10:03, and an
authenticated delivery at 10:08 remains pre-incident evidence. The event's
`observed_at`/`recorded_at` also show that Topo did not know it at 10:04. An
event whose authoritative effective time is 10:05 remains post-incident even
if transport metadata was queued earlier.

Persisted causal analyses are immutable records under the current design.
Late evidence becomes available to the next explicit/idempotent analysis
generation; TC-3 does not mutate an already persisted analysis or introduce
analysis revisions automatically.

## Relationship and entity semantics

Snapshot entity/relationship `observed_at` means seen during collection.
For declared or owner-reference edges it does not establish when the edge
became valid. Runtime/eBPF observations use `runtime_observed`, because the
sensor event is the strongest available validity evidence. TC-3 does not add
entity first-seen/last-seen history and does not confuse resource creation
metadata with Topo observation.

Temporal fields are representation-only in snapshot digests and diffs. They
do not change canonical entity IDs, relationship IDs, snapshot material
state, normalized-change fingerprints, incident fingerprints, or stable
source-event dedupe keys.

## Source-specific rules

| Source | Source time after TC-3 | Observation/system separation | Gap/fallback |
|---|---|---|---|
| Kubernetes events/failures | RFC3339 event/first/last timestamps | Agent poll or backend collection; backend record time | Missing/naive source time falls back to collection; agent Kubernetes changes without a timestamp are skipped as before. |
| GitHub | `head_commit.timestamp`; deployment/status `updated_at` | Verified delivery receipt; DB creation | Missing source field is labeled fallback. |
| GitHub Actions | run/job `updated_at`, then `started_at` | Verified delivery receipt; DB creation | Missing source field is labeled fallback. |
| GitLab | final push commit timestamp; pipeline finish/create; deployment update/status-change when present | Verified delivery receipt; DB creation | Some deployment payloads expose no source time and remain fallback. |
| Jenkins | authenticated payload `occurred_at` | Backend receipt; DB creation | Missing or naive source time is fallback. |
| Azure DevOps | resource date/finish/start, then provider `createdDate` | Verified delivery receipt; DB creation | Missing provider time is fallback. |
| Terraform Cloud | run update, then run creation | Verified delivery receipt; DB creation | Verification requests have no change event; missing run time is fallback. |
| AWS CloudTrail | `EventTime` | Authenticated agent poll; DB creation | Missing time uses labeled poll/ingestion fallback. |
| Azure Activity Log | `eventTimestamp` | Authenticated agent poll; DB creation | Missing time uses labeled poll/ingestion fallback. |
| GCP Audit Logs | entry `timestamp` | Authenticated agent poll; DB creation | Missing time uses labeled poll/ingestion fallback. |
| Runtime/eBPF | dependency/process `first_seen_at`/`last_seen_at` sensor observations | Backend record creation/update | Sensor clock is assumed aware UTC; naive values are non-authoritative fallback. |

## Before-state conflicts repaired

| Field/path | Previous actual meaning/conflict | TC-3 behavior |
|---|---|---|
| `ChangeEventRecord.occurred_at` | Provider time or normalizer/backend `now`, indistinguishable | Canonical effective time; full source/observed/recorded interpretation is in metadata. |
| External normalizer `_now()` | Looked like exact customer event time | Explicit `ingestion_fallback/fallback`. |
| `ChangeEventRecord.received_at` | Backend ingestion only | Preserved as backend observation/receipt and mirrored in temporal metadata. |
| `NormalizedChange.detected_at` | After-snapshot collection time | Explicit derived, bounded observation. |
| `GraphSnapshot.collected_at` | Collection/completion; sometimes treated as generic snapshot time | Explicit topology observation, separate from DB `created_at`. |
| Entity/relationship `observed_at` | Collection time with no validity distinction | Explicit observed time; no invented validity interval. |
| Signal `first_observed_at` | Kubernetes source event or collection fallback, unlabeled | Source/runtime effective time or labeled observation fallback. |
| Incident change snapshot fallback | Newest snapshot, possibly after incident | Safe at-or-before, scope-compatible selection only. |
| Change-event correlation fallback | Current/latest topology | Effective-time, at-or-before, scope-compatible topology only. |
| ISO string ordering | Offset-sensitive lexicographic comparisons | Parsed timezone-aware UTC comparisons on truth paths. |

## Legacy behavior

Historical JSON without `temporal` continues to deserialize. Detailed change
event views synthesize an in-memory `legacy_unspecified` interpretation from
the old `occurred_at` only; they do not claim it is `source_event_at` and do
not rewrite stored payloads. Legacy snapshots/signals retain `temporal=null`.
Timezone-less legacy database values are interpreted deterministically as UTC
only for compatibility and remain `legacy_unknown/unknown`.

## Timezone and clock skew

New authoritative comparison times must be timezone-aware and are normalized
to UTC. Provider and agent clocks are assumed to be reasonably synchronized;
TC-3 does not shift timestamps or add a hidden skew allowance. Existing causal
windows are applied to the normalized effective time. Clock skew remains an
evaluation concern and is visible through source/observed/recorded deltas.

## Known limitations

- TC-3 does not add a historical "what Topo knew at time T" API, although
  recorded time is retained for one.
- Existing persisted RCA is not automatically revised after late evidence.
- Some GitLab deployment and generic CI payloads lack provider source time.
- Snapshot collection has one completion timestamp, not separate start/end.
- No validity intervals are asserted for snapshot-derived owner/configuration
  relationships because the source does not expose their exact start/end.
- Source authentication is unchanged; TC-3 relies on existing agent tokens
  and configured webhook verification. The general Change Events API remains
  an untrusted timestamp boundary.
