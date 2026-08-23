# TopoAI Truth Substrate v1

Status: **frozen for adversarial evaluation**.

The accepted contracts below collectively form TopoAI Truth Substrate v1:

- TC-1: canonical entity identity (`entity-identity.md` and contract JSON)
- TC-2: relationship provenance (`relationship-provenance.md` and contract JSON)
- TC-3: temporal semantics (`temporal-semantics.md` and contract JSON)
- TC-4: causal evidence ledger (`causal-evidence-ledger.md` and contract JSON)
- TC-5: confidence semantics (`confidence-semantics.md` and contract JSON)

EVAL-1 consumes these contracts as the system-under-test boundary. It does not
change, reinterpret, weaken, or special-case them to make a Sentinel pass.

## Permitted reasons to change the frozen substrate

A later architecture block may change a Truth Contract only with at least one
of the following explicit justifications:

- independent evaluation evidence demonstrates a reproducible correctness defect;
- a reproducible compatibility or security defect requires the change;
- the contract cannot represent required operational truth.

Any such change requires architect review, a separately scoped repair, and a
permanent regression scenario. Evaluation convenience and score improvement
alone are not valid reasons.

## Permanent regression rule

**EVERY TIME TOPO IS WRONG, PRESERVE THE SCENARIO FOREVER.**

The lifecycle is: real failure → reproducible evaluation scenario → reviewed
architecture repair → permanent regression protection. Disposable provider
artifacts are not committed; the smallest defensible manifest/fixture is.

