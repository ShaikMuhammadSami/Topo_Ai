from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
KUBERNETES_DIR = ROOT / "infrastructure/kubernetes/golden"
EDGE_MANIFEST_PATH = KUBERNETES_DIR / "edge-services.yaml"
BACKEND_MANIFEST_PATH = KUBERNETES_DIR / "backend.yaml"
FRONTEND_MANIFEST_PATH = KUBERNETES_DIR / "frontend.yaml"
FOUNDATION_MANIFEST_PATH = KUBERNETES_DIR / "foundation.yaml"
TERRAFORM_DIR = ROOT / "infrastructure/aws/golden"
EDGE_TERRAFORM_PATH = TERRAFORM_DIR / "edge.tf"
VARIABLES_PATH = TERRAFORM_DIR / "variables.tf"
OUTPUTS_PATH = TERRAFORM_DIR / "outputs.tf"
DOCUMENT_PATH = ROOT / "docs/architecture/cloud-v1-1b3-public-edge-v1.md"


def _documents(path: Path) -> list[dict[str, Any]]:
    return [
        document
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if isinstance(document, dict)
    ]


def _all_kubernetes_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in sorted(KUBERNETES_DIR.glob("*.yaml")):
        documents.extend(_documents(path))
    return documents


def _resource(documents: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    matches = [
        document
        for document in documents
        if document.get("kind") == kind
        and document.get("metadata", {}).get("name") == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}/{name}; found {len(matches)}")
    return matches[0]


def _hcl_block(source: str, header: str) -> str:
    start = source.find(header)
    if start < 0:
        raise AssertionError(f"Missing HCL block: {header}")
    brace = source.find("{", start + len(header))
    if brace < 0:
        raise AssertionError(f"Missing opening brace for HCL block: {header}")

    depth = 0
    in_string = False
    escaped = False
    for index in range(brace, len(source)):
        character = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Unclosed HCL block: {header}")


class CloudV1PublicEdgeContractTests(unittest.TestCase):
    def test_nodeport_services_are_additive_exact_and_private_worker_facing(self) -> None:
        edge_documents = _documents(EDGE_MANIFEST_PATH)
        expected = {
            "topo-backend-edge": {
                "selector": {
                    "app.kubernetes.io/name": "topo-backend",
                    "app.kubernetes.io/component": "api",
                },
                "nodePort": 32080,
            },
            "topo-frontend": {
                "selector": {
                    "app.kubernetes.io/name": "topo-frontend",
                    "app.kubernetes.io/component": "web",
                },
                "nodePort": 32081,
            },
        }

        self.assertEqual(len(edge_documents), 2)
        for name, contract in expected.items():
            service = _resource(edge_documents, "Service", name)
            spec = service["spec"]
            self.assertEqual(service["metadata"]["namespace"], "topo-system")
            self.assertEqual(spec["type"], "NodePort")
            self.assertEqual(spec["externalTrafficPolicy"], "Cluster")
            self.assertEqual(spec["selector"], contract["selector"])
            self.assertEqual(
                spec["ports"],
                [
                    {
                        "name": "http",
                        "port": 80,
                        "targetPort": "http",
                        "nodePort": contract["nodePort"],
                        "protocol": "TCP",
                    }
                ],
            )
            self.assertNotIn("externalIPs", spec)
            self.assertNotIn("loadBalancerIP", spec)
            self.assertFalse(service["metadata"].get("annotations"))

    def test_existing_private_services_remain_clusterip_contracts(self) -> None:
        backend = _resource(_documents(BACKEND_MANIFEST_PATH), "Service", "topo-backend")
        frontend = _resource(
            _documents(FRONTEND_MANIFEST_PATH),
            "Service",
            "topo-frontend-internal",
        )

        self.assertEqual(backend["spec"], {
            "type": "ClusterIP",
            "selector": {
                "app.kubernetes.io/name": "topo-backend",
                "app.kubernetes.io/component": "api",
            },
            "ports": [
                {"name": "http", "port": 80, "targetPort": "http", "protocol": "TCP"}
            ],
        })
        self.assertEqual(frontend["spec"], {
            "type": "ClusterIP",
            "selector": {
                "app.kubernetes.io/name": "topo-frontend",
                "app.kubernetes.io/component": "web",
            },
            "ports": [
                {"name": "http", "port": 80, "targetPort": "http", "protocol": "TCP"}
            ],
        })

    def test_kubernetes_source_has_no_ingress_loadbalancer_or_controller(self) -> None:
        documents = _all_kubernetes_documents()
        services = [document for document in documents if document.get("kind") == "Service"]

        self.assertFalse(any(document.get("kind") == "Ingress" for document in documents))
        self.assertFalse(any(service["spec"].get("type") == "LoadBalancer" for service in services))
        serialized = yaml.safe_dump(documents, sort_keys=True).casefold()
        self.assertNotIn("aws-load-balancer-controller", serialized)
        self.assertNotIn("service.beta.kubernetes.io/aws-load-balancer", serialized)

    def test_alb_and_target_groups_use_existing_vpc_and_public_subnets(self) -> None:
        source = EDGE_TERRAFORM_PATH.read_text(encoding="utf-8")
        alb = _hcl_block(source, 'resource "aws_lb" "edge"')
        backend = _hcl_block(source, 'resource "aws_lb_target_group" "edge_backend"')
        frontend = _hcl_block(source, 'resource "aws_lb_target_group" "edge_frontend"')

        self.assertIn("internal           = false", alb)
        self.assertIn('load_balancer_type = "application"', alb)
        self.assertIn('ip_address_type    = "ipv4"', alb)
        self.assertIn("aws_security_group.edge_alb.id", alb)
        self.assertIn(
            "[for az in local.availability_zones : aws_subnet.public[az].id]",
            alb,
        )
        for block, port, path in (
            (backend, "local.edge_node_ports.backend", "/ready"),
            (frontend, "local.edge_node_ports.frontend", "/healthz"),
        ):
            self.assertIn(f"port        = {port}", block)
            self.assertIn('protocol    = "HTTP"', block)
            self.assertIn('target_type = "instance"', block)
            self.assertIn("vpc_id      = aws_vpc.golden.id", block)
            self.assertIn('port                = "traffic-port"', block)
            self.assertIn(f'path                = "{path}"', block)
            self.assertIn('matcher             = "200"', block)

    def test_validation_ingress_and_sg_to_sg_nodeport_rules_are_bounded(self) -> None:
        edge = EDGE_TERRAFORM_PATH.read_text(encoding="utf-8")
        variables = VARIABLES_PATH.read_text(encoding="utf-8")
        variable = _hcl_block(variables, 'variable "edge_validation_ipv4_cidrs"')
        ingress = _hcl_block(
            edge,
            'resource "aws_vpc_security_group_ingress_rule" "edge_alb_http_validation"',
        )
        egress = _hcl_block(
            edge,
            'resource "aws_vpc_security_group_egress_rule" "edge_alb_to_workers"',
        )
        worker_ingress = _hcl_block(
            edge,
            'resource "aws_vpc_security_group_ingress_rule" "edge_workers_from_alb"',
        )

        self.assertIn("type        = list(string)", variable)
        self.assertIn("default     = []", variable)
        self.assertIn('cidr != "0.0.0.0/0"', variable)
        self.assertIn("can(cidrnetmask(cidr))", variable)
        self.assertIn('endswith(cidr, "/32")', variable)
        self.assertIn("toset(var.edge_validation_ipv4_cidrs)", ingress)
        self.assertIn("cidr_ipv4         = each.value", ingress)
        self.assertIn("from_port         = 80", ingress)
        self.assertIn("to_port           = 80", ingress)
        self.assertNotRegex(edge, r'cidr_ipv[46]\s*=\s*"(?:0\.0\.0\.0/0|::/0)"')

        for block in (egress, worker_ingress):
            self.assertIn("for_each = local.edge_node_ports", block)
            self.assertIn("from_port", block)
            self.assertIn("each.value", block)
            self.assertIn("to_port", block)
        self.assertIn("security_group_id            = aws_security_group.edge_alb.id", egress)
        self.assertIn("referenced_security_group_id = aws_security_group.eks_nodes.id", egress)
        self.assertIn("security_group_id            = aws_security_group.eks_nodes.id", worker_ingress)
        self.assertIn("referenced_security_group_id = aws_security_group.edge_alb.id", worker_ingress)
        self.assertNotIn("cidr_ipv4", egress)
        self.assertNotIn("cidr_ipv4", worker_ingress)

    def test_managed_node_group_asgs_form_the_four_attachment_matrix(self) -> None:
        source = EDGE_TERRAFORM_PATH.read_text(encoding="utf-8")
        attachment = _hcl_block(source, 'resource "aws_autoscaling_attachment" "edge"')

        self.assertIn(
            "setproduct(local.availability_zones, keys(local.edge_target_group_arns))",
            source,
        )
        self.assertIn("for_each = local.edge_asg_target_group_attachments", attachment)
        self.assertIn("aws_eks_node_group.golden[each.value.availability_zone]", attachment)
        self.assertIn("resources[0].autoscaling_groups[0].name", attachment)
        self.assertIn("local.edge_target_group_arns[each.value.target_group]", attachment)
        self.assertNotRegex(source, r"\bi-[0-9a-f]{8,17}\b")
        self.assertNotIn("eks-topo-golden-us-east-1a", source)
        self.assertNotIn("eks-topo-golden-us-east-1b", source)

    def test_http_listener_routes_backend_explicitly_and_frontend_by_default(self) -> None:
        source = EDGE_TERRAFORM_PATH.read_text(encoding="utf-8")
        listener = _hcl_block(source, 'resource "aws_lb_listener" "edge_http"')
        expected_rules = {
            "edge_backend_api": (100, "/api/*"),
            "edge_backend_health": (110, "/health"),
            "edge_backend_ready": (120, "/ready"),
        }

        self.assertIn("port              = 80", listener)
        self.assertIn('protocol          = "HTTP"', listener)
        self.assertIn("aws_lb_target_group.edge_frontend.arn", listener)
        self.assertIn("var.edge_https_enabled ? [] : [true]", listener)
        for name, (priority, path) in expected_rules.items():
            rule = _hcl_block(source, f'resource "aws_lb_listener_rule" "{name}"')
            self.assertIn(f"priority     = {priority}", rule)
            self.assertIn(f'values = ["{path}"]', rule)
            self.assertIn("aws_lb_target_group.edge_backend.arn", rule)
            self.assertNotIn("host_header", rule)

    def test_output_is_stable_non_secret_and_later_block_oriented(self) -> None:
        source = OUTPUTS_PATH.read_text(encoding="utf-8")
        output = _hcl_block(source, 'output "edge"')

        for expected in (
            "aws_lb.edge.arn",
            "aws_lb.edge.dns_name",
            "aws_lb.edge.zone_id",
            "aws_security_group.edge_alb.id",
            "aws_lb_target_group.edge_backend.arn",
            "aws_lb_target_group.edge_frontend.arn",
            "aws_lb_listener.edge_http.arn",
            "local.edge_node_ports",
        ):
            self.assertIn(expected, output)
        self.assertNotRegex(output.casefold(), r"password|credential|token|secret")

    def test_no_tls_waf_dns_browser_origin_or_secret_authority_is_added(self) -> None:
        # Later blocks may add TLS in separate files. The accepted 1B.3 source
        # itself must remain free of certificate, DNS, and WAF authority.
        terraform = EDGE_TERRAFORM_PATH.read_text(encoding="utf-8")
        edge_documents = _documents(EDGE_MANIFEST_PATH)
        foundation = _resource(
            _documents(FOUNDATION_MANIFEST_PATH),
            "ConfigMap",
            "topo-runtime-config",
        )

        for forbidden_resource_prefix in (
            "aws_acm_",
            "aws_wafv2_",
            "aws_route53_",
            "aws_cloudfront_",
        ):
            self.assertNotRegex(
                terraform,
                rf'resource\s+"{forbidden_resource_prefix}',
            )
        self.assertNotIn("app.topoai.io", terraform)
        self.assertNotIn("api.topoai.io", terraform)
        self.assertEqual(foundation["data"]["browser-allowed-origins-json"], "[]")

        serialized = yaml.safe_dump(edge_documents, sort_keys=True)
        for forbidden in (
            "secretKeyRef",
            "configMapKeyRef",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "NEXT_PUBLIC",
            "TOPO_BACKEND_URL",
            "credential",
        ):
            self.assertNotIn(forbidden.casefold(), serialized.casefold())

    def test_document_records_preflight_handoffs_rollback_and_live_acceptance(self) -> None:
        document = DOCUMENT_PATH.read_text(encoding="utf-8")

        for expected in (
            "67fdd719d88803b23a43879ef6f3485420e7431c",
            "vpc-00dc74e72bd7f0129",
            "sg-071e1b40296d57288",
            "32080",
            "32081",
            "edge_validation_ipv4_cidrs",
            "203.0.113.10/32",
            "private workers",
            "instance",
            "four",
            "No human credential",
            "CLOUD-V1-1B.4",
            "CLOUD-V1-1B.5",
            "CLOUD-V1-1B.6",
            "Rollback",
            "No live resource was changed",
        ):
            self.assertIn(expected, document)


if __name__ == "__main__":
    unittest.main()
