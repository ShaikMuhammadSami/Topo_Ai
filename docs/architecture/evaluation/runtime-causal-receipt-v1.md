# Runtime Causal Receipt v1

Status: **LINEAGE-1C independent evaluation contract**

Version: `eval-runtime-causal-receipt-v1`

This receipt freezes provider-native Kubernetes truth before any Topo RCA is
read. Topo is the system under test and cannot supply any expected field.

## Validity gate

A valid receipt requires all of the following structured facts:

- the Pod specification references the exact immutable provider-built image;
- any available runtime `imageID` contains the same digest;
- Deployment, ReplicaSet, and Pod UIDs are present;
- the ReplicaSet controller owner UID equals the Deployment UID;
- the Pod controller owner UID equals the ReplicaSet UID;
- the last termination reason is `Error` and exit code is `42`;
- restart count is at least one;
- backoff is established from container waiting state or a Kubernetes event;
- Deployment desired/ready/available replicas are exactly `1/0/0`.

Failure of any gate makes the live experiment
`INCONCLUSIVE_GROUND_TRUTH`; Topo RCA is not graded.

## Observation source

`evaluation/runtime_causal_observer.py` reads Kubernetes JSON using `kubectl`.
It does not import Topo normalization, graph, candidate, relevance, RCA, or
evidence-ledger implementations. Logs are not authoritative proof. The
structured `lastState.terminated.exitCode` is.

The observer accepts only a digest-pinned image reference, renders only the
two accepted deployment placeholders, enforces a 120-second maximum, and
writes generated receipts beneath ignored evaluation results.

## Local-cluster and cleanup safety

Mutation is allowed only when the active context and cluster are
`docker-desktop`, the API host is loopback, and all node provider IDs identify
Docker Desktop kind nodes. Cleanup requires both the exact namespace
`topo-eval-lineage-causal-<run-id>` and label
`topo.ai/evaluation-run=<run-id>`.

## Boundaries

The receipt proves failure mechanism, runtime manifestation, operational
impact, immutable artifact identity, and Kubernetes ownership. It does not by
itself prove that Topo connected the source mutation to the failure.
