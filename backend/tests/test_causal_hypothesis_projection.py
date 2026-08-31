from __future__ import annotations
from domain_tenant_fixtures import seed_domain_parents
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant

import inspect
import itertools
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Base, CausalAnalysisRecord
from app.models.causal_projection import (
    CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION,
    CausalHypothesisProjectionSummary,
    DiagnosticProjectionReason,
    SupportedProjectionReason,
)
from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalConfidenceLevel,
    CausalHypothesis,
)
from app.models.causal_support import (
    CAUSAL_SUPPORT_GATE_POLICY_VERSION,
    CausalSupportGateAudit,
    CausalSupportGateState,
)
from app.models.confidence_semantics import (
    CausalEvidenceCompleteness,
    CausalEvidenceState,
)
from app.repositories.causal_analysis_repository import (
    load_causal_analysis,
    save_causal_analysis,
)
from app.services.causal_hypothesis_projection import (
    project_causal_hypotheses,
)
from app.services.causal_rca import _stable_id

ROOT = Path(__file__).resolve().parents[2]


def _gate(*, supported: bool) -> CausalSupportGateAudit:
    gate_state = (
        CausalSupportGateState.SATISFIED
        if supported
        else CausalSupportGateState.UNSATISFIED
    )
    return CausalSupportGateAudit(
        relevance_gate_state=gate_state,
        relevance_gate_reason=(
            "supported_semantic_path" if supported else "identity_unresolved"
        ),
        candidate_linkage_gate_state=gate_state,
        candidate_linkage_gate_reason=(
            "candidate_specific_linkage_supported"
            if supported
            else "candidate_specific_linkage_missing"
        ),
        support_state=(
            CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
            if supported
            else CausalEvidenceState.INSUFFICIENT_CANDIDATE_SPECIFIC_EVIDENCE
        ),
        support_reason=(
            "candidate_specific_causal_linkage_supported"
            if supported
            else "insufficient_candidate_specific_evidence"
        ),
        evidence_completeness=(
            CausalEvidenceCompleteness.COMPLETE_FOR_CURRENT_MODEL
            if supported
            else CausalEvidenceCompleteness.PARTIAL
        ),
    )


def _hypothesis(
    name: str,
    *,
    score: float,
    supported: bool,
) -> CausalHypothesis:
    return CausalHypothesis(
        hypothesis_id=f"hypothesis:{name}",
        rank=0,
        root_event_id=f"event:{name}",
        root_source="synthetic",
        root_title=f"Change {name}",
        target_event_id=f"event:{name}",
        target_title=f"Change {name}",
        affected_entity_id="entity:affected",
        score=score,
        confidence=0.5,
        confidence_level=CausalConfidenceLevel.MEDIUM,
        summary="Generic AR-3 projection fixture.",
        support_gate=_gate(supported=supported),
    )


def _count_fifty_shape() -> list[CausalHypothesis]:
    controls = [
        _hypothesis(
            f"control-{index}",
            score=99.0 - index,
            supported=False,
        )
        for index in range(5)
    ]
    return [*controls, _hypothesis("cause", score=10.0, supported=True)]


def _analysis() -> CausalAnalysisResponse:
    projection = project_causal_hypotheses(
        _count_fifty_shape(),
        diagnostic_limit=5,
        supported_limit=5,
    )
    hypotheses = list(projection.evaluated_hypotheses)
    by_id = {item.hypothesis_id: item for item in hypotheses}
    return CausalAnalysisResponse(
        analysis_id="causal-analysis:ar3",
        incident_id="incident:ar3",
        incident_title="AR-3 incident",
        incident_time="2026-08-26T12:00:00+00:00",
        topology_snapshot_id="snapshot:ar3",
        algorithm_version="13c-causal-v1",
        support_policy_version=CAUSAL_SUPPORT_GATE_POLICY_VERSION,
        projection_policy_version=CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION,
        diagnostic_hypothesis_ids=list(projection.diagnostic_hypothesis_ids),
        supported_hypothesis_ids=list(projection.supported_hypothesis_ids),
        hypothesis_projection_audit=list(projection.audit),
        hypothesis_projection_summary=projection.summary,
        generated_at="2026-08-26T12:01:00+00:00",
        parameters={"max_hypotheses": 5},
        candidate_count=51,
        node_count=0,
        edge_count=0,
        evidence_count=0,
        hypothesis_count=len(hypotheses),
        top_hypothesis=by_id[projection.diagnostic_hypothesis_ids[0]],
        hypotheses=hypotheses,
    )


def test_old_sort_cap_then_support_filter_reproduces_projection_loss() -> None:
    evaluated = sorted(_count_fifty_shape(), key=lambda item: item.score, reverse=True)
    old_final = evaluated[:5]
    old_supported = [
        item
        for item in old_final
        if item.support_gate.support_state
        == CausalEvidenceState.SUPPORTED_UNDER_CURRENT_MODEL
    ]

    assert [item.hypothesis_id for item in old_final] == [
        f"hypothesis:control-{index}" for index in range(5)
    ]
    assert old_supported == []


def test_count_fifty_shape_preserves_diagnostics_and_supported_cause() -> None:
    source = _count_fifty_shape()
    scores_before = {item.hypothesis_id: item.score for item in source}
    projection = project_causal_hypotheses(
        source,
        diagnostic_limit=5,
        supported_limit=5,
    )

    assert len(projection.evaluated_hypotheses) == 6
    assert list(projection.diagnostic_hypothesis_ids) == [
        f"hypothesis:control-{index}" for index in range(5)
    ]
    assert projection.supported_hypothesis_ids == ("hypothesis:cause",)
    assert projection.evaluated_hypotheses[0].hypothesis_id == (
        "hypothesis:control-0"
    )
    assert projection.evaluated_hypotheses[-1].rank == 6
    assert {
        item.hypothesis_id: item.score for item in projection.evaluated_hypotheses
    } == scores_before
    assert projection.summary.diagnostic_projection_limit == 5
    assert projection.summary.supported_projection_limit == 5
    assert projection.summary.projection_dropped_supported_count == 0

    cause_audit = next(
        item for item in projection.audit if item.hypothesis_id == "hypothesis:cause"
    )
    assert not cause_audit.diagnostic_projection_included
    assert cause_audit.diagnostic_projection_reason == (
        DiagnosticProjectionReason.DIAGNOSTIC_CAP_REACHED
    )
    assert cause_audit.supported_projection_included
    assert cause_audit.supported_projection_rank == 1
    assert cause_audit.supported_projection_reason == (
        SupportedProjectionReason.INCLUDED_AFTER_SUPPORT_QUALIFICATION
    )


def test_no_supported_hypothesis_preserves_diagnostics_and_abstains() -> None:
    hypotheses = [
        _hypothesis(f"unsupported-{index}", score=100 - index, supported=False)
        for index in range(6)
    ]
    projection = project_causal_hypotheses(
        hypotheses,
        diagnostic_limit=5,
        supported_limit=5,
    )

    assert len(projection.diagnostic_hypothesis_ids) == 5
    assert projection.supported_hypothesis_ids == ()
    assert projection.summary.support_qualified_hypothesis_count == 0
    assert projection.summary.projection_dropped_supported_count == 0
    assert all(
        item.supported_projection_reason
        == SupportedProjectionReason.SUPPORT_GATE_NOT_SATISFIED
        for item in projection.audit
    )


def test_supported_projection_filters_before_budgeting_and_keeps_causal_order() -> None:
    hypotheses = [
        _hypothesis("u1", score=100, supported=False),
        _hypothesis("u2", score=90, supported=False),
        _hypothesis("s1", score=80, supported=True),
        _hypothesis("u3", score=70, supported=False),
        _hypothesis("s2", score=60, supported=True),
    ]
    projection = project_causal_hypotheses(
        hypotheses,
        diagnostic_limit=5,
        supported_limit=5,
    )

    assert projection.supported_hypothesis_ids == (
        "hypothesis:s1",
        "hypothesis:s2",
    )
    ranks = {
        item.hypothesis_id: item.supported_projection_rank
        for item in projection.audit
    }
    assert ranks["hypothesis:s1"] == 1
    assert ranks["hypothesis:s2"] == 2
    assert ranks["hypothesis:u1"] is None


def test_supported_cap_overflow_is_distinct_from_unsupported_eviction() -> None:
    hypotheses = [
        _hypothesis("u1", score=100, supported=False),
        _hypothesis("s1", score=90, supported=True),
        _hypothesis("u2", score=80, supported=False),
        _hypothesis("s2", score=70, supported=True),
        _hypothesis("s3", score=60, supported=True),
    ]
    projection = project_causal_hypotheses(
        hypotheses,
        diagnostic_limit=2,
        supported_limit=2,
    )

    assert projection.supported_hypothesis_ids == (
        "hypothesis:s1",
        "hypothesis:s2",
    )
    excluded = next(
        item for item in projection.audit if item.hypothesis_id == "hypothesis:s3"
    )
    assert excluded.supported_projection_reason == (
        SupportedProjectionReason.SUPPORTED_CAP_REACHED
    )
    assert projection.summary.supported_projection_cap_excluded_count == 1
    assert projection.summary.projection_dropped_supported_count == 0


def test_projection_is_permutation_invariant_with_stable_id_tie_break() -> None:
    hypotheses = [
        _hypothesis("b", score=50, supported=True),
        _hypothesis("a", score=50, supported=True),
        _hypothesis("c", score=50, supported=False),
    ]
    results = {
        (
            projection.diagnostic_hypothesis_ids,
            projection.supported_hypothesis_ids,
            tuple(
                (item.hypothesis_id, item.rank)
                for item in projection.evaluated_hypotheses
            ),
        )
        for permutation in itertools.permutations(hypotheses)
        for projection in [
            project_causal_hypotheses(
                permutation,
                diagnostic_limit=2,
                supported_limit=2,
            )
        ]
    }

    assert results == {
        (
            ("hypothesis:a", "hypothesis:b"),
            ("hypothesis:a", "hypothesis:b"),
            (
                ("hypothesis:a", 1),
                ("hypothesis:b", 2),
                ("hypothesis:c", 3),
            ),
        )
    }


def test_supported_diagnostic_rank_twenty_is_retained_when_already_evaluated() -> None:
    hypotheses = [
        *[
            _hypothesis(f"u-{index:02d}", score=100 - index, supported=False)
            for index in range(19)
        ],
        _hypothesis("supported-20", score=1, supported=True),
    ]
    projection = project_causal_hypotheses(
        hypotheses,
        diagnostic_limit=19,
        supported_limit=19,
    )

    assert len(projection.evaluated_hypotheses) == 20
    assert "hypothesis:supported-20" not in projection.diagnostic_hypothesis_ids
    assert projection.supported_hypothesis_ids == ("hypothesis:supported-20",)


def test_projection_uses_only_supplied_evaluated_set_and_references_canonical_ids() -> None:
    hypotheses = _count_fifty_shape()
    projection = project_causal_hypotheses(
        hypotheses,
        diagnostic_limit=5,
        supported_limit=5,
    )
    canonical_ids = {item.hypothesis_id for item in projection.evaluated_hypotheses}

    assert set(projection.diagnostic_hypothesis_ids) <= canonical_ids
    assert set(projection.supported_hypothesis_ids) <= canonical_ids
    assert {item.hypothesis_id for item in projection.audit} == canonical_ids
    assert all(isinstance(item, str) for item in projection.supported_hypothesis_ids)
    assert "hypothesis:not-evaluated" not in canonical_ids


def test_duplicate_identity_and_unknown_policy_fail_closed() -> None:
    duplicate = _hypothesis("duplicate", score=10, supported=True)
    with pytest.raises(ValueError, match="must be unique"):
        project_causal_hypotheses(
            [duplicate, duplicate],
            diagnostic_limit=5,
            supported_limit=5,
        )
    with pytest.raises(ValueError, match="Unsupported causal hypothesis"):
        project_causal_hypotheses(
            [duplicate],
            diagnostic_limit=5,
            supported_limit=5,
            policy_version="pre-ar3",
        )


def test_projection_dropped_supported_invariant_is_model_enforced() -> None:
    with pytest.raises(ValueError, match="cannot be dropped"):
        CausalHypothesisProjectionSummary(
            diagnostic_projection_limit=5,
            supported_projection_limit=5,
            evaluated_hypothesis_count=1,
            diagnostic_projection_count=1,
            supported_projection_count=0,
            support_qualified_hypothesis_count=1,
            projection_dropped_supported_count=1,
            supported_projection_cap_excluded_count=0,
        )


def test_projection_metadata_and_supported_top1_survive_fresh_session_readback() -> (
    None
):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    seed_domain_parents(engine, ("incidents", "incident:ar3"))
    analysis = _analysis()
    seed_domain_parents(engine, ("topology_snapshots", analysis.topology_snapshot_id))
    with Session(engine) as session:
        save_causal_analysis(session, analysis=analysis, tenant_id=TEST_TENANT)
    with Session(engine) as fresh_session:
        loaded = load_causal_analysis(
            fresh_session, analysis_id=analysis.analysis_id, tenant_id=TEST_TENANT
        )

    assert loaded is not None
    assert loaded.projection_policy_version == (
        CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION
    )
    assert loaded.diagnostic_hypothesis_ids == analysis.diagnostic_hypothesis_ids
    assert loaded.supported_hypothesis_ids == ["hypothesis:cause"]
    assert loaded.hypothesis_projection_audit == analysis.hypothesis_projection_audit
    assert loaded.hypothesis_projection_summary == (
        analysis.hypothesis_projection_summary
    )
    assert loaded.top_hypothesis.hypothesis_id == "hypothesis:control-0"
    assert next(
        item
        for item in loaded.hypotheses
        if item.hypothesis_id == loaded.supported_hypothesis_ids[0]
    ).root_event_id == "event:cause"


def test_legacy_payload_loads_without_projection_reconstruction() -> None:
    payload = _analysis().model_dump(mode="json")
    payload.pop("projection_policy_version")
    payload.pop("diagnostic_hypothesis_ids")
    payload.pop("supported_hypothesis_ids")
    payload.pop("hypothesis_projection_audit")
    payload.pop("hypothesis_projection_summary")
    payload["analysis_id"] = "causal-analysis:legacy-pre-ar3"

    legacy = CausalAnalysisResponse.model_validate(payload)

    assert legacy.projection_policy_version is None
    assert legacy.diagnostic_hypothesis_ids == []
    assert legacy.supported_hypothesis_ids == []
    assert legacy.hypothesis_projection_audit == []
    assert legacy.hypothesis_projection_summary is None
    assert [item.hypothesis_id for item in legacy.hypotheses] == [
        item["hypothesis_id"] for item in payload["hypotheses"]
    ]

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    legacy_json = json.dumps(payload)
    with Session(engine) as session:
        session.add(
            CausalAnalysisRecord(
                analysis_id=payload["analysis_id"],
                incident_id=payload["incident_id"],
                generated_at=payload["generated_at"],
                algorithm_version=payload["algorithm_version"],
                candidate_count=payload["candidate_count"],
                hypothesis_count=payload["hypothesis_count"],
                top_hypothesis_score=payload["top_hypothesis"]["score"],
                top_root_event_id=payload["top_hypothesis"]["root_event_id"],
                payload_json=legacy_json,
                created_at=payload["generated_at"],
                updated_at=payload["generated_at"],
                tenant_id=TEST_TENANT,
            )
        )
        session.commit()
        loaded = load_causal_analysis(
            session, analysis_id=payload["analysis_id"], tenant_id=TEST_TENANT
        )
        stored_json = session.get(
            CausalAnalysisRecord,
            (TEST_TENANT, payload["analysis_id"]),
        ).payload_json

    assert loaded is not None
    assert loaded.projection_policy_version is None
    assert loaded.supported_hypothesis_ids == []
    assert stored_json == legacy_json


def test_projection_policy_is_material_to_analysis_fingerprint() -> None:
    current = {
        "incident_id": "incident:ar3",
        "causal_hypothesis_projection": (
            CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION
        ),
    }
    legacy = {
        "incident_id": "incident:ar3",
        "causal_hypothesis_projection": "pre-ar3-projection-semantics",
    }

    assert _stable_id("causal-analysis", json.dumps(current, sort_keys=True)) != (
        _stable_id("causal-analysis", json.dumps(legacy, sort_keys=True))
    )
    source = (ROOT / "backend/app/services/causal_rca.py").read_text(
        encoding="utf-8"
    )
    assert '"causal_hypothesis_projection":' in source
    assert "CAUSAL_HYPOTHESIS_PROJECTION_POLICY_VERSION" in source


def test_projection_service_has_no_external_or_fixture_specific_dependency() -> None:
    source = inspect.getsource(
        __import__(
            "app.services.causal_hypothesis_projection",
            fromlist=["project_causal_hypotheses"],
        )
    ).casefold()
    forbidden = (
        "openai",
        "embedding",
        "github",
        "kubernetes",
        "provider",
        "fuzzy",
        "noncausal_control",
        "32695735269",
        "4149b194c4c4fdfd",
        "a7616346acbcde6b",
        "runtime-mode.txt",
    )
    assert all(value not in source for value in forbidden)
