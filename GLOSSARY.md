# Topo AI

Topo AI links infrastructure topology, changes and operational signals to explain incidents with traceable evidence. This glossary fixes the words the README, UI and CLI use for those concepts.

## Workspace and data

**Tenant**:
An isolated set of Topo data (topology, changes, signals, incidents) that a user selects before working, such as "Topo AI Local Demo".
_Avoid_: Workspace, account, organization

**Snapshot**:
An immutable record of the infrastructure topology (entities and their relationships) as observed at one point in time.
_Avoid_: Scan, inventory, state

**Observer agent**:
The program installed next to infrastructure that collects snapshots and changes and sends them to Topo.
_Avoid_: Collector, sensor (when referring to the whole agent)

## Investigation

**Change**:
A recorded difference to an entity between two points in time, such as a Deployment's image moving from `v1` to `v2`.
_Avoid_: Event, diff, deploy (when meaning the recorded change)

**Signal**:
An observation that something is failing or degraded, such as a Pod entering CrashLoopBackOff.
_Avoid_: Alert, alarm

**Incident**:
A grouped, tracked occurrence of one or more related signals that is investigated and resolved as a unit.
_Avoid_: Alert, issue, outage

**Incident workspace**:
The page in the web app where a single incident is investigated.
_Avoid_: Workspace (alone), cockpit, dashboard

**Causal hypothesis**:
A candidate explanation that a specific change caused an incident, backed by supporting, contradicting and missing evidence.
_Avoid_: Root cause, verdict, diagnosis

**Supported hypothesis**:
A causal hypothesis with supporting evidence, no contradicting evidence and no expected evidence missing under the current model. It is not a proven root cause.
_Avoid_: Confirmed cause, certain cause

**Evidence**:
A durable, citable record (change, signal, relationship or timestamp) that supports, contradicts or is missing for a hypothesis.
_Avoid_: Proof, facts

**Ranking strength**:
A heuristic score used only to order hypotheses; it is never a probability.
_Avoid_: Confidence percentage, likelihood, certainty

**Blast radius**:
The set of entities reachable from a changed or failing entity through the topology, and therefore potentially affected.
_Avoid_: Impact zone, scope
