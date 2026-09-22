locals {
  edge_node_ports = {
    backend  = 32080
    frontend = 32081
  }

  edge_target_group_arns = {
    backend  = aws_lb_target_group.edge_backend.arn
    frontend = aws_lb_target_group.edge_frontend.arn
  }

  edge_asg_target_group_attachments = {
    for pair in setproduct(local.availability_zones, keys(local.edge_target_group_arns)) :
    "${pair[0]}:${pair[1]}" => {
      availability_zone = pair[0]
      target_group      = pair[1]
    }
  }
}

resource "aws_security_group" "edge_alb" {
  name        = "${local.name}-edge-alb"
  description = "TopoAI controlled pre-publication ALB boundary"
  vpc_id      = aws_vpc.golden.id

  tags = {
    Name = "${local.name}-edge-alb"
  }
}

resource "aws_vpc_security_group_ingress_rule" "edge_alb_http_validation" {
  for_each = toset(var.edge_validation_ipv4_cidrs)

  security_group_id = aws_security_group.edge_alb.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  description       = "Temporary operator-controlled HTTP validation"
}

resource "aws_vpc_security_group_egress_rule" "edge_alb_to_workers" {
  for_each = local.edge_node_ports

  security_group_id            = aws_security_group.edge_alb.id
  referenced_security_group_id = aws_security_group.eks_nodes.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
  description                  = "ALB to ${each.key} NodePort"
}

resource "aws_vpc_security_group_ingress_rule" "edge_workers_from_alb" {
  for_each = local.edge_node_ports

  security_group_id            = aws_security_group.eks_nodes.id
  referenced_security_group_id = aws_security_group.edge_alb.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
  description                  = "ALB to ${each.key} NodePort"
}

resource "aws_lb" "edge" {
  name               = "${local.name}-edge"
  internal           = false
  load_balancer_type = "application"
  ip_address_type    = "ipv4"
  security_groups    = [aws_security_group.edge_alb.id]
  subnets            = [for az in local.availability_zones : aws_subnet.public[az].id]

  drop_invalid_header_fields = true
  enable_deletion_protection = false
  enable_http2               = true

  tags = {
    Name = "${local.name}-edge"
  }
}

resource "aws_lb_target_group" "edge_backend" {
  name        = "${local.name}-backend"
  port        = local.edge_node_ports.backend
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = aws_vpc.golden.id

  deregistration_delay = 30

  health_check {
    enabled             = true
    protocol            = "HTTP"
    port                = "traffic-port"
    path                = "/ready"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }

  tags = {
    Name = "${local.name}-backend"
  }
}

resource "aws_lb_target_group" "edge_frontend" {
  name        = "${local.name}-frontend"
  port        = local.edge_node_ports.frontend
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = aws_vpc.golden.id

  deregistration_delay = 30

  health_check {
    enabled             = true
    protocol            = "HTTP"
    port                = "traffic-port"
    path                = "/healthz"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }

  tags = {
    Name = "${local.name}-frontend"
  }
}

resource "aws_autoscaling_attachment" "edge" {
  for_each = local.edge_asg_target_group_attachments

  autoscaling_group_name = aws_eks_node_group.golden[each.value.availability_zone].resources[0].autoscaling_groups[0].name
  lb_target_group_arn    = local.edge_target_group_arns[each.value.target_group]
}

resource "aws_lb_listener" "edge_http" {
  load_balancer_arn = aws_lb.edge.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.edge_frontend.arn
  }
}

resource "aws_lb_listener_rule" "edge_backend_api" {
  listener_arn = aws_lb_listener.edge_http.arn
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
}

resource "aws_lb_listener_rule" "edge_backend_health" {
  listener_arn = aws_lb_listener.edge_http.arn
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
}

resource "aws_lb_listener_rule" "edge_backend_ready" {
  listener_arn = aws_lb_listener.edge_http.arn
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
}
