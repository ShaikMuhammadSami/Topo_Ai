# Causal ground truth v1

`eval-causal-ground-truth-v1` keeps four independent semantic levels for the
future LINEAGE-1 experiment. It is evaluation truth, not product reasoning.

## 1. Initiating mutation

Git/provider truth must prove that the single source file
`runtime-mode.txt` changed from canonical `healthy` bytes to canonical `fail`
bytes in the future failure commit.

## 2. Failure mechanism

The built image's fixed entrypoint reads that source-controlled file. `fail`
causes the process to exit with code `42`. No Deployment command, environment,
ConfigMap, Secret, invalid image, network dependency, or cluster-side mutation
creates the failure.

## 3. Runtime manifestation

Kubernetes provider truth must use structured status rather than one brittle
display string. The bounded accepted evidence requires:

- last container termination exit code `42`;
- restart count of at least `1`;
- waiting reason `BackOff` or `CrashLoopBackOff`, with termination reason
  `Error` accepted where Kubernetes reports it.

LINEAGE-1C may additionally retain the corresponding provider Event. These
fields describe the runtime manifestation; they are not the initiating cause.

## 4. Operational impact

The disposable Deployment requests one replica. Expected provider status is:

- desired replicas: `1`;
- ready replicas: `0`;
- available replicas: `0`.

This impact state is distinct from both the source change and the container
exit mechanism.

## Evidence boundary

Expected truth comes from Git/provider objects and Kubernetes structured
runtime status. Topo is the system under test. Topo cannot define the expected
mutation, exit code, restart evidence, or replica impact.

The contract intentionally makes no confidence or causal-probability claim.
It supports deterministic equality and threshold checks only—no fuzzy matching,
LLM, embeddings, or time-proximity substitution.

