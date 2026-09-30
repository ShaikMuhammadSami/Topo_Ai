"""Build and compare a secret-safe Kubernetes reconstruction contract.

Only source-owned Deployment and Service fields are compared. Runtime identity,
status, and controller-generated metadata are intentionally outside this
contract. Secret and ConfigMap references are retained, but their values are
never loaded or emitted.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


SAFE_LABEL_PREFIXES = ("app.kubernetes.io/", "topo.ai/")
LITERAL_ENV_ALLOWLIST = {
    "TOPO_AUTH_MODE",
    "TOPO_SECRET_STORE_BACKEND",
    "TOPO_SECRET_KEYRING_FILE",
    "TOPO_BACKEND_URL",
    "TOPO_AGENT_NAME",
    "TOPO_ENABLED_PLUGINS",
    "TOPO_CHANGE_WATCH_KUBERNETES",
    "TOPO_CHANGE_WATCH_AWS",
    "TOPO_CHANGE_WATCH_AZURE",
    "TOPO_CHANGE_WATCH_GCP",
    "TOPO_COLLECTION_INTERVAL",
    "TOPO_CHANGE_WATCH_INTERVAL",
    "TOPO_HEARTBEAT_INTERVAL",
    "TOPO_AGENT_HOME",
    "TMPDIR",
}
BACKEND_IMAGE_PLACEHOLDER = (
    "example.invalid/topo-backend@sha256:"
    + "0" * 64
)
RUNTIME_FIELDS_EXCLUDED = (
    "uid",
    "resourceVersion",
    "managedFields",
    "creationTimestamp",
    "generation",
    "status",
    "observedGeneration",
    "pod names and UIDs",
    "ReplicaSet-generated names and hashes",
    "restart counts",
    "node assignment",
    "ephemeral runtime conditions",
)
REPRODUCTION_CRITICAL_FIELDS = (
    "namespace",
    "workload kind and name",
    "replica intent",
    "safe source labels and declared annotation keys",
    "selectors and strategy",
    "container and init-container names",
    "immutable image references",
    "commands, arguments, ports, resources, and probes",
    "allowlisted literal environment values",
    "Secret and ConfigMap references without values",
    "service account identity",
    "volume and volume-mount references",
    "service identity, type, selectors, traffic policy, and ports",
)


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata or {}
    labels = {
        str(key): str(value)
        for key, value in sorted((metadata.get("labels") or {}).items())
        if str(key).startswith(SAFE_LABEL_PREFIXES)
    }
    result: dict[str, Any] = {
        "name": str(metadata.get("name") or ""),
        "namespace": str(metadata.get("namespace") or ""),
        "labels": labels,
    }
    annotations = metadata.get("annotations") or {}
    if annotations:
        result["annotation_keys"] = sorted(str(key) for key in annotations)
    return result


def _reference(value_from: dict[str, Any] | None) -> dict[str, Any] | None:
    for kind in ("configMapKeyRef", "secretKeyRef", "fieldRef", "resourceFieldRef"):
        candidate = (value_from or {}).get(kind)
        if candidate is not None:
            return {
                "kind": kind,
                "name": candidate.get("name"),
                "key": candidate.get("key"),
                "field_path": candidate.get("fieldPath"),
            }
    return None


def _environment(entry: dict[str, Any]) -> dict[str, Any]:
    name = str(entry.get("name") or "")
    literal_present = "value" in entry
    return {
        "name": name,
        "value_from": _reference(entry.get("valueFrom")),
        "literal_env_value_present": literal_present,
        "allowlisted_literal_value": (
            str(entry.get("value") or "")
            if literal_present and name in LITERAL_ENV_ALLOWLIST
            else None
        ),
    }


def _container(container: dict[str, Any], backend_image: str) -> dict[str, Any]:
    image = container.get("image")
    if image == BACKEND_IMAGE_PLACEHOLDER:
        image = backend_image
    return {
        "name": container.get("name"),
        "image": image,
        "command": list(container.get("command") or []),
        "args": list(container.get("args") or []),
        "ports": sorted(
            (
                {
                    "name": port.get("name"),
                    "container_port": port.get("containerPort"),
                    "protocol": port.get("protocol"),
                }
                for port in container.get("ports") or []
            ),
            key=lambda item: str(item.get("name") or ""),
        ),
        "env": sorted(
            (_environment(entry) for entry in container.get("env") or []),
            key=lambda item: item["name"],
        ),
        "resources": container.get("resources") or {},
        "startup_probe": container.get("startupProbe"),
        "liveness_probe": container.get("livenessProbe"),
        "readiness_probe": container.get("readinessProbe"),
        "volume_mounts": sorted(
            (
                {
                    "name": mount.get("name"),
                    "mount_path": mount.get("mountPath"),
                    "read_only": bool(mount.get("readOnly", False)),
                }
                for mount in container.get("volumeMounts") or []
            ),
            key=lambda item: str(item.get("name") or ""),
        ),
    }


def _volume(volume: dict[str, Any]) -> dict[str, Any]:
    kind = "unknown"
    reference: Any = None
    for candidate in ("secret", "configMap", "emptyDir", "persistentVolumeClaim", "projected", "hostPath"):
        value = volume.get(candidate)
        if value is None:
            continue
        kind = candidate
        if candidate == "secret":
            reference = value.get("secretName")
        elif candidate == "configMap":
            reference = value.get("name")
        elif candidate == "persistentVolumeClaim":
            reference = value.get("claimName")
        elif candidate == "emptyDir":
            reference = {
                "medium": value.get("medium") or None,
                "size_limit": value.get("sizeLimit") or None,
            }
        break
    return {"name": volume.get("name"), "type": kind, "reference": reference}


def _pod_template(template: dict[str, Any] | None, backend_image: str) -> dict[str, Any]:
    template = template or {}
    spec = template.get("spec") or {}
    return {
        "labels": _safe_metadata(template.get("metadata"))["labels"],
        "service_account_name": spec.get("serviceAccountName"),
        "containers": sorted(
            (_container(item, backend_image) for item in spec.get("containers") or []),
            key=lambda item: str(item.get("name") or ""),
        ),
        "init_containers": sorted(
            (_container(item, backend_image) for item in spec.get("initContainers") or []),
            key=lambda item: str(item.get("name") or ""),
        ),
        "volumes": sorted(
            (_volume(item) for item in spec.get("volumes") or []),
            key=lambda item: str(item.get("name") or ""),
        ),
    }


def _deployment(document: dict[str, Any], backend_image: str) -> dict[str, Any]:
    spec = document.get("spec") or {}
    return {
        "kind": "Deployment",
        "metadata": _safe_metadata(document.get("metadata")),
        "replicas": spec.get("replicas"),
        "selector": spec.get("selector"),
        "strategy": spec.get("strategy"),
        "pod_template": _pod_template(spec.get("template"), backend_image),
    }


def _service(document: dict[str, Any]) -> dict[str, Any]:
    spec = document.get("spec") or {}
    return {
        "kind": "Service",
        "metadata": _safe_metadata(document.get("metadata")),
        "type": spec.get("type"),
        "selector": spec.get("selector"),
        "external_traffic_policy": spec.get("externalTrafficPolicy"),
        "ports": sorted(
            (
                {
                    "name": port.get("name"),
                    "protocol": port.get("protocol"),
                    "port": port.get("port"),
                    "target_port": port.get("targetPort"),
                    "node_port": port.get("nodePort"),
                }
                for port in spec.get("ports") or []
            ),
            key=lambda item: str(item.get("name") or ""),
        ),
    }


def load_source_contract(manifest_root: Path, backend_image: str) -> dict[str, Any]:
    deployments: list[dict[str, Any]] = []
    services: list[dict[str, Any]] = []
    for path in sorted(manifest_root.glob("*.yaml")):
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if not isinstance(document, dict):
                continue
            kind = document.get("kind")
            if kind == "Deployment":
                deployments.append(_deployment(document, backend_image))
            elif kind == "Service":
                services.append(_service(document))
    return {
        "schema_version": "cx0.kubernetes-source-contract.v1",
        "deployments": sorted(deployments, key=_identity_sort_key),
        "services": sorted(services, key=_identity_sort_key),
        "runtime_generated_fields_excluded": list(RUNTIME_FIELDS_EXCLUDED),
        "reproduction_critical_fields_compared": list(REPRODUCTION_CRITICAL_FIELDS),
        "secret_values_emitted": False,
    }


def _identity_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    metadata = item.get("metadata") or {}
    return (
        str(item.get("kind") or ""),
        str(metadata.get("namespace") or ""),
        str(metadata.get("name") or ""),
    )


def _normalize_live_item(kind: str, item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["kind"] = kind
    if kind == "Service" and normalized.get("external_traffic_policy") == "":
        normalized["external_traffic_policy"] = None
    for volume in ((normalized.get("pod_template") or {}).get("volumes") or []):
        if volume.get("type") == "emptyDir" and isinstance(volume.get("reference"), dict):
            volume["reference"]["medium"] = volume["reference"].get("medium") or None
            volume["reference"]["size_limit"] = volume["reference"].get("size_limit") or None
    return normalized


def _missing_required(item: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    metadata = item.get("metadata") or {}
    for name, value in (
        ("kind", item.get("kind")),
        ("metadata.namespace", metadata.get("namespace")),
        ("metadata.name", metadata.get("name")),
    ):
        if value is None or str(value).strip() == "":
            missing.append(name)
    if item.get("kind") == "Deployment":
        if item.get("replicas") is None:
            missing.append("replicas")
        for group in ("containers", "init_containers"):
            for index, container in enumerate((item.get("pod_template") or {}).get(group) or []):
                if not container.get("name"):
                    missing.append(f"pod_template.{group}[{index}].name")
                if not container.get("image"):
                    missing.append(f"pod_template.{group}[{index}].image")
    return missing


def _compare_subset(source: Any, live: Any, path: str, differences: list[str]) -> None:
    if isinstance(source, dict):
        if not isinstance(live, dict):
            differences.append(path)
            return
        for key, source_value in source.items():
            child = f"{path}.{key}" if path else key
            if key not in live:
                differences.append(child)
            else:
                _compare_subset(source_value, live[key], child, differences)
        return
    if isinstance(source, list):
        if not isinstance(live, list):
            differences.append(path)
            return
        if all(isinstance(item, dict) and item.get("name") is not None for item in source):
            live_by_name = {
                str(item.get("name")): item
                for item in live
                if isinstance(item, dict) and item.get("name") is not None
            }
            if len(live_by_name) != len(live):
                differences.append(path)
                return
            source_names = {str(item.get("name")) for item in source}
            if source_names != set(live_by_name):
                differences.append(path)
                return
            for item in source:
                name = str(item.get("name"))
                _compare_subset(item, live_by_name[name], f"{path}[name={name}]", differences)
            return
        if len(source) != len(live):
            differences.append(path)
            return
        for index, source_value in enumerate(source):
            _compare_subset(source_value, live[index], f"{path}[{index}]", differences)
        return
    if source != live:
        differences.append(path)


def compare_contracts(source: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    source_items = [
        *source.get("deployments", []),
        *source.get("services", []),
    ]
    live_items = [
        *(_normalize_live_item("Deployment", item) for item in live.get("deployments", [])),
        *(_normalize_live_item("Service", item) for item in live.get("services", [])),
    ]
    source_map = {_identity_sort_key(item): item for item in source_items}
    live_map = {_identity_sort_key(item): item for item in live_items}
    unresolved: list[str] = []
    for key, item in sorted(source_map.items()):
        unresolved.extend(f"{key}:{field}" for field in _missing_required(item))
    for key, item in sorted(live_map.items()):
        unresolved.extend(f"{key}:{field}" for field in _missing_required(item))
    live_only = sorted("/".join(key) for key in set(live_map) - set(source_map))
    source_only = sorted("/".join(key) for key in set(source_map) - set(live_map))
    differences: list[str] = []
    for key in sorted(set(source_map) & set(live_map)):
        _compare_subset(source_map[key], live_map[key], "/".join(key), differences)

    if unresolved:
        classification = "UNKNOWN_REQUIRED"
    elif live_only:
        classification = "LIVE_ONLY_REQUIRED"
    elif source_only or differences:
        classification = "CODIFIED_DIFFERENTLY"
    else:
        classification = "MATCH"
    return {
        "schema_version": "cx0.kubernetes-reconciliation.v1",
        "classification": classification,
        "source_object_count": len(source_map),
        "live_object_count": len(live_map),
        "difference_paths": sorted(set(differences)),
        "source_only_objects": source_only,
        "live_only_required_objects": live_only,
        "unresolved_required_paths": sorted(set(unresolved)),
        "runtime_generated_fields_excluded": list(RUNTIME_FIELDS_EXCLUDED),
        "reproduction_critical_fields_compared": list(REPRODUCTION_CRITICAL_FIELDS),
        "secret_values_emitted": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    source = subparsers.add_parser("source")
    source.add_argument("--manifest-root", type=Path, required=True)
    source.add_argument("--backend-image", required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--inventory", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "source":
        result = load_source_contract(args.manifest_root, args.backend_image)
    else:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        kubernetes = inventory.get("kubernetes") or {}
        result = compare_contracts(
            kubernetes.get("source_contract") or {},
            {
                "deployments": kubernetes.get("deployments") or [],
                "services": kubernetes.get("services") or [],
            },
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
