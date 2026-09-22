from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
TERRAFORM_DIR = ROOT / "infrastructure/aws/golden"
WAF_PATH = TERRAFORM_DIR / "waf.tf"
EDGE_PATH = TERRAFORM_DIR / "edge.tf"
TLS_PATH = TERRAFORM_DIR / "tls.tf"
VARIABLES_PATH = TERRAFORM_DIR / "variables.tf"
OUTPUTS_PATH = TERRAFORM_DIR / "outputs.tf"
FOUNDATION_PATH = ROOT / "infrastructure/kubernetes/golden/foundation.yaml"
SESSION_AUTH_PATH = ROOT / "backend/app/security/session_auth.py"
SYSTEM_API_PATH = ROOT / "backend/app/api/system.py"
CHANGE_SOURCE_WEBHOOK_PATH = ROOT / "backend/app/api/change_source_webhooks.py"
CHANGE_SOURCE_INGEST_PATH = ROOT / "backend/app/services/change_source_ingest.py"
DOCUMENT_PATH = ROOT / "docs/architecture/cloud-v1-1b5-waf-public-edge-hardening-v1.md"


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


class CloudV1WafPublicEdgeContractTests(unittest.TestCase):
    def test_controls_have_safe_defaults_and_bounded_rate_validation(self) -> None:
        source = VARIABLES_PATH.read_text(encoding="utf-8")
        expected = {
            "edge_waf_enabled": ("bool", "false"),
            "edge_waf_mode": ("string", '"count"'),
            "edge_public_ingress_enabled": ("bool", "false"),
            "edge_waf_rate_limit": ("number", "2000"),
        }
        for name, (kind, default) in expected.items():
            block = _hcl_block(source, f'variable "{name}"')
            self.assertIn(f"type        = {kind}", block)
            self.assertIn(f"default     = {default}", block)

        mode = _hcl_block(source, 'variable "edge_waf_mode"')
        rate = _hcl_block(source, 'variable "edge_waf_rate_limit"')
        self.assertIn('contains(["count", "block"], var.edge_waf_mode)', mode)
        self.assertIn("var.edge_waf_rate_limit == floor(var.edge_waf_rate_limit)", rate)
        self.assertIn("var.edge_waf_rate_limit >= 100", rate)
        self.assertIn("var.edge_waf_rate_limit <= 2000000", rate)

    def test_regional_acl_has_exact_managed_groups_and_deterministic_priorities(self) -> None:
        source = WAF_PATH.read_text(encoding="utf-8")
        acl = _hcl_block(source, 'resource "aws_wafv2_web_acl" "edge"')

        self.assertIn("count = var.edge_waf_enabled ? 1 : 0", acl)
        self.assertIn('scope       = "REGIONAL"', acl)
        self.assertRegex(acl, r"default_action\s*\{\s*allow\s*\{\}\s*\}")
        self.assertIn("for_each = local.edge_waf_managed_rule_groups", acl)
        self.assertIn('vendor_name = "AWS"', acl)
        for name, priority in (
            ("AWSManagedRulesCommonRuleSet", 10),
            ("AWSManagedRulesKnownBadInputsRuleSet", 20),
            ("AWSManagedRulesAmazonIpReputationList", 30),
        ):
            self.assertIn(f'name        = "{name}"', source)
            self.assertIn(f"priority    = {priority}", source)

    def test_count_and_block_modes_cover_managed_and_rate_rules(self) -> None:
        acl = _hcl_block(
            WAF_PATH.read_text(encoding="utf-8"),
            'resource "aws_wafv2_web_acl" "edge"',
        )
        self.assertIn('dynamic "count"', acl)
        self.assertIn('dynamic "none"', acl)
        self.assertIn('dynamic "block"', acl)
        self.assertGreaterEqual(
            acl.count('var.edge_waf_mode == "count" ? [true] : []'),
            2,
        )
        self.assertIn('var.edge_waf_mode == "block" ? [true] : []', acl)
        self.assertIn('name     = "SourceIpRateLimit"', acl)
        self.assertIn("priority = 100", acl)
        self.assertIn('aggregate_key_type    = "IP"', acl)
        self.assertIn("evaluation_window_sec = 300", acl)
        self.assertIn("limit                 = var.edge_waf_rate_limit", acl)
        self.assertNotIn("FORWARDED_IP", acl)
        self.assertNotIn("X-Forwarded-For", acl)

    def test_metrics_disable_samples_for_acl_wrappers_and_rate_rule(self) -> None:
        acl = _hcl_block(
            WAF_PATH.read_text(encoding="utf-8"),
            'resource "aws_wafv2_web_acl" "edge"',
        )
        self.assertEqual(acl.count("visibility_config {"), 3)
        self.assertEqual(acl.count("cloudwatch_metrics_enabled = true"), 3)
        self.assertEqual(acl.count("sampled_requests_enabled   = false"), 3)
        for metric in (
            "edge-common",
            "edge-known-bad-inputs",
            "edge-ip-reputation",
            "edge-source-ip-rate",
        ):
            self.assertIn(metric, WAF_PATH.read_text(encoding="utf-8"))

    def test_logging_is_finite_filtered_and_redacts_real_sensitive_headers(self) -> None:
        source = WAF_PATH.read_text(encoding="utf-8")
        log_group = _hcl_block(source, 'resource "aws_cloudwatch_log_group" "edge_waf"')
        logging = _hcl_block(
            source,
            'resource "aws_wafv2_web_acl_logging_configuration" "edge"',
        )
        session_auth = SESSION_AUTH_PATH.read_text(encoding="utf-8")
        change_source_ingest = CHANGE_SOURCE_INGEST_PATH.read_text(encoding="utf-8")

        self.assertIn('edge_waf_log_group_name = "aws-waf-logs-${local.name}-edge"', source)
        self.assertIn("retention_in_days = 30", log_group)
        self.assertIn("aws_cloudwatch_log_group.edge_waf[0].arn", logging)
        for header in (
            "authorization",
            "cookie",
            "x-topo-csrf",
            "x-hub-signature-256",
            "x-gitlab-token",
            "webhook-signature",
            "x-tfe-notification-signature",
            "x-topo-signature-256",
        ):
            self.assertIn(f'name = "{header}"', logging)
        self.assertIn('CSRF_HEADER_NAME = "X-Topo-CSRF"', session_auth)
        for webhook_header in (
            '"x-hub-signature-256"',
            '"x-gitlab-token"',
            '"webhook-signature"',
            '"x-tfe-notification-signature"',
            '"x-topo-signature-256"',
        ):
            self.assertIn(webhook_header, change_source_ingest)
        self.assertIn('default_behavior = "DROP"', logging)
        self.assertIn('behavior    = "KEEP"', logging)
        self.assertIn('action = "COUNT"', logging)
        self.assertIn('action = "BLOCK"', logging)

    def test_association_is_exactly_the_existing_alb(self) -> None:
        source = WAF_PATH.read_text(encoding="utf-8")
        association = _hcl_block(
            source,
            'resource "aws_wafv2_web_acl_association" "edge"',
        )
        self.assertEqual(
            len(re.findall(r'resource\s+"aws_wafv2_web_acl_association"', source)),
            1,
        )
        self.assertIn("count = var.edge_waf_enabled ? 1 : 0", association)
        self.assertIn("resource_arn = aws_lb.edge.arn", association)
        self.assertIn("web_acl_arn  = aws_wafv2_web_acl.edge[0].arn", association)

    def test_public_ingress_is_guarded_and_limited_to_alb_ports_80_and_443(self) -> None:
        waf = WAF_PATH.read_text(encoding="utf-8")
        edge = EDGE_PATH.read_text(encoding="utf-8")
        tls = TLS_PATH.read_text(encoding="utf-8")
        security_group = _hcl_block(edge, 'resource "aws_security_group" "edge_alb"')
        http_validation = _hcl_block(
            edge,
            'resource "aws_vpc_security_group_ingress_rule" "edge_alb_http_validation"',
        )
        https_validation = _hcl_block(
            tls,
            'resource "aws_vpc_security_group_ingress_rule" "edge_alb_https_validation"',
        )
        public = _hcl_block(
            waf,
            'resource "aws_vpc_security_group_ingress_rule" "edge_alb_public"',
        )

        self.assertIn("!var.edge_public_ingress_enabled", security_group)
        self.assertIn("var.edge_https_enabled", security_group)
        self.assertIn("var.edge_waf_enabled", security_group)
        self.assertIn('var.edge_waf_mode == "block"', security_group)
        self.assertIn("precondition", security_group)
        self.assertIn("var.edge_public_ingress_enabled ? toset([])", http_validation)
        self.assertIn("!var.edge_public_ingress_enabled", https_validation)
        self.assertIn("http  = 80", waf)
        self.assertIn("https = 443", waf)
        self.assertIn("var.edge_public_ingress_enabled ? local.edge_public_listener_ports : {}", public)
        self.assertIn('cidr_ipv4         = "0.0.0.0/0"', public)
        self.assertNotIn("::/0", waf)

    def test_worker_nodeport_rds_and_listener_authority_are_unchanged(self) -> None:
        edge = EDGE_PATH.read_text(encoding="utf-8")
        tls = TLS_PATH.read_text(encoding="utf-8")
        waf = WAF_PATH.read_text(encoding="utf-8")
        egress = _hcl_block(
            edge,
            'resource "aws_vpc_security_group_egress_rule" "edge_alb_to_workers"',
        )
        worker = _hcl_block(
            edge,
            'resource "aws_vpc_security_group_ingress_rule" "edge_workers_from_alb"',
        )
        https = _hcl_block(tls, 'resource "aws_lb_listener" "edge_https"')

        self.assertIn("for_each = local.edge_node_ports", egress)
        self.assertIn("for_each = local.edge_node_ports", worker)
        self.assertIn("referenced_security_group_id", egress)
        self.assertIn("referenced_security_group_id", worker)
        self.assertNotIn("cidr_ipv4", egress)
        self.assertNotIn("cidr_ipv4", worker)
        self.assertIn("backend  = 32080", edge)
        self.assertIn("frontend = 32081", edge)
        self.assertNotIn("authenticate_", https)
        self.assertNotRegex(waf, r"aws_db_|aws_eks_|aws_lb_target_group")

    def test_output_is_bounded_non_secret_operational_metadata(self) -> None:
        output = _hcl_block(
            OUTPUTS_PATH.read_text(encoding="utf-8"),
            'output "edge_protection"',
        )
        for field in (
            "enabled",
            "mode",
            "web_acl_arn",
            "web_acl_name",
            "association_target_arn",
            "rate_limit",
            "evaluation_window_seconds",
            "log_group_name",
            "public_ingress_enabled",
        ):
            self.assertIn(field, output)
        self.assertNotRegex(
            output.casefold(),
            r"request_sample|authorization|cookie|csrf|credential|token|password",
        )

    def test_dns_browser_auth_and_webhook_boundaries_remain_explicit(self) -> None:
        terraform = _terraform_source()
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
        system_api = SYSTEM_API_PATH.read_text(encoding="utf-8")
        change_webhook = CHANGE_SOURCE_WEBHOOK_PATH.read_text(encoding="utf-8")

        for forbidden in ("aws_route53_", "aws_cloudfront_"):
            self.assertNotRegex(terraform, rf'resource\s+"{forbidden}')
        self.assertNotIn("api.topoai.io", terraform)
        self.assertEqual(config_map["data"]["browser-allowed-origins-json"], "[]")
        self.assertIn("status_code=401", system_api)
        self.assertIn("load_change_source_for_authentication", change_webhook)
        self.assertIn("WebhookAuthenticationError", change_webhook)

    def test_document_records_staged_acceptance_and_prohibitions(self) -> None:
        document = DOCUMENT_PATH.read_text(encoding="utf-8")
        for expected in (
            "b160dc52c85c3c1767abca641242a5e10a336a71",
            "AWSManagedRulesCommonRuleSet",
            "AWSManagedRulesKnownBadInputsRuleSet",
            "AWSManagedRulesAmazonIpReputationList",
            "COUNT",
            "BLOCK",
            "2,000 requests",
            "X-Topo-CSRF",
            "edge_public_ingress_enabled",
            "0.0.0.0/0",
            "app.topoai.io application DNS remains absent",
            "No human credentials",
            "webhook",
            "deferred",
            "CLOUD-V1-1B.6",
            "Rollback",
        ):
            self.assertIn(expected, document)


if __name__ == "__main__":
    unittest.main()
