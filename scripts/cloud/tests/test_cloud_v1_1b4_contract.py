from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
TERRAFORM_DIR = ROOT / "infrastructure/aws/golden"
TLS_PATH = TERRAFORM_DIR / "tls.tf"
EDGE_PATH = TERRAFORM_DIR / "edge.tf"
VARIABLES_PATH = TERRAFORM_DIR / "variables.tf"
OUTPUTS_PATH = TERRAFORM_DIR / "outputs.tf"
FOUNDATION_PATH = ROOT / "infrastructure/kubernetes/golden/foundation.yaml"
DOCUMENT_PATH = ROOT / "docs/architecture/cloud-v1-1b4-acm-https-v1.md"


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


def _terraform_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(TERRAFORM_DIR.glob("*.tf"))
    )


class CloudV1AcmHttpsContractTests(unittest.TestCase):
    def test_certificate_request_is_exact_single_name_dns_validated_and_unconditional(self) -> None:
        source = TLS_PATH.read_text(encoding="utf-8")
        certificate = _hcl_block(source, 'resource "aws_acm_certificate" "edge"')

        self.assertEqual(len(re.findall(r'resource\s+"aws_acm_certificate"\s+"', source)), 1)
        self.assertIn('domain_name       = "app.topoai.io"', certificate)
        self.assertIn('validation_method = "DNS"', certificate)
        self.assertIn('key_algorithm     = "RSA_2048"', certificate)
        self.assertIn('certificate_transparency_logging_preference = "ENABLED"', certificate)
        self.assertIn("create_before_destroy = true", certificate)
        self.assertNotIn("subject_alternative_names", certificate)
        self.assertNotIn("count", certificate)
        self.assertNotIn("for_each", certificate)
        for forbidden in ('"topoai.io"', '"www.topoai.io"', '"api.topoai.io"', "*."):
            self.assertNotIn(forbidden, certificate)

    def test_https_gate_defaults_false_and_controls_waiter_listener_and_ingress(self) -> None:
        variables = VARIABLES_PATH.read_text(encoding="utf-8")
        tls = TLS_PATH.read_text(encoding="utf-8")
        variable = _hcl_block(variables, 'variable "edge_https_enabled"')
        validation = _hcl_block(
            tls,
            'resource "aws_acm_certificate_validation" "edge"',
        )
        ingress = _hcl_block(
            tls,
            'resource "aws_vpc_security_group_ingress_rule" "edge_alb_https_validation"',
        )
        listener = _hcl_block(tls, 'resource "aws_lb_listener" "edge_https"')

        self.assertIn("type        = bool", variable)
        self.assertIn("default     = false", variable)
        self.assertIn("count = var.edge_https_enabled ? 1 : 0", validation)
        self.assertIn("certificate_arn = aws_acm_certificate.edge.arn", validation)
        self.assertIn(
            "for_each = var.edge_https_enabled ? toset(var.edge_validation_ipv4_cidrs) : toset([])",
            ingress,
        )
        self.assertIn("cidr_ipv4         = each.value", ingress)
        self.assertIn("from_port         = 443", ingress)
        self.assertIn("to_port           = 443", ingress)
        self.assertIn("count = var.edge_https_enabled ? 1 : 0", listener)

    def test_https_listener_uses_issued_certificate_and_exact_tls_policy(self) -> None:
        source = TLS_PATH.read_text(encoding="utf-8")
        listener = _hcl_block(source, 'resource "aws_lb_listener" "edge_https"')

        self.assertIn("port              = 443", listener)
        self.assertIn('protocol          = "HTTPS"', listener)
        self.assertIn("ssl_policy        = local.edge_tls_policy", listener)
        self.assertIn(
            "certificate_arn   = aws_acm_certificate_validation.edge[0].certificate_arn",
            listener,
        )
        self.assertIn(
            'edge_tls_policy            = "ELBSecurityPolicy-TLS13-1-2-RFC9151-INTEROP4-FIPS-2023-07"',
            source,
        )
        self.assertNotIn("certificate_arn   = aws_acm_certificate.edge.arn", listener)

    def test_https_routes_match_accepted_http_routing(self) -> None:
        source = TLS_PATH.read_text(encoding="utf-8")
        expected = {
            "edge_https_backend_api": (100, "/api/*"),
            "edge_https_backend_health": (110, "/health"),
            "edge_https_backend_ready": (120, "/ready"),
        }

        for name, (priority, path) in expected.items():
            rule = _hcl_block(source, f'resource "aws_lb_listener_rule" "{name}"')
            self.assertIn("count = var.edge_https_enabled ? 1 : 0", rule)
            self.assertIn("listener_arn = aws_lb_listener.edge_https[0].arn", rule)
            self.assertIn(f"priority     = {priority}", rule)
            self.assertIn(f'values = ["{path}"]', rule)
            self.assertIn("target_group_arn = aws_lb_target_group.edge_backend.arn", rule)
            self.assertIn("create_before_destroy = true", rule)

    def test_http_resources_keep_addresses_and_become_redirect_only_when_enabled(self) -> None:
        source = EDGE_PATH.read_text(encoding="utf-8")
        resources = [
            _hcl_block(source, 'resource "aws_lb_listener" "edge_http"'),
            _hcl_block(source, 'resource "aws_lb_listener_rule" "edge_backend_api"'),
            _hcl_block(source, 'resource "aws_lb_listener_rule" "edge_backend_health"'),
            _hcl_block(source, 'resource "aws_lb_listener_rule" "edge_backend_ready"'),
        ]

        for block in resources:
            resource_arguments = block.split('dynamic "', maxsplit=1)[0]
            self.assertNotRegex(resource_arguments, r"(?m)^\s*(?:count|for_each)\s*=")
            self.assertIn("var.edge_https_enabled ? [] : [true]", block)
            self.assertIn("var.edge_https_enabled ? [true] : []", block)
            self.assertIn('type = "redirect"', block)
            self.assertIn('host        = "#{host}"', block)
            self.assertIn('path        = "/#{path}"', block)
            self.assertIn('query       = "#{query}"', block)
            self.assertIn('port        = "443"', block)
            self.assertIn('protocol    = "HTTPS"', block)
            self.assertIn('status_code = "HTTP_301"', block)

    def test_tls_output_preserves_exact_provider_validation_record(self) -> None:
        source = OUTPUTS_PATH.read_text(encoding="utf-8")
        tls = TLS_PATH.read_text(encoding="utf-8")
        output = _hcl_block(source, 'output "tls"')

        self.assertIn("one(aws_acm_certificate.edge.domain_validation_options)", tls)
        for expected in (
            "aws_acm_certificate.edge.arn",
            "aws_acm_certificate.edge.domain_name",
            "aws_acm_certificate.edge.status",
            "local.edge_acm_validation_record.resource_record_name",
            "local.edge_acm_validation_record.resource_record_type",
            "local.edge_acm_validation_record.resource_record_value",
            "var.edge_https_enabled",
            "local.edge_tls_policy",
        ):
            self.assertIn(expected, output)
        for field in (
            "validation_record_name",
            "validation_record_type",
            "validation_record_value",
        ):
            self.assertIn(field, output)
        self.assertNotRegex(output.casefold(), r"password|credential|token|secret")

    def test_existing_edge_output_and_worker_boundary_remain_compatible(self) -> None:
        outputs = OUTPUTS_PATH.read_text(encoding="utf-8")
        edge = EDGE_PATH.read_text(encoding="utf-8")
        edge_output = _hcl_block(outputs, 'output "edge"')
        alb_egress = _hcl_block(
            edge,
            'resource "aws_vpc_security_group_egress_rule" "edge_alb_to_workers"',
        )
        worker_ingress = _hcl_block(
            edge,
            'resource "aws_vpc_security_group_ingress_rule" "edge_workers_from_alb"',
        )

        self.assertIn("listener_arn = aws_lb_listener.edge_http.arn", edge_output)
        self.assertIn("node_ports   = local.edge_node_ports", edge_output)
        self.assertIn("backend  = 32080", edge)
        self.assertIn("frontend = 32081", edge)
        for block in (alb_egress, worker_ingress):
            self.assertIn("for_each = local.edge_node_ports", block)
            self.assertIn("referenced_security_group_id", block)
            self.assertNotIn("cidr_ipv4", block)

    def test_no_dns_waf_cloudfront_or_public_cidr_authority_is_added(self) -> None:
        source = _terraform_source()
        edge_boundary = "\n".join(
            (EDGE_PATH.read_text(encoding="utf-8"), TLS_PATH.read_text(encoding="utf-8"))
        )

        for forbidden in ("aws_route53_", "aws_wafv2_", "aws_cloudfront_"):
            self.assertNotRegex(source, rf'resource\s+"{forbidden}')
        self.assertNotRegex(
            edge_boundary,
            r'cidr_ipv[46]\s*=\s*"(?:0\.0\.0\.0/0|::/0)"',
        )
        self.assertNotIn("aws_acm_certificate.edge.domain_validation_options[*]", source)
        self.assertNotIn("www.topoai.io", source)
        self.assertNotIn("api.topoai.io", source)
        self.assertNotRegex(source.casefold(), r'provider\s+"porkbun"')
        self.assertNotRegex(source.casefold(), r"porkbun_(?:api|secret|token|credential)")

    def test_browser_origin_remains_unpublished(self) -> None:
        documents = [
            item
            for item in yaml.safe_load_all(FOUNDATION_PATH.read_text(encoding="utf-8"))
            if isinstance(item, dict)
        ]
        config_map = next(
            item
            for item in documents
            if item.get("kind") == "ConfigMap"
            and item.get("metadata", {}).get("name") == "topo-runtime-config"
        )

        self.assertEqual(config_map["data"]["browser-allowed-origins-json"], "[]")

    def test_document_defines_staged_external_dns_and_controlled_tls_acceptance(self) -> None:
        document = DOCUMENT_PATH.read_text(encoding="utf-8")

        for expected in (
            "a51574057cd6151c6ecaa0b71914ce33ce949b41",
            "297361542190",
            "topo-golden-edge-823808315.us-east-1.elb.amazonaws.com",
            "Porkbun",
            "ACM validation CNAME",
            "edge_https_enabled = false",
            "edge_https_enabled = true",
            "ELBSecurityPolicy-TLS13-1-2-RFC9151-INTEROP4-FIPS-2023-07",
            "curl.exe --connect-to",
            "HTTP_301",
            "No human credentials",
            "must not be published",
            "CLOUD-V1-1B.5",
            "CLOUD-V1-1B.6",
            "Rollback",
        ):
            self.assertIn(expected, document)


if __name__ == "__main__":
    unittest.main()
