# TC-5 confidence semantics and calibration boundaries

Status: implemented additive interpretation contract `tc5.v1`.

Scope: formal interpretation of the existing Block 13C causal ranking and a
repository-wide taxonomy for other active score/confidence fields. TC-5 does
not alter candidate generation, graph traversal, ranking weights, ordering,
threshold behavior, the TC-4 evidence ledger, or any probability model.

## Governing rule

TopoAI never presents mathematical precision it has not earned. A heuristic
is labeled heuristic. A ranking value orders hypotheses. Evidence support,
evidence completeness, TC-2 provenance, and TC-3 temporal quality stay
separate. No empirical calibration corpus exists, so calibrated causal
probability is unavailable.

## Before-state matrix

| Domain / field | Producer and exact rule | Range | Active consumers | Actual semantics before TC-5 | Probability / calibration | Previous presentation risk |
|---|---|---:|---|---|---|---|
| `CausalHypothesis.score` | `causal_rca.py`; 40% 13A candidate + topology ×25 + temporal ×15 + kind prior ×10 + lineage ×10, clipped 0–100 | 0–100 | rank/order, API, briefing, CLI | deterministic relative ranking | no / none | often paired with a field named confidence |
| `CausalHypothesis.confidence` | `score / 100`, rounded to four decimals | 0–1 | 14B thresholds, 14E evidence band, 14F via 14E, API/UI | legacy normalized ranking value | no / none | cockpit displayed it as a percentage |
| `CausalHypothesis.confidence_level` | high ≥.75; medium ≥.50; otherwise low | categorical | API/UI and response language | heuristic ranking band | no / none | label implied general certainty |
| `CausalEdge.confidence` / chain hop | event-lineage and graph-edge construction rules | 0–1 | causal-chain display and strongest-lineage input | edge/link strength heuristic | no / none | generic `CONF` label in CLI |
| `CausalEvidenceItem.weight` | existing evidence/edge construction | 0–1 | evidence graph/presentation | contribution or source strength, depending on item | no / none | generic percentage formatter in briefing UI |
| TC-4 ledger stance/counts | `causal_evidence_ledger.py` from durable expected sources | non-negative counts | evidence audit and briefing | descriptive support/contradiction/missing | no / not applicable | not previously summarized beside score |
| `IncidentChangeCandidate.score` | 13A: temporal up to 40, entity 35/20, scope 4 each, risk ×.09, cap 100 | 0–100 | 13C candidate input | deterministic relevance rank | no / none | could be confused with final causal score |
| `ChangeEntityLinkRecord.confidence` | exact canonical/native/alias/fallback constants 1/.98/.97/.95; metadata match .75 | 0–1 | event/entity correlation | match-strategy score | no / none | field name alone is ambiguous |
| `Relationship.confidence` | TC-2 permits a labeled value only for inferred edges with a real heuristic; legacy edges may retain 1.0 | 0–1 or null | graph views, causal path | inferred-edge heuristic only | no / none | historical 1.0 could look like certainty |
| logical identity confidence | identity resolver constants by exact owner/selector/name method | 0–1 | identity API/UI | deterministic match score | no / none | UI displayed percentages |
| ownership confidence | exact entity 1.0; service .90 + .02/scope capped .99; kind/name .85; metadata .75; unresolved 0 | 0–1 | 14A/briefing/routing | match specificity | no / none | name suggested probability of owner correctness |
| `HistoricalIncidentMatch.similarity_score` | 14D weighted exact/Jaccard factors; missing factors contribute zero and are not renormalized | 0–1 | history selection/patterns/briefing | deterministic incident similarity | no / none | generic percent formatter implied likelihood |
| `HistoricalActionSupport.score` | 14E similarity × RCA-quality support minus conflict, divided by observations, capped by `min(n/3,1)` | 0–1 | response intelligence | bounded historical support index | no / none | must not be read as action success rate |
| `CurrentEvidenceStrength` | legacy causal threshold plus presence of evidence IDs | low/moderate/high | 14E and dormant 14F | policy band | no / none | inherits legacy causal threshold semantics |
| blast `impact_score` | fixed distance decay | 0–1 | blast/briefing | graph-distance impact heuristic | no / none | generic percentage formatter |
| outcome `rca_confidence` | responder override or deterministic verdict constants | 0–1 | 14C/history | outcome-verdict support marker | no / none | separate from live 13C ranking |
| legacy recommendation/recovery confidence | old analysis/recovery rules | 0–1 | Advanced/manual UI | legacy action/check heuristic | no / none | UI displayed percentages |
| generated AI confidence fields | Groq-generated or fallback self-scores in legacy explanation/copilot/plan/report paths | 0–1 | Advanced/manual UI only | non-authoritative generated self-score | no / none | UI called it confidence without qualification |
| predeployment risk / importance scores | deterministic rule weights | domain-specific | predeployment/change UI | risk/priority indices, not causal confidence | no / none | percentage-like display could imply probability |

The machine-readable inventory is
[confidence-semantics-contract.json](./confidence-semantics-contract.json).
Unrelated score families remain unrelated; TC-5 does not create a universal
confidence abstraction.

## Current 13C formula — unchanged

Algorithm version remains `13c-causal-v1`:

```text
ranking_score = min(100, max(0,
    incident_change_candidate_score * 0.40
  + topology_component * 25
  + temporal_component * 15
  + change_kind_prior * 10
  + strongest_incoming_lineage_component * 10
))

legacy confidence = ranking_score / 100
```

The implementation still rounds `ranking_score` to two decimals and legacy
`confidence` to four decimals. High remains `>= 0.75`, medium remains
`>= 0.50`, and low remains below `0.50`. Scores are clipped to the model's
existing range before normalization. No weight, ordering, cap, or threshold
changed in TC-5.

Alternative hypothesis scores are independent ranking values. They do not
sum to one and must never be normalized with softmax or interpreted as a
probability distribution.

## Authoritative TC-5 object

Every newly generated analysis exposes `CausalConfidenceSemantics` for each
hypothesis and one analysis-level object for the top hypothesis. Briefing
`root_cause.confidence_semantics` reuses that same object rather than
reconstructing meaning in the frontend.

The object contains:

- `score_type=heuristic_ranking`;
- the existing `ranking_score` on a 0–100 range;
- the existing low/medium/high threshold result as `ranking_strength`;
- the legacy normalized value and its explicit
  `legacy_normalized_heuristic_ranking_score` meaning;
- TC-4 supporting, contradicting, and missing counts;
- evidence completeness and evidence state;
- `calibration_status=not_calibrated`;
- `calibrated_probability=null`; and
- separate `tc5.v1` semantics and `13c-causal-v1` algorithm versions.

Old persisted causal payloads are not rewritten. Repository reads enrich them
in memory with `legacy_unknown` evidence state when their TC-4 ledger is
absent. TC-5 is included in the deterministic analysis input fingerprint, so
a new explicit analysis generation can persist the contract without mutating
an older generation.

## Ranking strength versus evidence state

`ranking_strength` is the old high/medium/low threshold interpreted honestly
as a heuristic ranking band. It is not a certainty band.

Evidence state comes only from the existing TC-4 ledger:

| Ledger state | TC-5 evidence state | Completeness |
|---|---|---|
| no contradiction and no expected evidence missing | `supported_under_current_model` | `complete_for_current_model` |
| contradiction, no missing item | `contested` | `complete_for_current_model` |
| expected evidence missing, no contradiction | `incomplete` | `partial` |
| contradiction and expected evidence missing | `contested_with_gaps` | `partial` |
| old hypothesis without a ledger | `legacy_unknown` | `unknown` |
| no ranked hypothesis | `insufficient_evidence` | `unknown` |

“Complete for current model” means that TC-4 emitted no defensibly expected
missing item. It does not claim that every possible telemetry source exists
or that the cause is correct. TC-5 deliberately adds no materiality score for
missing or contradicting evidence because TC-4 does not provide one.

Evidence counts are descriptive. They never feed the ranking formula,
probability, candidate ordering, response eligibility, or safety policy.

## Contradiction and missing evidence

A high heuristic rank can be `contested`. A high heuristic rank can also have
`partial` evidence completeness. TC-5 exposes these combinations directly and
does not subtract an arbitrary percentage. A contradiction does not create a
numeric penalty, and missing artifact/provenance evidence does not convert an
85 ranking into a fabricated 60% probability.

## Insufficient evidence

An analysis with no supported hypothesis returns an analysis-level semantics
object with no ranking score, no legacy confidence, `insufficient_evidence`,
`not_calibrated`, and null probability. It never emits 0%, 50%, or another
placeholder. Existing `completed_no_hypothesis` lifecycle behavior remains
unchanged.

## Provenance and temporal quality remain separate

TC-2 relationship origin (`observed`, `declared`, `derived`, `inferred`) and
provenance completeness remain typed relationship facts. TC-3 time origin and
quality remain typed temporal facts. Neither is collapsed into causal
confidence. TC-5 only summarizes TC-4 stance counts; callers can inspect the
ledger for the underlying TC-1/TC-2/TC-3 evidence.

## Other score families

- 14D similarity is weighted feature overlap, not causal probability.
- Ownership confidence is deterministic mapping specificity, not causal
  confidence and not owner correctness probability.
- TC-2 relationship confidence is an inferred-link heuristic only; observed,
  declared, and derived new edges omit numeric confidence.
- 14E historical support is a bounded evidence index with raw counts and
  small-sample caps, not remediation success probability.
- Blast impact, identity match, outcome verdict, risk, importance, and
  legacy/generated self-scores keep their domain-specific meaning.

## Response and dormant safety compatibility

14B still uses the legacy normalized heuristic threshold `0.75` for rollback
candidate eligibility and `0.50` for weak-evidence guidance. 14E still maps
the same value plus evidence IDs to current evidence strength. Dormant 14F
still consumes that 14E band. TC-5 changes labels and metadata only; it does
not loosen or tighten current response/safety behavior. These heuristic policy
dependencies require future empirical evaluation before production execution.

## LLM boundary

LLMs cannot produce or overwrite ranking score, ranking strength, evidence
state, calibration status, calibrated probability, or any other authoritative
TC-5 field. The optional briefing prompt receives the deterministic object and
is explicitly prohibited from generating numeric confidence/probability.
Legacy advanced AI surfaces expose their numeric fields as uncalibrated
generated self-scores, never as authoritative causal facts.

## API and display rules

- Preserve `score`, `confidence`, `confidence_level`, `causal_confidence`, and
  equivalent legacy copies for compatibility.
- New code reads the typed semantics object.
- Technical UI may show `83.5 / 100` as a heuristic ranking score, together
  with evidence state and “probability not calibrated.”
- Business UI uses the evidence state and heuristic band and explicitly says
  calibrated probability is unavailable.
- CLI prints heuristic ranking score, ranking band, evidence state,
  completeness, calibration status, and null probability. JSON remains the
  complete backend response.
- Similarity, ownership, relationship, impact, risk, and historical support
  use domain-specific “score”, “match”, or “support” wording, not causal
  probability wording.
- No uncalibrated causal value is formatted as “83.5% confidence.”

## Persistence and historical correctness

TC-5 adds no table. Semantics are derived from the already persisted causal
hypothesis and TC-4 ledger, embedded in new causal-analysis JSON, and carried
by derived briefing responses. Snapshot pinning and historical graph selection
are unchanged. The contract never queries latest topology.

## Future calibration requirements

TopoAI may expose calibrated probability only after all of the following are
real and versioned:

1. a sufficiently large labeled incident corpus with independently verified
   ground-truth root causes;
2. explicit inclusion/exclusion rules and representative source/scenario
   coverage;
3. strict train, calibration, and held-out evaluation separation;
4. score reliability analysis and calibration curves;
5. Brier score (or an equivalent proper scoring rule) and expected calibration
   error, reported with uncertainty;
6. per-source and per-scenario calibration analysis rather than one misleading
   global number;
7. minimum sample requirements for each published calibration claim;
8. versioned causal algorithm, dataset, calibration mapping, and evaluation
   procedure;
9. prospective monitoring for calibration drift and source-distribution
   changes; and
10. a policy for withholding probability when a scenario is out of calibration
    scope.

None of these calibration assets exists today. TC-5 implements no calibration,
sigmoid, logistic transform, softmax, training, or predictive model.

## Known limitations

- Ranking quality is not evaluated by TC-5; only its meaning is made honest.
- Existing 13C ranking can remain high with contradiction or missing evidence;
  TC-5 exposes rather than repairs that behavior.
- Older analyses without TC-4 ledgers have unknown evidence completeness.
- 14B/14E/14F still consume legacy heuristic bands for compatibility.
- Advanced legacy confidence/self-score fields remain separate contracts and
  are not retrofitted into the 13C semantics model.
- No empirical probability, reliability claim, or expected correctness rate
  is available.
