from types import SimpleNamespace

import topo_cli.commands.causal_rca as causal_rca
from topo_cli.output import OutputFormat


def _payload() -> dict:
    semantics = {
        "semantics_version": "tc5.v1",
        "ranking_algorithm_version": "13c-causal-v1",
        "score_type": "heuristic_ranking",
        "ranking_score": 83.5,
        "ranking_strength": "high",
        "legacy_confidence": 0.835,
        "evidence_state": "contested",
        "evidence_completeness": "complete_for_current_model",
        "calibration_status": "not_calibrated",
        "calibrated_probability": None,
    }
    hypothesis = {
        "rank": 1,
        "score": 83.5,
        "confidence": 0.835,
        "confidence_level": "high",
        "confidence_semantics": semantics,
        "root_source": "kubernetes",
        "root_title": "Deployment changed",
        "target_title": "Pod failed",
        "chain": [],
    }
    return {
        "analysis_id": "analysis:tc5",
        "incident_id": "incident:tc5",
        "incident_title": "Pod image pull failed",
        "topology_snapshot_id": "snapshot:tc5",
        "candidate_count": 1,
        "hypothesis_count": 1,
        "top_hypothesis": hypothesis,
        "hypotheses": [hypothesis],
        "confidence_semantics": semantics,
    }


def test_causal_cli_renders_semantics_without_probability_claim(
    monkeypatch,
) -> None:
    rendered_data = []
    rendered_records = []
    monkeypatch.setattr(
        causal_rca,
        "render_data",
        lambda value, **kwargs: rendered_data.append(value),
    )
    monkeypatch.setattr(
        causal_rca,
        "render_records",
        lambda value, **kwargs: rendered_records.append(value),
    )

    causal_rca._render_analysis(
        SimpleNamespace(output_format=OutputFormat.TABLE),
        _payload(),
    )

    summary = rendered_data[0]
    assert summary["top_score"] == 83.5
    assert summary["top_legacy_normalized_rank"] == 0.835
    assert summary["score_type"] == "heuristic_ranking"
    assert summary["evidence_state"] == "contested"
    assert summary["calibration"] == "not_calibrated"
    assert summary["calibrated_probability"] is None
    assert rendered_records[0][0]["band"] == "high"
    assert rendered_records[0][0]["evidence"] == "contested"


def test_causal_cli_json_preserves_complete_backend_payload(
    monkeypatch,
) -> None:
    emitted = []
    payload = _payload()
    monkeypatch.setattr(causal_rca, "emit_json", emitted.append)

    causal_rca._render_analysis(
        SimpleNamespace(output_format=OutputFormat.JSON),
        payload,
    )

    assert emitted == [payload]
    assert emitted[0]["confidence_semantics"]["calibrated_probability"] is None
