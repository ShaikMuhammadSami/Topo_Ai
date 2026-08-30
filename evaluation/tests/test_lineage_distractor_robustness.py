from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.lineage_distractor_robustness import (
    DEFAULT_SEED_DB,
    DISPOSABLE_EVALUATION_TENANT_ID,
    DISTRACTOR_COUNTS,
    EXPECTED_SEED_SHA256,
    FIRST_DIVERGENCE_ORDER,
    GOLDEN_EVENT_ID,
    GOLDEN_IMAGE_DIGEST,
    GOLDEN_INCIDENT_BOUNDARY,
    GOLDEN_MUTATION_ID,
    GOLDEN_REVISION,
    GOLDEN_RUN_ID,
    INSERTION_ORDER_SEEDS,
    SCENARIO_VERSION,
    ScenarioSpec,
    aggregate_results,
    copy_seed_database,
    deterministic_json_bytes,
    distractor_set,
    distractor_timestamp,
    evaluator_ground_truth,
    expected_event_id,
    insertion_permutation,
    parse_utc,
    prepare_disposable_product_database,
    product_distractor_input,
    product_input_contains_answer_hint,
    run_scenario,
    scenario_specs,
    sha256_file,
    structured_golden_cause_match,
    validate_distractor_contract,
    validate_seed_database,
)


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "evaluation/lineage_distractor_robustness.py"


def _sqlite_fixture(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('frozen')")
        connection.commit()
    finally:
        connection.close()
    return sha256_file(path)


def _synthetic_result(
    *,
    scenario_id: str,
    count: int,
    order_seed: int,
    raw_top1: str | None = GOLDEN_EVENT_ID,
    raw_top3: list[str] | None = None,
    supported_top1: str | None = GOLDEN_EVENT_ID,
    supported_top3: list[str] | None = None,
    false_supported: list[str] | None = None,
    divergence: str = "NO_DIVERGENCE",
    valid: bool = True,
) -> dict:
    raw_top3 = [GOLDEN_EVENT_ID] if raw_top3 is None else raw_top3
    supported_top3 = [GOLDEN_EVENT_ID] if supported_top3 is None else supported_top3
    false_supported = [] if false_supported is None else false_supported
    return {
        "metrics": {
            "scenario_id": scenario_id,
            "distractor_count": count,
            "insertion_order_seed": order_seed,
            "inserted_event_ids": [f"event-{index}" for index in range(count)],
            "raw_top1": raw_top1,
            "raw_top3": raw_top3,
            "golden_raw_rank": (
                raw_top3.index(GOLDEN_EVENT_ID) + 1
                if GOLDEN_EVENT_ID in raw_top3
                else None
            ),
            "supported_top1": supported_top1,
            "supported_top3": supported_top3,
            "golden_supported_rank": (
                supported_top3.index(GOLDEN_EVENT_ID) + 1
                if GOLDEN_EVENT_ID in supported_top3
                else None
            ),
            "false_supported_distractor_ids": false_supported,
            "false_supported_distractor_count": len(false_supported),
            "golden_admitted": True,
            "golden_relevance_supported": True,
            "golden_evidence_complete": True,
            "analysis_id": f"analysis-{count}",
            "analysis_normalized_sha256": f"hash-{count}",
            "final_verdict": "PROVEN" if divergence == "NO_DIVERGENCE" else "WRONG",
        },
        "grade": {
            "scenario_valid": valid,
            "first_adversarial_divergence": divergence,
        },
    }


@pytest.fixture(scope="module")
def count_zero_result(tmp_path_factory: pytest.TempPathFactory) -> dict:
    output = tmp_path_factory.mktemp("lineage-2a-count-zero")
    return run_scenario(DEFAULT_SEED_DB, output, ScenarioSpec(0, 0))


def test_seed_database_hash_guard_accepts_exact_hash(tmp_path: Path) -> None:
    seed = tmp_path / "seed.db"
    expected = _sqlite_fixture(seed)
    receipt = validate_seed_database(seed, expected_sha256=expected)
    assert receipt["sha256"] == expected
    assert receipt["quick_check"] == "ok"
    assert receipt["integrity_check"] == "ok"


def test_seed_database_hash_guard_rejects_mismatch(tmp_path: Path) -> None:
    seed = tmp_path / "seed.db"
    _sqlite_fixture(seed)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        validate_seed_database(seed, expected_sha256="0" * 64)


def test_seed_database_is_opened_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = tmp_path / "seed.db"
    expected = _sqlite_fixture(seed)
    original_connect = sqlite3.connect
    calls: list[tuple[str, bool]] = []

    def guarded_connect(database, *args, **kwargs):
        calls.append((str(database), bool(kwargs.get("uri"))))
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    validate_seed_database(seed, expected_sha256=expected)
    assert len(calls) == 1
    assert "mode=ro&immutable=1" in calls[0][0]
    assert calls[0][1] is True


def test_each_scenario_uses_an_exact_copy(tmp_path: Path) -> None:
    seed = tmp_path / "seed.db"
    _sqlite_fixture(seed)
    destination = tmp_path / "scenario/copy.db"
    receipt = copy_seed_database(seed, destination)
    assert receipt["seed_sha256_before_copy"] == receipt["scenario_copy_sha256"]
    assert destination.read_bytes() == seed.read_bytes()


def test_copy_mutation_cannot_mutate_seed(tmp_path: Path) -> None:
    seed = tmp_path / "seed.db"
    original_hash = _sqlite_fixture(seed)
    destination = tmp_path / "scenario.db"
    copy_seed_database(seed, destination)
    connection = sqlite3.connect(destination)
    try:
        connection.execute("INSERT INTO sample VALUES ('scenario-only')")
        connection.commit()
    finally:
        connection.close()
    assert sha256_file(seed) == original_hash
    assert sha256_file(destination) != original_hash


def test_disposable_product_schema_preparation_preserves_frozen_seed(
    tmp_path: Path,
) -> None:
    seed_before = sha256_file(DEFAULT_SEED_DB)
    destination = tmp_path / "current-product-copy.db"
    copy_seed_database(DEFAULT_SEED_DB, destination)

    prepare_disposable_product_database(destination)

    connection = sqlite3.connect(destination)
    try:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0006_domain_tenant_enforcement",)
        assert connection.execute(
            "SELECT tenant_id FROM tenants"
        ).fetchall() == [(DISPOSABLE_EVALUATION_TENANT_ID,)]
        domain_tables = []
        for (table_name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ):
            columns = {
                str(row[1])
                for row in connection.execute(
                    f'PRAGMA table_info("{table_name}")'
                )
            }
            if "tenant_id" in columns and table_name not in {
                "tenants",
                "tenant_memberships",
                "service_api_tenant_bindings",
            }:
                domain_tables.append(table_name)
                assert connection.execute(
                    f'SELECT COUNT(*) FROM "{table_name}" '
                    "WHERE tenant_id IS NULL"
                ).fetchone() == (0,)
        assert len(domain_tables) == 35
    finally:
        connection.close()

    assert sha256_file(DEFAULT_SEED_DB) == seed_before == EXPECTED_SEED_SHA256


def test_product_schema_preparation_refuses_frozen_database() -> None:
    with pytest.raises(ValueError, match="frozen evaluation database"):
        prepare_disposable_product_database(DEFAULT_SEED_DB)


@pytest.mark.parametrize("count", DISTRACTOR_COUNTS[1:])
def test_distractor_ids_are_deterministic(count: int) -> None:
    first = [item["expected_event_id"] for item in distractor_set(count)]
    second = [item["expected_event_id"] for item in distractor_set(count)]
    assert first == second
    assert first == [expected_event_id(count, ordinal) for ordinal in range(count)]


@pytest.mark.parametrize("count", DISTRACTOR_COUNTS[1:])
def test_distractor_timestamps_are_deterministic(count: int) -> None:
    first = [distractor_timestamp(count, ordinal) for ordinal in range(count)]
    second = [distractor_timestamp(count, ordinal) for ordinal in range(count)]
    assert first == second
    assert len(set(first)) == count


@pytest.mark.parametrize("count", DISTRACTOR_COUNTS)
def test_distractor_count_is_exact(count: int) -> None:
    assert len(distractor_set(count)) == count


def test_matrix_has_exactly_sixteen_runs() -> None:
    specs = scenario_specs()
    assert len(specs) == 16
    assert sum(spec.distractor_count == 0 for spec in specs) == 1
    assert {
        spec.order_seed for spec in specs if spec.distractor_count
    } == set(INSERTION_ORDER_SEEDS)


@pytest.mark.parametrize("count", DISTRACTOR_COUNTS[1:])
def test_insertion_permutations_preserve_identical_set(count: int) -> None:
    permutations = [insertion_permutation(count, seed) for seed in INSERTION_ORDER_SEEDS]
    assert all(sorted(value) == list(range(count)) for value in permutations)


def test_nontrivial_insertion_permutations_change_order() -> None:
    assert len(
        {insertion_permutation(50, seed) for seed in INSERTION_ORDER_SEEDS}
    ) > 1


@pytest.mark.parametrize(
    "forbidden",
    [GOLDEN_REVISION, GOLDEN_IMAGE_DIGEST],
)
def test_distractors_do_not_contain_golden_provenance(forbidden: str) -> None:
    serialized = json.dumps(distractor_set(50), sort_keys=True)
    assert forbidden not in serialized


def test_distractors_do_not_contain_golden_producer_run() -> None:
    for item in distractor_set(50):
        product = item["product_input"]
        run_bearing_fields = {
            key: product.get(key)
            for key in (
                "external_id",
                "repository",
                "commit_sha",
                "pipeline_name",
                "release_version",
                "metadata",
                "raw_payload",
            )
        }
        assert GOLDEN_RUN_ID not in json.dumps(run_bearing_fields, sort_keys=True)


def test_distractors_do_not_identify_affected_topology_entity() -> None:
    assert all(
        item["product_input"]["entity_refs"] == [] for item in distractor_set(50)
    )


@pytest.mark.parametrize("count", DISTRACTOR_COUNTS[1:])
def test_distractors_do_not_occur_after_incident(count: int) -> None:
    boundary = parse_utc(GOLDEN_INCIDENT_BOUNDARY)
    assert all(
        parse_utc(item["product_input"]["occurred_at"]) <= boundary
        for item in distractor_set(count)
    )


@pytest.mark.parametrize("count", DISTRACTOR_COUNTS[1:])
def test_distractors_remain_inside_ordinary_path_a(count: int) -> None:
    boundary = parse_utc(GOLDEN_INCIDENT_BOUNDARY)
    gaps = [
        boundary - parse_utc(item["product_input"]["occurred_at"])
        for item in distractor_set(count)
    ]
    assert min(gaps).total_seconds() == 5 * 60
    assert max(gaps).total_seconds() == (5 if count == 1 else 175) * 60


def test_ground_truth_label_is_evaluator_only() -> None:
    product = product_distractor_input(5, 0)
    truth = evaluator_ground_truth(5, 0)
    assert truth["classification"] == "NONCAUSAL_CONTROL"
    assert "classification" not in product
    assert "basis" not in product


@pytest.mark.parametrize("count", DISTRACTOR_COUNTS[1:])
def test_product_visible_metadata_has_no_expected_answer_hint(count: int) -> None:
    for item in distractor_set(count):
        assert product_input_contains_answer_hint(item["product_input"]) is False


def test_distractor_contract_accepts_complete_matrix() -> None:
    for count in DISTRACTOR_COUNTS:
        validate_distractor_contract(distractor_set(count))


def test_frozen_seed_has_exact_golden_event_and_mutation_once() -> None:
    assert sha256_file(DEFAULT_SEED_DB) == EXPECTED_SEED_SHA256
    connection = sqlite3.connect(
        f"file:{DEFAULT_SEED_DB.resolve().as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT metadata_json FROM change_events WHERE event_id = ?",
            (GOLDEN_EVENT_ID,),
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 1
    metadata = json.loads(rows[0]["metadata_json"])
    mutation_ids = [
        item.get("mutation_id") for item in metadata["source_file_mutations"]
    ]
    assert mutation_ids.count(GOLDEN_MUTATION_ID) == 1


def test_count_zero_scenario_output_is_valid_and_proven(count_zero_result: dict) -> None:
    assert count_zero_result["grade"]["scenario_valid"] is True
    assert count_zero_result["grade"]["first_adversarial_divergence"] == "NO_DIVERGENCE"
    assert count_zero_result["metrics"]["final_verdict"] == "PROVEN"


def test_count_zero_separates_raw_and_supported_metrics(count_zero_result: dict) -> None:
    metrics = count_zero_result["metrics"]
    assert metrics["raw_top1"] == GOLDEN_EVENT_ID
    assert metrics["supported_top1"] == GOLDEN_EVENT_ID
    assert "raw_top3" in metrics
    assert "supported_top3" in metrics
    assert metrics["golden_raw_rank"] == 1
    assert metrics["golden_supported_rank"] == 1


def test_false_supported_detection_uses_evaluator_ids() -> None:
    false_id = "change-event:control"
    results = [
        _synthetic_result(
            scenario_id="count-001-order-0",
            count=1,
            order_seed=0,
            supported_top1=false_id,
            supported_top3=[false_id, GOLDEN_EVENT_ID],
            false_supported=[false_id],
            divergence="FALSE_SUPPORTED_DISTRACTOR",
        )
    ]
    aggregate = aggregate_results(results)
    assert aggregate["false_supported_distractor_count"] == 1
    assert aggregate["false_supported_candidate_rate"] == {
        "numerator": 1,
        "denominator": 1,
        "rate": 1.0,
    }


def test_supported_top1_flip_calculation_includes_abstention() -> None:
    aggregate = aggregate_results(
        [
            _synthetic_result(
                scenario_id="count-001-order-0",
                count=1,
                order_seed=0,
                supported_top1=None,
                supported_top3=[],
                divergence="SUPPORTED_TOP1_FLIPPED",
            )
        ]
    )
    assert aggregate["supported_top1_flip_rate"]["numerator"] == 1
    assert aggregate["supported_top1_flip_rate"]["denominator"] == 1


def test_supported_top3_retention_calculation_is_raw_counted() -> None:
    aggregate = aggregate_results(
        [
            _synthetic_result(scenario_id="a", count=1, order_seed=0),
            _synthetic_result(
                scenario_id="b",
                count=1,
                order_seed=1,
                supported_top3=["other"],
                divergence="SUPPORTED_TOP3_DROPPED",
            ),
        ]
    )
    assert aggregate["supported_top3_retention_rate"] == {
        "numerator": 1,
        "denominator": 2,
        "rate": 0.5,
    }


def test_order_sensitivity_compares_supported_result_only() -> None:
    results = [
        _synthetic_result(scenario_id="a", count=5, order_seed=0),
        _synthetic_result(
            scenario_id="b",
            count=5,
            order_seed=1,
            supported_top1="other",
            supported_top3=["other", GOLDEN_EVENT_ID],
        ),
        _synthetic_result(scenario_id="c", count=5, order_seed=2),
    ]
    aggregate = aggregate_results(results)
    assert aggregate["order_sensitive_counts"] == [5]
    assert aggregate["order_sensitivity_rate"]["rate"] == 1.0


def test_aggregate_report_is_deterministic() -> None:
    results = [
        _synthetic_result(scenario_id="a", count=5, order_seed=0),
        _synthetic_result(scenario_id="b", count=5, order_seed=1),
        _synthetic_result(scenario_id="c", count=5, order_seed=2),
    ]
    first = deterministic_json_bytes(aggregate_results(results))
    second = deterministic_json_bytes(aggregate_results(results))
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_frozen_golden_cause_match_remains_exactly_structured() -> None:
    connection = sqlite3.connect(
        f"file:{DEFAULT_SEED_DB.resolve().as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT metadata_json FROM change_events WHERE event_id = ?",
            (GOLDEN_EVENT_ID,),
        ).fetchone()
    finally:
        connection.close()
    result = structured_golden_cause_match(
        SimpleNamespace(metadata_json=row["metadata_json"])
    )
    assert result["exact"] is True
    assert result["matched_field_count"] == result["required_field_count"] == 8
    assert result["method"] == "exact_structured_initiating_mutation_fields"


def test_harness_uses_no_fuzzy_embedding_or_llm_matcher() -> None:
    source = HARNESS.read_text(encoding="utf-8").lower()
    for forbidden in (
        "sequencematcher",
        "rapidfuzz",
        "levenshtein",
        "openai",
        "sentence_transformer",
    ):
        assert forbidden not in source
    result = structured_golden_cause_match(None)
    assert result["fuzzy_matching_used"] is False
    assert result["embeddings_used"] is False
    assert result["llm_used"] is False


def test_harness_has_no_provider_or_kubernetes_execution_transport() -> None:
    source = HARNESS.read_text(encoding="utf-8").lower()
    for forbidden in (
        "import subprocess",
        "import requests",
        "import httpx",
        "kubectl",
        "githubconnector",
        "kubernetescollector",
    ):
        assert forbidden not in source


def test_divergence_taxonomy_order_is_frozen() -> None:
    assert FIRST_DIVERGENCE_ORDER == (
        "GOLDEN_CAUSE_NOT_ADMITTED",
        "GOLDEN_CAUSAL_RELEVANCE_LOST",
        "FALSE_SUPPORTED_DISTRACTOR",
        "SUPPORTED_TOP1_FLIPPED",
        "SUPPORTED_TOP3_DROPPED",
        "ORDER_DEPENDENT_SUPPORTED_RESULT",
        "GOLDEN_EVIDENCE_CHAIN_DEGRADED",
        "NO_DIVERGENCE",
    )


def test_scenario_version_is_explicit() -> None:
    assert SCENARIO_VERSION == "lineage-2a-distractor-source-robustness-v1"
