from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sqlite3
import sys
from argparse import Namespace
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCENARIO_VERSION = "lineage-2a-distractor-source-robustness-v1"
ACCEPTED_MAIN_COMMIT = "4f119ae"
GOLDEN_PRODUCT_COMMIT = "42f68835333c71371d3e54033a9bcdd69c1de36d"

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
DEFAULT_SEED_DB = (
    ROOT
    / "evaluation/results/lineage/post-sc4"
    / "topo-product-32695735269.db"
)
DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "evaluation/results/lineage/adversarial"
    / "lineage-2a-distractors"
)

EXPECTED_SEED_SHA256 = (
    "9f3918a027c6d9a7bbd679495c48b387c9a1ac8c86141f85cf8b4495cd00b69f"
)
DISPOSABLE_EVALUATION_TENANT_ID = (
    "tenant:eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
)
DISTRACTOR_COUNTS = (0, 1, 5, 10, 20, 50)
INSERTION_ORDER_SEEDS = (0, 1, 2)
LOOKBACK_MINUTES = 180

GOLDEN_EVENT_ID = "change-event:20a8946c8c445153d85c90ee2166d487"
GOLDEN_MUTATION_ID = (
    "source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633"
)
GOLDEN_REVISION = "4149b194c4c4fdfdcd402a157c5336ad59dfdbbe"
GOLDEN_PARENT_REVISION = "f9b152133a8075428766dd48b3f752b255ec5270"
GOLDEN_RUN_ID = "32695735269"
GOLDEN_IMAGE_DIGEST = (
    "sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed"
)
GOLDEN_INCIDENT_ID = (
    "incident:docker-desktop:topo-eval-lineage-causal-32695735269:"
    "workload-lineage-causal-fixture:1afbac4ef76921c7aca2c3d3"
)
GOLDEN_INCIDENT_BOUNDARY = "2026-08-26T05:09:49Z"
GOLDEN_SNAPSHOT_ID = "snapshot:actions-enriched:20260826T051031Z:2d8416d3"
GOLDEN_AFFECTED_ENTITY_ID = (
    "k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168"
)
GOLDEN_REPOSITORY = "ShaikMuhammadSami/Topo_Ai"
GOLDEN_FILE_PATH = "evaluation/fixtures/lineage-image/runtime-mode.txt"
GOLDEN_BEFORE_HASH = (
    "63745aef95742025c6d7a1b4fc0e7107e6f3c3eb2e0cb290f33c46f176e6740d"
)
GOLDEN_AFTER_HASH = (
    "2056a28ea38a000f3a3328cb7fabe330638d3258affe1a869e3f92986222d997"
)

SUPPORTED_EVIDENCE_STATE = "supported_under_current_model"
SUPPORTED_RELEVANCE_STATES = {"direct", "semantic_path"}
FORBIDDEN_PRODUCT_HINTS = (
    "noncausal",
    "non-causal",
    "distractor",
    "expected wrong",
    "expected=false",
    "expected_false",
)
FIRST_DIVERGENCE_ORDER = (
    "GOLDEN_CAUSE_NOT_ADMITTED",
    "GOLDEN_CAUSAL_RELEVANCE_LOST",
    "FALSE_SUPPORTED_DISTRACTOR",
    "SUPPORTED_TOP1_FLIPPED",
    "SUPPORTED_TOP3_DROPPED",
    "ORDER_DEPENDENT_SUPPORTED_RESULT",
    "GOLDEN_EVIDENCE_CHAIN_DEGRADED",
    "NO_DIVERGENCE",
)


@dataclass(frozen=True)
class ScenarioSpec:
    distractor_count: int
    order_seed: int

    @property
    def relative_directory(self) -> Path:
        return Path(f"count-{self.distractor_count:03d}") / f"order-{self.order_seed}"

    @property
    def scenario_id(self) -> str:
        return f"count-{self.distractor_count:03d}-order-{self.order_seed}"


def scenario_specs() -> tuple[ScenarioSpec, ...]:
    return (ScenarioSpec(0, 0),) + tuple(
        ScenarioSpec(count, order_seed)
        for count in DISTRACTOR_COUNTS
        if count
        for order_seed in INSERTION_ORDER_SEEDS
    )


def deterministic_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n"
    ).encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(deterministic_json_bytes(value))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_only_sqlite_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"


def validate_seed_database(
    seed_db: Path,
    *,
    expected_sha256: str = EXPECTED_SEED_SHA256,
) -> dict[str, Any]:
    seed_db = seed_db.resolve()
    if not seed_db.is_file():
        raise FileNotFoundError(f"Frozen seed database does not exist: {seed_db}")
    actual_hash = sha256_file(seed_db)
    if actual_hash.lower() != expected_sha256.lower():
        raise ValueError(
            "Frozen seed database SHA-256 mismatch: "
            f"expected {expected_sha256.lower()}, observed {actual_hash.lower()}"
        )
    connection = sqlite3.connect(
        _read_only_sqlite_uri(seed_db),
        uri=True,
    )
    try:
        connection.execute("PRAGMA query_only = ON")
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        integrity_check = str(
            connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        table_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    if quick_check != "ok" or integrity_check != "ok":
        raise ValueError(
            "Frozen seed database failed SQLite integrity checks: "
            f"quick_check={quick_check}, integrity_check={integrity_check}"
        )
    return {
        "path": seed_db.as_posix(),
        "sha256": actual_hash,
        "quick_check": quick_check,
        "integrity_check": integrity_check,
        "table_count": table_count,
        "open_mode": "mode=ro&immutable=1; PRAGMA query_only=ON",
    }


def copy_seed_database(seed_db: Path, destination: Path) -> dict[str, str]:
    seed_hash_before = sha256_file(seed_db)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_db, destination)
    copy_hash = sha256_file(destination)
    seed_hash_after = sha256_file(seed_db)
    if copy_hash != seed_hash_before or seed_hash_after != seed_hash_before:
        raise AssertionError("Seed copy operation did not preserve exact database bytes.")
    return {
        "seed_sha256_before_copy": seed_hash_before,
        "scenario_copy_sha256": copy_hash,
        "seed_sha256_after_copy": seed_hash_after,
    }


def parse_utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Evaluation timestamps must include a UTC offset.")
    return result.astimezone(timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def distractor_offset_seconds(count: int, ordinal: int) -> int:
    if count <= 0 or not 0 <= ordinal < count:
        raise ValueError("Distractor ordinal must be inside a non-zero count.")
    if count == 1:
        return 5 * 60
    return (5 * 60) + ((170 * 60 * ordinal) // (count - 1))


def distractor_timestamp(count: int, ordinal: int) -> str:
    boundary = parse_utc(GOLDEN_INCIDENT_BOUNDARY)
    return format_utc(
        boundary - timedelta(seconds=distractor_offset_seconds(count, ordinal))
    )


def _stable_hex(*parts: Any, length: int) -> str:
    material = "|".join(str(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:length]


def distractor_revision(count: int, ordinal: int) -> str:
    return _stable_hex(SCENARIO_VERSION, count, ordinal, "revision", length=40)


def distractor_repository(count: int, ordinal: int) -> str:
    suffix = _stable_hex(SCENARIO_VERSION, count, ordinal, "repository", length=12)
    return f"eval-controls/service-{suffix}"


def distractor_external_id(count: int, ordinal: int) -> str:
    return f"github:{distractor_repository(count, ordinal)}:{distractor_revision(count, ordinal)}"


def expected_event_id(count: int, ordinal: int) -> str:
    fingerprint_payload = {
        "source": "github",
        "external_id": distractor_external_id(count, ordinal),
    }
    fingerprint = sha256_bytes(
        json.dumps(
            fingerprint_payload,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    )
    canonical_suffix = sha256_bytes(fingerprint.encode("utf-8"))[:32]
    return f"change-event:{canonical_suffix}"


def product_distractor_input(count: int, ordinal: int) -> dict[str, Any]:
    revision = distractor_revision(count, ordinal)
    repository = distractor_repository(count, ordinal)
    return {
        "source": "github",
        "kind": "code",
        "external_id": distractor_external_id(count, ordinal),
        "title": f"Update repository revision {revision[:12]}",
        "summary": "Repository revision updated.",
        "actor": "automation-bot",
        "occurred_at": distractor_timestamp(count, ordinal),
        "environment": "evaluation",
        "cluster_name": "docker-desktop",
        "namespace": "topo-eval-lineage-causal-32695735269",
        "repository": repository,
        "commit_sha": revision,
        "risk_score": 65 + (ordinal % 20),
        "status": "observed",
        "entity_refs": [],
        "metadata": {},
        "raw_payload": {},
    }


def evaluator_ground_truth(count: int, ordinal: int) -> dict[str, Any]:
    return {
        "event_id": expected_event_id(count, ordinal),
        "classification": "NONCAUSAL_CONTROL",
        "basis": (
            "Independent synthetic repository and revision with no immutable "
            "artifact, producer run, entity, or source-to-runtime lineage evidence."
        ),
    }


def distractor_set(count: int) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "ordinal": ordinal,
            "expected_event_id": expected_event_id(count, ordinal),
            "product_input": product_distractor_input(count, ordinal),
            "ground_truth": evaluator_ground_truth(count, ordinal),
        }
        for ordinal in range(count)
    )


def insertion_permutation(count: int, order_seed: int) -> tuple[int, ...]:
    values = list(range(count))
    random.Random(f"{SCENARIO_VERSION}|{count}|{order_seed}").shuffle(values)
    return tuple(values)


def _walk_scalars(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_scalars(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_scalars(item)
    elif value is not None:
        yield str(value)


def product_input_contains_answer_hint(value: Mapping[str, Any]) -> bool:
    text = "\n".join(_walk_scalars(value)).lower()
    return any(hint in text for hint in FORBIDDEN_PRODUCT_HINTS)


def validate_distractor_contract(items: Iterable[Mapping[str, Any]]) -> None:
    values = list(items)
    event_ids = [str(item["expected_event_id"]) for item in values]
    if len(event_ids) != len(set(event_ids)):
        raise AssertionError("Distractor canonical event IDs are not unique.")
    boundary = parse_utc(GOLDEN_INCIDENT_BOUNDARY)
    for item in values:
        product_input = dict(item["product_input"])
        serialized = json.dumps(product_input, sort_keys=True)
        if product_input_contains_answer_hint(product_input):
            raise AssertionError("Product-visible distractor contains an answer hint.")
        for forbidden in (GOLDEN_REVISION, GOLDEN_IMAGE_DIGEST):
            if forbidden in serialized:
                raise AssertionError("Distractor contains frozen golden provenance.")
        run_bearing_fields = {
            key: product_input.get(key)
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
        if GOLDEN_RUN_ID in json.dumps(run_bearing_fields, sort_keys=True):
            raise AssertionError("Distractor contains the golden producer run.")
        if product_input.get("entity_refs"):
            raise AssertionError("Temporal-only distractors cannot identify entities.")
        effective_at = parse_utc(str(product_input["occurred_at"]))
        gap = boundary - effective_at
        if gap.total_seconds() < 0:
            raise AssertionError("Distractor occurs after the incident boundary.")
        if gap > timedelta(minutes=LOOKBACK_MINUTES):
            raise AssertionError("Distractor falls outside ordinary temporal Path A.")


def _ensure_backend_import_path() -> None:
    value = str(BACKEND_ROOT)
    if value not in sys.path:
        sys.path.insert(0, value)


def prepare_disposable_product_database(database_path: Path) -> None:
    """Upgrade only an isolated evaluation copy to the current ORM schema."""

    database_path = database_path.resolve()
    if database_path == DEFAULT_SEED_DB.resolve():
        raise ValueError("Refusing to prepare the frozen evaluation database.")

    connection = sqlite3.connect(database_path)
    try:
        table_names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "alembic_version" in table_names:
            revisions = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT version_num FROM alembic_version"
                )
            )
            if revisions == ("0007_machine_tenant_binding",):
                return
            raise ValueError(
                "Disposable evaluation database has unexpected migration state."
            )
        if len(table_names) != 38:
            raise ValueError(
                "Disposable evaluation database is not the accepted "
                "38-table pre-tenancy fixture."
            )
    finally:
        connection.close()

    _ensure_backend_import_path()
    from alembic import command
    from sqlalchemy import create_engine, text

    from app.db.schema_management import alembic_config

    engine = create_engine(
        f"sqlite+pysqlite:///{database_path.as_posix()}"
    )
    try:
        with engine.begin() as migration_connection:
            config = alembic_config(connection=migration_connection)
            config.cmd_opts = Namespace(x=[])
            command.stamp(config, "0001_current_schema")
            command.upgrade(config, "0004_tenant_foundation")
            migration_connection.execute(
                text(
                    "INSERT INTO tenants "
                    "(tenant_id, display_name, status, created_at, "
                    "updated_at, created_by_subject) VALUES "
                    "(:tenant_id, :display_name, 'active', :created_at, "
                    ":created_at, :created_by_subject)"
                ),
                {
                    "tenant_id": DISPOSABLE_EVALUATION_TENANT_ID,
                    "display_name": "Disposable evaluation fixture",
                    "created_at": "2026-08-30T00:00:00+00:00",
                    "created_by_subject": "evaluation:fixture-migration",
                },
            )
            config.cmd_opts = Namespace(
                x=[
                    "legacy_tenant_id="
                    f"{DISPOSABLE_EVALUATION_TENANT_ID}"
                ]
            )
            command.upgrade(config, "0005_domain_tenant_ownership")
            config.cmd_opts = Namespace(x=[])
            command.upgrade(config, "0006_domain_tenant_enforcement")
            # Explicit assertion for this isolated single-scenario copy only.
            # Never migrate the frozen source or infer from fixture identities.
            config.cmd_opts = Namespace(x=[
                f"legacy_machine_tenant_id={DISPOSABLE_EVALUATION_TENANT_ID}"
            ])
            command.upgrade(config, "0007_machine_tenant_binding")
    finally:
        engine.dispose()


def _scenario_engine(database_path: Path):
    _ensure_backend_import_path()
    from sqlalchemy import create_engine

    prepare_disposable_product_database(database_path)
    return create_engine(f"sqlite+pysqlite:///{database_path.resolve().as_posix()}")


def ingest_distractors(session: Any, items: Iterable[Mapping[str, Any]], order: Iterable[int]) -> list[str]:
    _ensure_backend_import_path()
    from app.models.change_events import ChangeEventCreate
    from app.models.temporal import TimeOrigin, TimeQuality
    from app.repositories.change_event_repository import ingest_change_event

    indexed = {int(item["ordinal"]): item for item in items}
    event_ids: list[str] = []
    for ordinal in order:
        item = indexed[int(ordinal)]
        request = ChangeEventCreate.model_validate(item["product_input"])
        receipt = ingest_change_event(
            session,
            tenant_id=DISPOSABLE_EVALUATION_TENANT_ID,
            request=request,
            auto_correlate=False,
            source_time_trusted=True,
            observed_at=request.occurred_at,
            source_field="ChangeEventCreate.occurred_at",
            source_time_origin=TimeOrigin.SOURCE_REPORTED,
            source_time_quality=TimeQuality.EXACT,
            commit=True,
        )
        expected = str(item["expected_event_id"])
        if receipt.event_id != expected or not receipt.created:
            raise AssertionError(
                "Distractor ingestion was not a fresh deterministic canonical event."
            )
        event_ids.append(receipt.event_id)
    return event_ids


def _load_record_json(record: Any, attribute: str) -> dict[str, Any]:
    value = json.loads(str(getattr(record, attribute)))
    if not isinstance(value, dict):
        raise ValueError(f"{attribute} must contain a JSON object.")
    return value


def _mutation_identity(event_record: Any) -> dict[str, Any]:
    metadata = _load_record_json(event_record, "metadata_json")
    mutations = metadata.get("source_file_mutations")
    mutation = mutations[0] if isinstance(mutations, list) and len(mutations) == 1 else {}
    before = mutation.get("before") if isinstance(mutation, dict) else {}
    after = mutation.get("after") if isinstance(mutation, dict) else {}
    parent = mutation.get("parent_context") if isinstance(mutation, dict) else {}
    parents = parent.get("parent_shas") if isinstance(parent, dict) else []
    return {
        "repository": (
            (mutation.get("repository") or {}).get("full_name")
            if isinstance(mutation, dict)
            else None
        ),
        "parent_commit_sha": parents[0] if isinstance(parents, list) and len(parents) == 1 else None,
        "commit_sha": mutation.get("commit_sha") if isinstance(mutation, dict) else None,
        "file_path": mutation.get("current_path") if isinstance(mutation, dict) else None,
        "before_hash": before.get("content_sha256") if isinstance(before, dict) else None,
        "after_hash": after.get("content_sha256") if isinstance(after, dict) else None,
        "before_semantic_value": before.get("semantic_value") if isinstance(before, dict) else None,
        "after_semantic_value": after.get("semantic_value") if isinstance(after, dict) else None,
    }


def structured_golden_cause_match(event_record: Any | None) -> dict[str, Any]:
    expected = {
        "repository": GOLDEN_REPOSITORY,
        "parent_commit_sha": GOLDEN_PARENT_REVISION,
        "commit_sha": GOLDEN_REVISION,
        "file_path": GOLDEN_FILE_PATH,
        "before_hash": GOLDEN_BEFORE_HASH,
        "after_hash": GOLDEN_AFTER_HASH,
        "before_semantic_value": "healthy",
        "after_semantic_value": "fail",
    }
    actual = _mutation_identity(event_record) if event_record is not None else {}
    comparisons = {
        key: (
            "matched"
            if actual.get(key) == expected_value
            else "missing"
            if actual.get(key) is None
            else "mismatched"
        )
        for key, expected_value in expected.items()
    }
    matched = sum(value == "matched" for value in comparisons.values())
    return {
        "method": "exact_structured_initiating_mutation_fields",
        "fuzzy_matching_used": False,
        "embeddings_used": False,
        "llm_used": False,
        "expected": expected,
        "actual": actual,
        "comparisons": comparisons,
        "matched_field_count": matched,
        "required_field_count": len(expected),
        "exact": matched == len(expected),
    }


def _ledger_summary(hypothesis: Any) -> dict[str, Any]:
    ledger = hypothesis.evidence_ledger
    if ledger is None:
        return {
            "supporting": 0,
            "contradicting": 0,
            "missing": 0,
            "unknown": 0,
            "claim_types": [],
            "supporting_refs": [],
            "topology_relationships": [],
        }
    all_items = [*ledger.supporting, *ledger.contradicting, *ledger.missing]
    return {
        "supporting": len(ledger.supporting),
        "contradicting": len(ledger.contradicting),
        "missing": len(ledger.missing),
        "unknown": sum(item.quality.value == "unknown" for item in all_items),
        "claim_types": sorted({item.claim_type.value for item in all_items}),
        "supporting_refs": sorted(
            {
                f"{reference.reference_type}:{reference.reference_id}"
                for item in ledger.supporting
                for reference in item.source_references
            }
        ),
        "topology_relationships": sorted(
            {
                relationship_id
                for item in all_items
                for relationship_id in item.relationship_ids
            }
        ),
    }


def _normalized_analysis(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalized_analysis(item)
            for key, item in sorted(value.items())
            if key
            not in {
                "generated_at",
                "created_at",
                "updated_at",
                "recorded_at",
            }
        }
    if isinstance(value, list):
        return [_normalized_analysis(item) for item in value]
    return value


def normalized_analysis_hash(analysis: Mapping[str, Any]) -> str:
    return sha256_bytes(deterministic_json_bytes(_normalized_analysis(dict(analysis))))


def _find_audit(values: Iterable[Any], event_id: str, attribute: str) -> Any | None:
    return next((item for item in values if str(getattr(item, attribute)) == event_id), None)


def _is_supported_hypothesis(hypothesis: Any) -> bool:
    semantics = hypothesis.confidence_semantics
    return bool(
        semantics is not None
        and semantics.evidence_state.value == SUPPORTED_EVIDENCE_STATE
    )


def _golden_invariants(session: Any, analysis: Any) -> dict[str, bool]:
    _ensure_backend_import_path()
    from sqlalchemy import func, select
    from app.db.models import ChangeEventRecord, IncidentRecord, SnapshotRecord

    golden_count = int(
        session.scalar(
            select(func.count()).select_from(ChangeEventRecord).where(
                ChangeEventRecord.event_id == GOLDEN_EVENT_ID
            )
        )
        or 0
    )
    golden = session.get(ChangeEventRecord, GOLDEN_EVENT_ID)
    metadata = _load_record_json(golden, "metadata_json") if golden is not None else {}
    mutation_ids = [
        str(item.get("mutation_id"))
        for item in metadata.get("source_file_mutations", [])
        if isinstance(item, dict)
    ]
    incident = session.get(IncidentRecord, GOLDEN_INCIDENT_ID)
    snapshot = session.get(SnapshotRecord, GOLDEN_SNAPSHOT_ID)
    payload = _load_record_json(snapshot, "payload_json") if snapshot is not None else {}
    image_entity_id = f"artifact:container-image:{GOLDEN_IMAGE_DIGEST}"
    image_count = sum(
        isinstance(entity, dict) and entity.get("id") == image_entity_id
        for entity in payload.get("entities", [])
    )
    admission = _find_audit(
        analysis.lineage_admission_audit,
        GOLDEN_EVENT_ID,
        "canonical_change_id",
    )
    lineage_paths = list(admission.lineage_paths) if admission is not None else []
    return {
        "golden_source_event_exists_exactly_once": golden_count == 1,
        "golden_mutation_exists_exactly_once": mutation_ids.count(GOLDEN_MUTATION_ID) == 1,
        "golden_immutable_lineage_intact": any(
            path.revision == GOLDEN_REVISION
            and path.run_id == GOLDEN_RUN_ID
            and path.image_digest == GOLDEN_IMAGE_DIGEST
            for path in lineage_paths
        ),
        "golden_sc2_admission_available": bool(
            admission is not None
            and "exact_immutable_lineage" in {
                item.value for item in admission.admission_basis
            }
        ),
        "golden_image_anchor_exact": image_count == 1,
        "incident_id_unchanged": incident is not None and incident.incident_id == GOLDEN_INCIDENT_ID,
        "incident_boundary_unchanged": bool(
            incident is not None
            and parse_utc(incident.first_observed_at)
            == parse_utc(GOLDEN_INCIDENT_BOUNDARY)
        ),
        "pinned_topology_id_unchanged": bool(
            incident is not None and incident.topology_snapshot_id == GOLDEN_SNAPSHOT_ID
        ),
        "affected_entity_unchanged": bool(
            incident is not None
            and incident.affected_entity_id == GOLDEN_AFFECTED_ENTITY_ID
        ),
    }


def _distractor_invariants(session: Any, items: Iterable[Mapping[str, Any]], analysis: Any) -> dict[str, bool]:
    _ensure_backend_import_path()
    from sqlalchemy import func, select
    from app.db.models import ChangeEventRecord

    values = list(items)
    expected_ids = [str(item["expected_event_id"]) for item in values]
    records = {
        event_id: session.get(ChangeEventRecord, event_id) for event_id in expected_ids
    }
    audit_by_id = {item.event_id: item for item in analysis.candidate_selection_audit}
    boundary = parse_utc(GOLDEN_INCIDENT_BOUNDARY)
    canonical_counts = {
        event_id: int(
            session.scalar(
                select(func.count()).select_from(ChangeEventRecord).where(
                    ChangeEventRecord.event_id == event_id
                )
            )
            or 0
        )
        for event_id in expected_ids
    }
    serialized = {
        event_id: (
            json.dumps(_load_record_json(record, "metadata_json"), sort_keys=True)
            + json.dumps(_load_record_json(record, "raw_payload_json"), sort_keys=True)
            if record is not None
            else ""
        )
        for event_id, record in records.items()
    }
    return {
        "canonical_event_exists_exactly_once": all(
            count == 1 for count in canonical_counts.values()
        ),
        "effective_at_not_after_incident": all(
            record is not None
            and parse_utc(record.occurred_at) <= boundary
            for record in records.values()
        ),
        "effective_at_within_path_a": all(
            record is not None
            and timedelta(0) <= boundary - parse_utc(record.occurred_at)
            <= timedelta(minutes=LOOKBACK_MINUTES)
            for record in records.values()
        ),
        "no_exact_immutable_lineage_basis": all(
            "exact_immutable_lineage"
            not in {
                basis.value
                for basis in getattr(audit_by_id.get(event_id), "admission_basis", [])
            }
            for event_id in expected_ids
        ),
        "no_golden_producer_run": all(
            GOLDEN_RUN_ID not in serialized[event_id] for event_id in expected_ids
        ),
        "no_golden_image_digest": all(
            GOLDEN_IMAGE_DIGEST not in serialized[event_id] for event_id in expected_ids
        ),
        "no_affected_topology_identity": all(
            record is not None
            and GOLDEN_AFFECTED_ENTITY_ID not in serialized[event_id]
            for event_id, record in records.items()
        ),
        "no_duplicate_canonical_event_id": len(expected_ids) == len(set(expected_ids)),
    }


def grade_analysis(session: Any, analysis: Any, items: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _ensure_backend_import_path()
    from app.db.models import ChangeEventRecord

    values = list(items)
    distractor_ids = {str(item["expected_event_id"]) for item in values}
    selection = sorted(analysis.candidate_selection_audit, key=lambda item: item.raw_rank)
    raw_ids = [item.event_id for item in selection]
    supported = sorted(
        (item for item in analysis.hypotheses if _is_supported_hypothesis(item)),
        key=lambda item: item.rank,
    )
    supported_ids = [item.root_event_id for item in supported]
    false_supported = sorted(distractor_ids.intersection(supported_ids))
    golden_selection = _find_audit(selection, GOLDEN_EVENT_ID, "event_id")
    golden_relevance = _find_audit(
        analysis.candidate_relevance_audit,
        GOLDEN_EVENT_ID,
        "candidate_event_id",
    )
    golden_hypothesis = next(
        (item for item in analysis.hypotheses if item.root_event_id == GOLDEN_EVENT_ID),
        None,
    )
    golden_ledger = _ledger_summary(golden_hypothesis) if golden_hypothesis else _ledger_summary(type("NoHypothesis", (), {"evidence_ledger": None})())
    top_supported = supported[0] if supported else None
    top_event = (
        session.get(ChangeEventRecord, top_supported.root_event_id)
        if top_supported is not None
        else None
    )
    structured_match = structured_golden_cause_match(top_event)
    golden_invariants = _golden_invariants(session, analysis)
    distractor_invariants = _distractor_invariants(session, values, analysis)
    valid = all(golden_invariants.values()) and all(distractor_invariants.values())
    golden_admitted = bool(
        golden_selection is not None
        and "exact_immutable_lineage"
        in {item.value for item in golden_selection.admission_basis}
    )
    golden_relevance_supported = bool(
        golden_relevance is not None
        and golden_relevance.relevance_status.value in SUPPORTED_RELEVANCE_STATES
        and golden_relevance.topology_component > 0
    )
    golden_evidence_complete = bool(
        golden_hypothesis is not None
        and golden_hypothesis.confidence_semantics is not None
        and golden_hypothesis.confidence_semantics.evidence_completeness.value
        == "complete_for_current_model"
        and golden_ledger["contradicting"] == 0
        and golden_ledger["missing"] == 0
        and golden_ledger["unknown"] == 0
    )

    if not golden_admitted:
        divergence = "GOLDEN_CAUSE_NOT_ADMITTED"
    elif not golden_relevance_supported:
        divergence = "GOLDEN_CAUSAL_RELEVANCE_LOST"
    elif false_supported:
        divergence = "FALSE_SUPPORTED_DISTRACTOR"
    elif (supported_ids[0] if supported_ids else None) != GOLDEN_EVENT_ID:
        divergence = "SUPPORTED_TOP1_FLIPPED"
    elif GOLDEN_EVENT_ID not in supported_ids[:3]:
        divergence = "SUPPORTED_TOP3_DROPPED"
    elif not golden_evidence_complete:
        divergence = "GOLDEN_EVIDENCE_CHAIN_DEGRADED"
    else:
        divergence = "NO_DIVERGENCE"

    if not valid:
        verdict = "INVALID"
    elif divergence == "NO_DIVERGENCE" and structured_match["exact"]:
        verdict = "PROVEN"
    elif false_supported or (supported_ids and supported_ids[0] != GOLDEN_EVENT_ID):
        verdict = "WRONG"
    elif GOLDEN_EVENT_ID in supported_ids[:3]:
        verdict = "PARTIAL"
    else:
        verdict = "MISSING"

    relevance_by_id = {
        item.candidate_event_id: item for item in analysis.candidate_relevance_audit
    }
    false_supported_forensics = []
    for hypothesis in supported:
        if hypothesis.root_event_id not in false_supported:
            continue
        relevance = relevance_by_id.get(hypothesis.root_event_id)
        false_supported_forensics.append(
            {
                "event_id": hypothesis.root_event_id,
                "hypothesis_id": hypothesis.hypothesis_id,
                "rank": hypothesis.rank,
                "score": hypothesis.score,
                "confidence_semantics": hypothesis.confidence_semantics.model_dump(mode="json"),
                "tc4": _ledger_summary(hypothesis),
                "relevance": relevance.model_dump(mode="json") if relevance else None,
            }
        )

    metrics = {
        "distractor_count": len(values),
        "total_candidate_count": analysis.candidate_count,
        "golden_candidate_present": GOLDEN_EVENT_ID in raw_ids,
        "golden_candidate_occurrence_count": raw_ids.count(GOLDEN_EVENT_ID),
        "golden_admission_basis": (
            [item.value for item in golden_selection.admission_basis]
            if golden_selection
            else []
        ),
        "golden_relevance_state": (
            golden_relevance.relevance_status.value if golden_relevance else None
        ),
        "golden_topology_component": (
            golden_relevance.topology_component if golden_relevance else None
        ),
        "golden_tc4": golden_ledger,
        "raw_top1": raw_ids[0] if raw_ids else None,
        "raw_top3": raw_ids[:3],
        "golden_raw_rank": (
            raw_ids.index(GOLDEN_EVENT_ID) + 1 if GOLDEN_EVENT_ID in raw_ids else None
        ),
        "supported_hypothesis_count": len(supported_ids),
        "supported_top1": supported_ids[0] if supported_ids else None,
        "supported_top3": supported_ids[:3],
        "golden_supported_rank": (
            supported_ids.index(GOLDEN_EVENT_ID) + 1
            if GOLDEN_EVENT_ID in supported_ids
            else None
        ),
        "false_supported_distractor_ids": false_supported,
        "false_supported_distractor_count": len(false_supported),
        "unsupported_distractor_count": len(distractor_ids - set(false_supported)),
        "distractor_relevance_supported_count": sum(
            relevance_by_id[event_id].relevance_status.value
            in SUPPORTED_RELEVANCE_STATES
            for event_id in distractor_ids.intersection(relevance_by_id)
        ),
        "final_semantic_level": (
            "INITIATING_MUTATION"
            if structured_match["exact"] and top_supported is not None
            else "ABSTAINED"
            if top_supported is None
            else "UNRELATED"
        ),
        "structural_source_cause_match": structured_match,
        "evidence_completeness": (
            top_supported.confidence_semantics.evidence_completeness.value
            if top_supported is not None and top_supported.confidence_semantics
            else "unknown"
        ),
        "final_verdict": verdict,
        "analysis_id": analysis.analysis_id,
        "analysis_normalized_sha256": normalized_analysis_hash(
            analysis.model_dump(mode="json")
        ),
        "safe_abstention": top_supported is None,
        "golden_admitted": golden_admitted,
        "golden_relevance_supported": golden_relevance_supported,
        "golden_evidence_complete": golden_evidence_complete,
    }
    grade = {
        "scenario_valid": valid,
        "final_verdict": verdict,
        "first_adversarial_divergence": divergence,
        "golden_invariants": golden_invariants,
        "distractor_invariants": distractor_invariants,
        "false_supported_forensics": false_supported_forensics,
    }
    tc4 = {
        "golden_event_id": GOLDEN_EVENT_ID,
        "golden": golden_ledger,
        "supported_distractors": false_supported_forensics,
    }
    return metrics, grade, tc4


def _scenario_manifest(spec: ScenarioSpec, items: Iterable[Mapping[str, Any]], order: Iterable[int]) -> dict[str, Any]:
    values = list(items)
    indexed = {int(item["ordinal"]): item for item in values}
    return {
        "scenario_version": SCENARIO_VERSION,
        "scenario_id": spec.scenario_id,
        "distractor_count": spec.distractor_count,
        "insertion_order_seed": spec.order_seed,
        "insertion_ordinals": list(order),
        "product_inputs_in_insertion_order": [
            indexed[ordinal]["product_input"] for ordinal in order
        ],
        "evaluator_ground_truth": {
            "golden_event_id": GOLDEN_EVENT_ID,
            "controls": [item["ground_truth"] for item in values],
            "labels_visible_to_product": False,
        },
    }


def run_scenario(seed_db: Path, output_root: Path, spec: ScenarioSpec) -> dict[str, Any]:
    items = distractor_set(spec.distractor_count)
    validate_distractor_contract(items)
    order = insertion_permutation(spec.distractor_count, spec.order_seed)
    scenario_dir = output_root / spec.relative_directory
    database_path = scenario_dir / "topo-product.db"
    copy_receipt = copy_seed_database(seed_db, database_path)
    input_manifest = _scenario_manifest(spec, items, order)
    write_json(scenario_dir / "scenario-input.json", input_manifest)

    engine = _scenario_engine(database_path)
    try:
        _ensure_backend_import_path()
        from sqlalchemy.orm import Session
        from app.models.causal_rca import CausalAnalysisRequest
        from app.services.causal_rca import analyze_causal_rca

        with Session(engine) as session:
            inserted_ids = ingest_distractors(session, items, order)
            database_hash_before_analysis = sha256_file(database_path)
            analysis = analyze_causal_rca(
                session,
                tenant_id=DISPOSABLE_EVALUATION_TENANT_ID,
                incident_id=GOLDEN_INCIDENT_ID,
                request=CausalAnalysisRequest(),
                persist=True,
            )
            metrics, grade, tc4 = grade_analysis(session, analysis, items)
            analysis_payload = analysis.model_dump(mode="json")
    finally:
        engine.dispose()

    database_hash_after_analysis = sha256_file(database_path)
    metrics = {
        "scenario_id": spec.scenario_id,
        "insertion_order_seed": spec.order_seed,
        "inserted_event_ids": inserted_ids,
        "database_copy": {
            **copy_receipt,
            "sha256_before_analysis": database_hash_before_analysis,
            "sha256_after_analysis": database_hash_after_analysis,
        },
        **metrics,
    }
    write_json(scenario_dir / "analysis.json", analysis_payload)
    write_json(
        scenario_dir / "candidate-audit.json",
        analysis_payload.get("candidate_selection_audit", []),
    )
    write_json(
        scenario_dir / "relevance-audit.json",
        analysis_payload.get("candidate_relevance_audit", []),
    )
    write_json(scenario_dir / "tc4-summary.json", tc4)
    write_json(scenario_dir / "grade.json", grade)
    write_json(scenario_dir / "metrics.json", metrics)
    return {"spec": spec, "metrics": metrics, "grade": grade, "directory": scenario_dir}


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": (numerator / denominator) if denominator else None,
    }


def aggregate_results(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(results)
    valid = [item for item in values if item["grade"]["scenario_valid"]]
    invalid = [item for item in values if not item["grade"]["scenario_valid"]]
    total = len(valid)
    groups: dict[int, list[Mapping[str, Any]]] = {}
    for item in valid:
        count = int(item["metrics"]["distractor_count"])
        if count:
            groups.setdefault(count, []).append(item)
    order_sensitive_counts: list[int] = []
    deterministic_id_sensitive_counts: list[int] = []
    for count, group in groups.items():
        supported_signatures = {
            deterministic_json_bytes(
                {
                    "supported_top1": item["metrics"]["supported_top1"],
                    "supported_top3": item["metrics"]["supported_top3"],
                    "golden_supported_rank": item["metrics"]["golden_supported_rank"],
                    "false_supported": item["metrics"]["false_supported_distractor_ids"],
                }
            )
            for item in group
        }
        analysis_id_hashes = {
            (
                item["metrics"]["analysis_id"],
                item["metrics"]["analysis_normalized_sha256"],
            )
            for item in group
        }
        if len(supported_signatures) > 1:
            order_sensitive_counts.append(count)
        if len(analysis_id_hashes) > 1:
            deterministic_id_sensitive_counts.append(count)

    divergence_candidates = [
        item
        for divergence in FIRST_DIVERGENCE_ORDER[:-2]
        for item in valid
        if item["grade"]["first_adversarial_divergence"] == divergence
    ]
    if divergence_candidates:
        first_failure = min(
            divergence_candidates,
            key=lambda item: (
                FIRST_DIVERGENCE_ORDER.index(
                    item["grade"]["first_adversarial_divergence"]
                ),
                item["metrics"]["distractor_count"],
                item["metrics"]["insertion_order_seed"],
            ),
        )
        first_divergence = first_failure["grade"]["first_adversarial_divergence"]
    elif order_sensitive_counts:
        first_divergence = "ORDER_DEPENDENT_SUPPORTED_RESULT"
        failing_count = min(order_sensitive_counts)
        first_failure = min(
            groups[failing_count], key=lambda item: item["metrics"]["insertion_order_seed"]
        )
    else:
        evidence_failure = next(
            (
                item
                for item in valid
                if not item["metrics"]["golden_evidence_complete"]
            ),
            None,
        )
        if evidence_failure is not None:
            first_divergence = "GOLDEN_EVIDENCE_CHAIN_DEGRADED"
            first_failure = evidence_failure
        else:
            first_divergence = "NO_DIVERGENCE"
            first_failure = None

    false_supported_total = sum(
        int(item["metrics"]["false_supported_distractor_count"]) for item in valid
    )
    distractor_opportunities = sum(
        int(item["metrics"]["distractor_count"]) for item in valid
    )
    false_supported_scenarios = sum(
        int(item["metrics"]["false_supported_distractor_count"] > 0)
        for item in valid
    )
    aggregate = {
        "scenario_version": SCENARIO_VERSION,
        "definitions": {
            "supported_top1_flip": "supported Top1 event ID is not the golden causal event ID, including no supported Top1",
            "supported_top3_retained": "golden causal event ID appears in the evidence-supported Top3",
            "raw_top1_flip": "raw candidate Top1 event ID is not the golden causal event ID",
            "raw_top3_retained": "golden causal event ID appears in raw candidate Top3",
            "false_supported_candidate": "an evaluator-controlled noncausal event appears as a product hypothesis with evidence_state=supported_under_current_model",
            "order_sensitive_scenario": "the same count/set yields different supported Top1, Top3, golden rank, or false-supported set across insertion orders",
        },
        "run_count": len(values),
        "valid_run_count": len(valid),
        "invalid_run_count": len(invalid),
        "invalid_scenario_ids": [item["metrics"]["scenario_id"] for item in invalid],
        "supported_top1_flip_rate": _rate(
            sum(item["metrics"]["supported_top1"] != GOLDEN_EVENT_ID for item in valid),
            total,
        ),
        "supported_top3_retention_rate": _rate(
            sum(GOLDEN_EVENT_ID in item["metrics"]["supported_top3"] for item in valid),
            total,
        ),
        "raw_top1_flip_rate": _rate(
            sum(item["metrics"]["raw_top1"] != GOLDEN_EVENT_ID for item in valid),
            total,
        ),
        "raw_top3_retention_rate": _rate(
            sum(GOLDEN_EVENT_ID in item["metrics"]["raw_top3"] for item in valid),
            total,
        ),
        "false_supported_candidate_rate": _rate(
            false_supported_total,
            distractor_opportunities,
        ),
        "false_supported_scenario_rate": _rate(
            false_supported_scenarios,
            total,
        ),
        "golden_candidate_admission_stability": _rate(
            sum(item["metrics"]["golden_admitted"] for item in valid),
            total,
        ),
        "golden_relevance_stability": _rate(
            sum(item["metrics"]["golden_relevance_supported"] for item in valid),
            total,
        ),
        "evidence_completeness_stability": _rate(
            sum(item["metrics"]["golden_evidence_complete"] for item in valid),
            total,
        ),
        "order_sensitivity_rate": _rate(len(order_sensitive_counts), len(groups)),
        "order_sensitive_counts": sorted(order_sensitive_counts),
        "analysis_id_or_hash_order_sensitive_counts": sorted(
            deterministic_id_sensitive_counts
        ),
        "golden_raw_rank_range": _rank_range(valid, "golden_raw_rank"),
        "golden_supported_rank_range": _rank_range(valid, "golden_supported_rank"),
        "false_supported_distractor_count": false_supported_total,
        "false_supported_scenario_count": false_supported_scenarios,
        "first_adversarial_divergence": first_divergence,
        "first_failing_scenario": (
            {
                "scenario_id": first_failure["metrics"]["scenario_id"],
                "count": first_failure["metrics"]["distractor_count"],
                "order_seed": first_failure["metrics"]["insertion_order_seed"],
                "distractor_ids": first_failure["metrics"]["inserted_event_ids"],
                "grade": first_failure["grade"],
            }
            if first_failure is not None
            else None
        ),
    }
    aggregate["release_gate_observations"] = {
        "supported_top1_flip_rate_zero": aggregate["supported_top1_flip_rate"]["rate"] == 0,
        "supported_top3_retention_100_percent": aggregate["supported_top3_retention_rate"]["rate"] == 1,
        "false_supported_candidates_zero": false_supported_total == 0,
        "golden_admission_stability_100_percent": aggregate["golden_candidate_admission_stability"]["rate"] == 1,
        "golden_relevance_stability_100_percent": aggregate["golden_relevance_stability"]["rate"] == 1,
        "evidence_completeness_stability_100_percent": aggregate["evidence_completeness_stability"]["rate"] == 1,
        "order_sensitivity_zero": aggregate["order_sensitivity_rate"]["rate"] == 0,
    }
    aggregate["final_adversarial_verdict"] = (
        "INCONCLUSIVE"
        if invalid
        else "ROBUST_IN_MEASURED_MATRIX"
        if first_divergence == "NO_DIVERGENCE"
        else "ADVERSARIAL_DIVERGENCE_FOUND"
    )
    aggregate["runs"] = [
        {
            "scenario_id": item["metrics"]["scenario_id"],
            "count": item["metrics"]["distractor_count"],
            "order_seed": item["metrics"]["insertion_order_seed"],
            "raw_top1": item["metrics"]["raw_top1"],
            "raw_top3": item["metrics"]["raw_top3"],
            "golden_raw_rank": item["metrics"]["golden_raw_rank"],
            "supported_top1": item["metrics"]["supported_top1"],
            "supported_top3": item["metrics"]["supported_top3"],
            "golden_supported_rank": item["metrics"]["golden_supported_rank"],
            "false_supported_count": item["metrics"]["false_supported_distractor_count"],
            "divergence": item["grade"]["first_adversarial_divergence"],
            "verdict": item["metrics"]["final_verdict"],
            "analysis_id": item["metrics"]["analysis_id"],
            "analysis_normalized_sha256": item["metrics"]["analysis_normalized_sha256"],
        }
        for item in valid
    ]
    return aggregate


def _rank_range(values: Iterable[Mapping[str, Any]], field: str) -> dict[str, Any]:
    ranks = [
        int(item["metrics"][field])
        for item in values
        if item["metrics"][field] is not None
    ]
    return {
        "minimum": min(ranks) if ranks else None,
        "maximum": max(ranks) if ranks else None,
        "observed_count": len(ranks),
    }


def _safe_reset_output_root(output_root: Path) -> None:
    resolved = output_root.resolve()
    allowed_parent = (
        ROOT / "evaluation/results/lineage/adversarial"
    ).resolve()
    if resolved.parent != allowed_parent or resolved.name != "lineage-2a-distractors":
        raise ValueError("Refusing to replace an output path outside the exact LINEAGE-2A root.")
    if resolved.exists():
        shutil.rmtree(resolved)


def artifact_hashes(output_root: Path) -> dict[str, str]:
    return {
        path.relative_to(output_root).as_posix(): sha256_file(path)
        for path in sorted(output_root.rglob("*.json"))
    }


def run_matrix(
    *,
    seed_db: Path = DEFAULT_SEED_DB,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    replace_output: bool = False,
) -> dict[str, Any]:
    seed_db = seed_db.resolve()
    output_root = output_root.resolve()
    seed_receipt = validate_seed_database(seed_db)
    if output_root.exists():
        if not replace_output:
            raise FileExistsError(
                f"Output root already exists; pass --replace-output to replace it: {output_root}"
            )
        _safe_reset_output_root(output_root)
    output_root.mkdir(parents=True, exist_ok=False)
    root_manifest = {
        "scenario_version": SCENARIO_VERSION,
        "accepted_main_commit": ACCEPTED_MAIN_COMMIT,
        "golden_product_commit": GOLDEN_PRODUCT_COMMIT,
        "seed": seed_receipt,
        "counts": list(DISTRACTOR_COUNTS),
        "nonzero_insertion_order_seeds": list(INSERTION_ORDER_SEEDS),
        "expected_run_count": len(scenario_specs()),
        "ordinary_path_a_minutes": LOOKBACK_MINUTES,
        "distractor_timing": "integer-second linear distribution from 5 through 175 minutes before the incident boundary",
        "provider_calls": False,
        "kubernetes_execution": False,
        "llm_or_embeddings": False,
        "existing_evaluator_semantics_modified": False,
    }
    write_json(output_root / "manifest.json", root_manifest)
    results = [run_scenario(seed_db, output_root, spec) for spec in scenario_specs()]
    aggregate = aggregate_results(results)
    aggregate["seed_post_run"] = validate_seed_database(seed_db)
    write_json(output_root / "aggregate.json", aggregate)
    hashes = artifact_hashes(output_root)
    write_json(output_root / "artifact-hashes.json", hashes)
    return {
        "manifest": root_manifest,
        "aggregate": aggregate,
        "artifact_hashes": hashes,
        "output_root": output_root.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the offline LINEAGE-2A temporal distractor matrix."
    )
    parser.add_argument("--seed-db", type=Path, default=DEFAULT_SEED_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--replace-output", action="store_true")
    arguments = parser.parse_args()
    result = run_matrix(
        seed_db=arguments.seed_db,
        output_root=arguments.output_root,
        replace_output=arguments.replace_output,
    )
    aggregate = result["aggregate"]
    print(
        f"{aggregate['final_adversarial_verdict']}: "
        f"{aggregate['run_count']} runs -> {result['output_root']}"
    )
    print(f"first divergence: {aggregate['first_adversarial_divergence']}")
    return 0 if aggregate["final_adversarial_verdict"] != "INCONCLUSIVE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
