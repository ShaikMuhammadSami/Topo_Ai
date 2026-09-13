resource "aws_cloudwatch_log_group" "eks" {
  name              = "/aws/eks/${local.name}/cluster"
  retention_in_days = var.eks_log_retention_days
}

resource "aws_eks_cluster" "golden" {
  name     = local.name
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.kubernetes_version

  enabled_cluster_log_types = var.eks_control_plane_log_types

  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = true
  }

  upgrade_policy {
    support_type = "STANDARD"
  }

  vpc_config {
    subnet_ids = [for az in local.availability_zones : aws_subnet.private[az].id]

    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.eks_public_access_cidrs
  }

  depends_on = [
    aws_cloudwatch_log_group.eks,
    aws_iam_role_policy_attachment.eks_cluster,
  ]
}

resource "aws_security_group" "eks_nodes" {
  name        = "${local.name}-eks-nodes"
  description = "TopoAI internal golden EKS worker boundary"
  vpc_id      = aws_vpc.golden.id

  tags = {
    Name = "${local.name}-eks-nodes"
  }
}

resource "aws_vpc_security_group_ingress_rule" "eks_nodes_self" {
  security_group_id            = aws_security_group.eks_nodes.id
  referenced_security_group_id = aws_security_group.eks_nodes.id
  ip_protocol                  = "-1"
  description                  = "Node and pod traffic within the golden worker boundary"
}

resource "aws_vpc_security_group_ingress_rule" "eks_control_plane_https" {
  security_group_id            = aws_security_group.eks_nodes.id
  referenced_security_group_id = aws_eks_cluster.golden.vpc_config[0].cluster_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "EKS control plane to node HTTPS"
}

resource "aws_vpc_security_group_ingress_rule" "eks_control_plane_kubelet" {
  security_group_id            = aws_security_group.eks_nodes.id
  referenced_security_group_id = aws_eks_cluster.golden.vpc_config[0].cluster_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 10250
  to_port                      = 10250
  description                  = "EKS control plane to kubelet"
}

resource "aws_vpc_security_group_egress_rule" "eks_nodes_ipv4" {
  security_group_id = aws_security_group.eks_nodes.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Worker outbound through private subnet NAT or VPC endpoints"
}

resource "aws_vpc_security_group_ingress_rule" "eks_api_from_nodes" {
  security_group_id            = aws_eks_cluster.golden.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.eks_nodes.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "Private workers to EKS control-plane API"
}

resource "aws_launch_template" "eks_nodes" {
  name_prefix            = "${local.name}-node-"
  update_default_version = true

  vpc_security_group_ids = [aws_security_group.eks_nodes.id]

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      delete_on_termination = true
      encrypted             = true
      volume_size           = var.node_root_volume_gib
      volume_type           = "gp3"
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags = merge(local.common_tags, {
      Name = "${local.name}-worker"
    })
  }

  tag_specifications {
    resource_type = "volume"
    tags = merge(local.common_tags, {
      Name = "${local.name}-worker"
    })
  }
}

# A one-node managed group in each AZ makes the two-node placement explicit.
# Scaling/autoscaling is intentionally deferred until real usage requires it.
resource "aws_eks_node_group" "golden" {
  for_each = aws_subnet.private

  cluster_name    = aws_eks_cluster.golden.name
  node_group_name = "${local.name}-${each.key}"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = [each.value.id]

  ami_type       = "AL2023_x86_64_STANDARD"
  capacity_type  = "ON_DEMAND"
  instance_types = var.node_instance_types

  scaling_config {
    desired_size = 1
    min_size     = 1
    max_size     = 1
  }

  update_config {
    max_unavailable = 1
  }

  launch_template {
    id      = aws_launch_template.eks_nodes.id
    version = aws_launch_template.eks_nodes.latest_version
  }

  labels = {
    "topo.ai/environment" = var.environment
    "topo.ai/role"        = "golden-worker"
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node,
    aws_iam_role_policy_attachment.eks_ecr_pull,
    aws_iam_role_policy_attachment.eks_cni,
    aws_route.private_internet,
    aws_vpc_endpoint.s3,
  ]
}
