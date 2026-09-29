"""Emit only hash-gated, sanitized metadata from the accepted local state.

The Terraform state is secret-bearing input.  This helper has no arbitrary
path argument, verifies the complete file fingerprint before parsing, and
never emits state JSON, attributes, outputs, variables, provider data, or
resource values.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


EXPECTED_SHA256 = "b3321648facd8506f322b7f91ad3ad04dd8b1a017ba89124c5f382e4abd48994"
EXPECTED_RESOURCE_COUNT = 80
STATE_PATH = Path(__file__).resolve().parents[3] / "infrastructure/aws/golden/terraform.tfstate"
REPRESENTATIVE_ADDRESSES = (
    "aws_vpc.golden",
    "aws_eks_cluster.golden",
    "aws_db_instance.postgres",
    "aws_lb.edge",
    "aws_ecr_repository.topo",
)

_LINEAGE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_TERRAFORM_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_MODULE_ADDRESS = re.compile(r'^(?:module\.[A-Za-z0-9_-]+(?:\[(?:[0-9]+|"[^"\\]*")\])?\.?)+$')


class InspectionError(RuntimeError):
    """Fail-closed local-state inspection error."""


def _safe_top_level(state: Any, name: str, expected_type: type) -> Any:
    if not isinstance(state, dict) or name not in state or not isinstance(state[name], expected_type):
        raise InspectionError(f"STOP: local state {name} metadata is invalid")
    return state[name]


def _instance_address(resource: dict[str, Any], instance: dict[str, Any]) -> str:
    mode = resource.get("mode")
    resource_type = resource.get("type")
    name = resource.get("name")
    module = resource.get("module")
    if mode not in {"managed", "data"}:
        raise InspectionError("STOP: local state resource mode is invalid")
    if not isinstance(resource_type, str) or not _IDENTIFIER.fullmatch(resource_type):
        raise InspectionError("STOP: local state resource type metadata is invalid")
    if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
        raise InspectionError("STOP: local state resource name metadata is invalid")
    if module is not None and (not isinstance(module, str) or not _MODULE_ADDRESS.fullmatch(f"{module}.")):
        raise InspectionError("STOP: local state module metadata is invalid")

    prefix = f"{module}." if module else ""
    data_prefix = "data." if mode == "data" else ""
    address = f"{prefix}{data_prefix}{resource_type}.{name}"
    index = instance.get("index_key")
    if index is None:
        return address
    if isinstance(index, bool) or not isinstance(index, (str, int)):
        raise InspectionError("STOP: local state instance index metadata is invalid")
    if isinstance(index, str):
        return f"{address}[{json.dumps(index, ensure_ascii=True, separators=(',', ':'))}]"
    return f"{address}[{index}]"


def inspect_state_bytes(payload: bytes, expected_sha256: str = EXPECTED_SHA256) -> dict[str, Any]:
    fingerprint = hashlib.sha256(payload).hexdigest()
    if fingerprint != expected_sha256:
        raise InspectionError("STOP: local state fingerprint differs from accepted authority")

    try:
        state = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InspectionError("STOP: accepted local state is not valid JSON") from error

    state_format_version = _safe_top_level(state, "version", int)
    terraform_version = _safe_top_level(state, "terraform_version", str)
    lineage = _safe_top_level(state, "lineage", str)
    serial = _safe_top_level(state, "serial", int)
    resources = _safe_top_level(state, "resources", list)

    if isinstance(state_format_version, bool) or state_format_version < 1:
        raise InspectionError("STOP: local state format version is invalid")
    if not _TERRAFORM_VERSION.fullmatch(terraform_version):
        raise InspectionError("STOP: local state Terraform version metadata is invalid")
    if not _LINEAGE.fullmatch(lineage):
        raise InspectionError("STOP: local state lineage metadata is invalid")
    if isinstance(serial, bool) or serial < 0:
        raise InspectionError("STOP: local state serial metadata is invalid")

    address_count = 0
    representatives = {address: False for address in REPRESENTATIVE_ADDRESSES}
    for resource in resources:
        if not isinstance(resource, dict):
            raise InspectionError("STOP: local state resource metadata is invalid")
        instances = resource.get("instances")
        if not isinstance(instances, list):
            raise InspectionError("STOP: local state instance metadata is invalid")
        for instance in instances:
            if not isinstance(instance, dict):
                raise InspectionError("STOP: local state instance metadata is invalid")
            address = _instance_address(resource, instance)
            address_count += 1
            if address in representatives:
                representatives[address] = True

    return {
        "state_format_version": state_format_version,
        "terraform_version": terraform_version,
        "lineage": lineage.lower(),
        "serial": serial,
        "resource_address_count": address_count,
        "representative_addresses_present": representatives,
        "all_representative_addresses_present": all(representatives.values()),
        "local_state_sha256": fingerprint,
        "local_state_size_bytes": len(payload),
        "state_payload_read_in_memory": True,
        "raw_state_emitted": False,
        "resource_attributes_emitted": False,
        "outputs_emitted": False,
    }


def inspect_accepted_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        raise InspectionError("STOP: approved local state file is absent")
    # A single bounded in-memory read is hashed before JSON parsing.
    payload = STATE_PATH.read_bytes()
    result = inspect_state_bytes(payload)
    if result["resource_address_count"] != EXPECTED_RESOURCE_COUNT:
        raise InspectionError("STOP: accepted local state resource count differs")
    if not result["all_representative_addresses_present"]:
        raise InspectionError("STOP: accepted representative resource identity is incomplete")
    return result


def main() -> int:
    try:
        print(json.dumps(inspect_accepted_state(), indent=2, sort_keys=True))
        return 0
    except InspectionError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
