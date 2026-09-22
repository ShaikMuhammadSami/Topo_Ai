locals {
  edge_tls_policy            = "ELBSecurityPolicy-TLS13-1-2-RFC9151-INTEROP4-FIPS-2023-07"
  edge_acm_validation_record = one(aws_acm_certificate.edge.domain_validation_options)
}

resource "aws_acm_certificate" "edge" {
  domain_name       = "app.topoai.io"
  validation_method = "DNS"
  key_algorithm     = "RSA_2048"

  options {
    certificate_transparency_logging_preference = "ENABLED"
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${local.name}-edge"
  }
}

# Porkbun remains authoritative for DNS. This waiter is enabled only after the
# exact ACM validation CNAME from the output.tls validation fields is added.
resource "aws_acm_certificate_validation" "edge" {
  count = var.edge_https_enabled ? 1 : 0

  certificate_arn = aws_acm_certificate.edge.arn
}

resource "aws_vpc_security_group_ingress_rule" "edge_alb_https_validation" {
  for_each = var.edge_https_enabled ? toset(var.edge_validation_ipv4_cidrs) : toset([])

  security_group_id = aws_security_group.edge_alb.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "Temporary operator-controlled HTTPS validation"
}

resource "aws_lb_listener" "edge_https" {
  count = var.edge_https_enabled ? 1 : 0

  load_balancer_arn = aws_lb.edge.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = local.edge_tls_policy
  certificate_arn   = aws_acm_certificate_validation.edge[0].certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.edge_frontend.arn
  }
}

resource "aws_lb_listener_rule" "edge_https_backend_api" {
  count = var.edge_https_enabled ? 1 : 0

  listener_arn = aws_lb_listener.edge_https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.edge_backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_listener_rule" "edge_https_backend_health" {
  count = var.edge_https_enabled ? 1 : 0

  listener_arn = aws_lb_listener.edge_https[0].arn
  priority     = 110

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.edge_backend.arn
  }

  condition {
    path_pattern {
      values = ["/health"]
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_lb_listener_rule" "edge_https_backend_ready" {
  count = var.edge_https_enabled ? 1 : 0

  listener_arn = aws_lb_listener.edge_https[0].arn
  priority     = 120

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.edge_backend.arn
  }

  condition {
    path_pattern {
      values = ["/ready"]
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}
