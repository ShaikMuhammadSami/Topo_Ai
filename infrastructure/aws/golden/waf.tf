locals {
  edge_waf_log_group_name = "aws-waf-logs-${local.name}-edge"

  edge_waf_managed_rule_groups = {
    common = {
      name        = "AWSManagedRulesCommonRuleSet"
      priority    = 10
      metric_name = "${local.name}-edge-common"
    }
    known_bad_inputs = {
      name        = "AWSManagedRulesKnownBadInputsRuleSet"
      priority    = 20
      metric_name = "${local.name}-edge-known-bad-inputs"
    }
    ip_reputation = {
      name        = "AWSManagedRulesAmazonIpReputationList"
      priority    = 30
      metric_name = "${local.name}-edge-ip-reputation"
    }
  }

  edge_public_listener_ports = {
    http  = 80
    https = 443
  }
}

resource "aws_cloudwatch_log_group" "edge_waf" {
  count = var.edge_waf_enabled ? 1 : 0

  name              = local.edge_waf_log_group_name
  retention_in_days = 30

  tags = {
    Name = local.edge_waf_log_group_name
  }
}

resource "aws_wafv2_web_acl" "edge" {
  count = var.edge_waf_enabled ? 1 : 0

  name        = "${local.name}-edge"
  description = "TopoAI regional public-edge defense in depth"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "BlockOversizeBodyOutsideProviderCallbacks"
    priority = 5

    action {
      block {}
    }

    statement {
      and_statement {
        statement {
          size_constraint_statement {
            comparison_operator = "GT"
            size                = 8192

            field_to_match {
              body {
                oversize_handling = "MATCH"
              }
            }

            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }

        statement {
          not_statement {
            statement {
              byte_match_statement {
                positional_constraint = "STARTS_WITH"
                search_string         = "/api/v1/change-source-webhooks/"

                field_to_match {
                  uri_path {}
                }

                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.name}-edge-non-provider-oversize-body"
      sampled_requests_enabled   = false
    }
  }

  dynamic "rule" {
    for_each = local.edge_waf_managed_rule_groups

    content {
      name     = rule.value.name
      priority = rule.value.priority

      override_action {
        dynamic "count" {
          for_each = var.edge_waf_mode == "count" ? [true] : []
          content {}
        }

        dynamic "none" {
          for_each = var.edge_waf_mode == "block" ? [true] : []
          content {}
        }
      }

      statement {
        managed_rule_group_statement {
          name        = rule.value.name
          vendor_name = "AWS"

          dynamic "rule_action_override" {
            for_each = rule.value.name == "AWSManagedRulesCommonRuleSet" ? [true] : []

            content {
              name = "SizeRestrictions_BODY"

              action_to_use {
                count {}
              }
            }
          }
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = rule.value.metric_name
        sampled_requests_enabled   = false
      }
    }
  }

  rule {
    name     = "SourceIpRateLimit"
    priority = 100

    action {
      dynamic "count" {
        for_each = var.edge_waf_mode == "count" ? [true] : []
        content {}
      }

      dynamic "block" {
        for_each = var.edge_waf_mode == "block" ? [true] : []
        content {}
      }
    }

    statement {
      rate_based_statement {
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300
        limit                 = var.edge_waf_rate_limit
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.name}-edge-source-ip-rate"
      sampled_requests_enabled   = false
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.name}-edge"
    sampled_requests_enabled   = false
  }
}

resource "aws_wafv2_web_acl_association" "edge" {
  count = var.edge_waf_enabled ? 1 : 0

  resource_arn = aws_lb.edge.arn
  web_acl_arn  = aws_wafv2_web_acl.edge[0].arn
}

resource "aws_wafv2_web_acl_logging_configuration" "edge" {
  count = var.edge_waf_enabled ? 1 : 0

  resource_arn            = aws_wafv2_web_acl.edge[0].arn
  log_destination_configs = [aws_cloudwatch_log_group.edge_waf[0].arn]

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }

  redacted_fields {
    single_header {
      name = "x-topo-csrf"
    }
  }

  redacted_fields {
    single_header {
      name = "x-hub-signature-256"
    }
  }

  redacted_fields {
    single_header {
      name = "x-gitlab-token"
    }
  }

  redacted_fields {
    single_header {
      name = "webhook-signature"
    }
  }

  redacted_fields {
    single_header {
      name = "x-tfe-notification-signature"
    }
  }

  redacted_fields {
    single_header {
      name = "x-topo-signature-256"
    }
  }

  logging_filter {
    default_behavior = "DROP"

    filter {
      behavior    = "KEEP"
      requirement = "MEETS_ANY"

      condition {
        action_condition {
          action = "COUNT"
        }
      }

      condition {
        action_condition {
          action = "BLOCK"
        }
      }
    }
  }
}

resource "aws_vpc_security_group_ingress_rule" "edge_alb_public" {
  for_each = var.edge_public_ingress_enabled ? local.edge_public_listener_ports : {}

  security_group_id = aws_security_group.edge_alb.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = each.value
  to_port           = each.value
  description       = "Public ${upper(each.key)} listener after WAF block-mode acceptance"
}
