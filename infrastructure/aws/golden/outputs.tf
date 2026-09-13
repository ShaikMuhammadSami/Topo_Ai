output "aws_region" {
  description = "AWS region containing the golden environment."
  value       = var.aws_region
}

output "availability_zones" {
  description = "The two Availability Zones selected for the golden network."
  value       = local.availability_zones
}

output "vpc" {
  description = "VPC identity consumed by later network and workload blocks."
  value = {
    id         = aws_vpc.golden.id
    cidr_block = aws_vpc.golden.cidr_block
  }
}

output "subnets" {
  description = "Ordered public, private worker, and isolated database subnet IDs."
  value = {
    public   = [for az in local.availability_zones : aws_subnet.public[az].id]
    private  = [for az in local.availability_zones : aws_subnet.private[az].id]
    database = [for az in local.availability_zones : aws_subnet.database[az].id]
  }
}

output "public_alb_subnet_ids" {
  description = "Two-AZ public subnet set reserved for the later ALB ingress block."
  value       = [for az in local.availability_zones : aws_subnet.public[az].id]
}

output "private_route_table_ids" {
  description = "Private worker route tables carrying NAT and S3 endpoint routes."
  value       = [for az in local.availability_zones : aws_route_table.private[az].id]
}

output "nat_gateway_ids" {
  description = "NAT gateways used by private workers. One is the cost-sensitive default; one per AZ is optional."
  value       = aws_nat_gateway.golden[*].id
}

output "s3_gateway_endpoint_id" {
  description = "S3 gateway VPC endpoint identity."
  value       = aws_vpc_endpoint.s3.id
}

output "eks" {
  description = "EKS control-plane details for later access and workload blocks."
  value = {
    name                   = aws_eks_cluster.golden.name
    arn                    = aws_eks_cluster.golden.arn
    endpoint               = aws_eks_cluster.golden.endpoint
    kubernetes_version     = aws_eks_cluster.golden.version
    certificate_authority  = try(aws_eks_cluster.golden.certificate_authority[0].data, null)
    oidc_issuer            = try(aws_eks_cluster.golden.identity[0].oidc[0].issuer, null)
    cluster_security_group = aws_eks_cluster.golden.vpc_config[0].cluster_security_group_id
    worker_security_group  = aws_security_group.eks_nodes.id
    node_group_names       = [for az in local.availability_zones : aws_eks_node_group.golden[az].node_group_name]
  }
}

output "ecr" {
  description = "Immutable image repository details for the next delivery block."
  value = {
    name           = aws_ecr_repository.topo.name
    arn            = aws_ecr_repository.topo.arn
    repository_url = aws_ecr_repository.topo.repository_url
    registry_id    = aws_ecr_repository.topo.registry_id
  }
}

output "rds" {
  description = "Non-secret PostgreSQL connection and security-boundary metadata."
  value = {
    identifier        = aws_db_instance.postgres.identifier
    arn               = aws_db_instance.postgres.arn
    address           = aws_db_instance.postgres.address
    endpoint          = aws_db_instance.postgres.endpoint
    port              = aws_db_instance.postgres.port
    database_name     = aws_db_instance.postgres.db_name
    master_username   = aws_db_instance.postgres.username
    master_secret_arn = try(aws_db_instance.postgres.master_user_secret[0].secret_arn, null)
    security_group_id = aws_security_group.postgres.id
    subnet_group_name = aws_db_subnet_group.postgres.name
  }
}

output "iam_roles" {
  description = "Foundation IAM role ARNs for later access/workload-identity blocks."
  value = {
    eks_cluster = aws_iam_role.eks_cluster.arn
    eks_nodes   = aws_iam_role.eks_nodes.arn
  }
}
