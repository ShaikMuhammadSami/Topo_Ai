# SC-1 Source File Mutation Identity Repair

## Checkpoint type

Product-repair checkpoint. This document records the intended repair boundary;
it is not a new LINEAGE measurement.

## Before SC-1

The durable GitHub source change retained:

- repository;
- ref;
- push-level before commit;
- push-level after commit;
- commit count.

The exact file-level initiating mutation was missing. Provider-authentic current
and previous paths, exact commit parent context, before/after blob identity,
exact content SHA-256, and bounded before/after scalar evidence did not survive
the normalized change persistence boundary.

The frozen pre-repair measurement remains:

`docs/architecture/evaluation/baselines/lineage-1-final-source-to-runtime-causal-baseline.md`

## After SC-1 target

An exact, provider-authentic, commit-scoped GitHub file mutation survives:

```text
signed webhook
  -> provider enrichment
  -> typed normalization
  -> ChangeEvent metadata persistence
  -> fresh-session repository read
  -> existing ChangeEvent serialization
```

The additive record preserves stable repository identity, child and parent
identity, exact provider paths, provider blob OIDs, exact byte SHA-256 when
bounded bytes are available, conservative scalar display evidence, provenance,
and explicit completeness/reasons.

No topology file nodes or relationships are created. Parent source-change
fingerprinting remains unchanged. The repair does not change causal time,
candidate admission, relevance, scoring, ranking, incident lifecycle, H3-R1, or
runtime evidence.

## Claim boundary

SC-1 does **not** claim LINEAGE-1 causal proof. It repairs only the previously
measured first divergence: durable source-change identity. The preserved
LINEAGE-1 scenario must be rerun after this repair is reviewed and merged to
measure the next first divergence. No evaluator or frozen result is changed by
this checkpoint.
