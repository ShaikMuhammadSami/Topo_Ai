mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/topo-golden-mock"
    }
  }

  mock_resource "aws_launch_template" {
    defaults = {
      id             = "lt-0123456789abcdef0"
      latest_version = 1
    }
  }

  mock_resource "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    }
  }

  mock_resource "aws_ecr_repository" {
    defaults = {
      arn            = "arn:aws:ecr:us-east-1:123456789012:repository/topo-golden/topo"
      repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo"
    }
  }
}

override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["us-east-1a", "us-east-1b"]
  }
}

run "golden_foundation_contract" {
  # This applies only to Terraform's ephemeral mock-provider state. It never
  # loads AWS credentials or contacts AWS.
  command = apply

  variables {
    eks_public_access_cidrs = ["198.51.100.10/32"]
    github_repository       = "example/topo-ai"
  }

  assert {
    condition     = length(aws_subnet.public) == 2 && length(aws_subnet.private) == 2 && length(aws_subnet.database) == 2
    error_message = "The network must contain public, private worker, and database subnets across exactly two AZs."
  }

  assert {
    condition     = alltrue([for subnet in aws_subnet.private : !subnet.map_public_ip_on_launch])
    error_message = "Every EKS worker subnet must disable public IP assignment."
  }

  assert {
    condition     = alltrue([for subnet in aws_subnet.database : !subnet.map_public_ip_on_launch])
    error_message = "Every RDS subnet must disable public IP assignment."
  }

  assert {
    condition     = length(aws_eks_node_group.golden) == 2 && alltrue([for group in aws_eks_node_group.golden : group.scaling_config[0].desired_size == 1])
    error_message = "The golden must plan one managed worker in each Availability Zone."
  }

  assert {
    condition     = aws_eks_cluster.golden.vpc_config[0].endpoint_private_access && aws_eks_cluster.golden.vpc_config[0].endpoint_public_access
    error_message = "The golden control plane must support private worker access and narrow operator public access."
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.eks_api_from_nodes.from_port == 443 && aws_vpc_security_group_ingress_rule.eks_api_from_nodes.to_port == 443
    error_message = "Private workers must have an explicit HTTPS path to the EKS control-plane security group."
  }

  assert {
    condition     = length(aws_nat_gateway.golden) == 1 && length(aws_route.private_internet) == 2
    error_message = "The cost-sensitive default must route both private AZs through one NAT gateway."
  }

  assert {
    condition     = aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway" && length(aws_vpc_endpoint.s3.route_table_ids) == 2
    error_message = "The S3 gateway endpoint must cover both private worker route tables."
  }

  assert {
    condition     = aws_db_instance.postgres.engine == "postgres" && !aws_db_instance.postgres.multi_az && !aws_db_instance.postgres.publicly_accessible && aws_db_instance.postgres.storage_encrypted
    error_message = "RDS must be encrypted private Single-AZ PostgreSQL."
  }

  assert {
    condition     = aws_db_instance.postgres.manage_master_user_password && length(aws_db_instance.postgres.vpc_security_group_ids) == 1
    error_message = "RDS must use an AWS-managed password and a single dedicated security group."
  }

  assert {
    condition     = aws_vpc_security_group_ingress_rule.postgres_from_eks.referenced_security_group_id == aws_security_group.eks_nodes.id && aws_vpc_security_group_ingress_rule.postgres_from_eks.from_port == 5432 && aws_vpc_security_group_ingress_rule.postgres_from_eks.to_port == 5432
    error_message = "PostgreSQL ingress must be SG-to-SG from the dedicated worker boundary on port 5432 only."
  }

  assert {
    condition     = aws_ecr_repository.topo.image_tag_mutability == "IMMUTABLE" && aws_ecr_repository.topo.image_scanning_configuration[0].scan_on_push
    error_message = "ECR must enforce immutable tags and scan images on push."
  }
}

run "nat_per_az_option" {
  command = apply

  variables {
    eks_public_access_cidrs = ["198.51.100.10/32"]
    nat_gateway_per_az      = true
    github_repository       = "example/topo-ai"
  }

  assert {
    condition     = length(aws_nat_gateway.golden) == 2
    error_message = "The higher-availability option must create one NAT gateway per AZ."
  }
}

run "reject_world_open_eks_api" {
  command = plan

  variables {
    eks_public_access_cidrs = ["0.0.0.0/0"]
    github_repository       = "example/topo-ai"
  }

  expect_failures = [var.eks_public_access_cidrs]
}

run "github_artifact_publisher_contract" {
  command = apply

  variables {
    eks_public_access_cidrs = ["198.51.100.10/32"]
    github_repository       = "example/topo-ai"
  }

  assert {
    condition     = aws_iam_openid_connect_provider.github[0].url == "https://token.actions.githubusercontent.com"
    error_message = "The GitHub OIDC provider must use the exact GitHub Actions issuer."
  }

  assert {
    condition     = toset(aws_iam_openid_connect_provider.github[0].client_id_list) == toset(["sts.amazonaws.com"])
    error_message = "The GitHub OIDC provider must expose only the AWS STS audience."
  }

  assert {
    condition     = local.github_oidc_subject == "repo:example/topo-ai:ref:refs/heads/main"
    error_message = "OIDC subject must bind the exact repository and main branch."
  }

  assert {
    condition     = jsondecode(aws_iam_role.github_artifact_publisher.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    error_message = "OIDC trust must require the AWS STS audience."
  }

  assert {
    condition     = jsondecode(aws_iam_role.github_artifact_publisher.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == local.github_oidc_subject
    error_message = "OIDC trust must use the exact configured repository/ref subject."
  }

  assert {
    condition     = toset(jsondecode(aws_iam_role_policy.github_artifact_publisher.policy).Statement[0].Action) == toset(["ecr:GetAuthorizationToken"])
    error_message = "The account-wide statement must contain only ECR authorization-token retrieval."
  }

  assert {
    condition = toset(jsondecode(aws_iam_role_policy.github_artifact_publisher.policy).Statement[1].Action) == toset([
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ])
    error_message = "The repository statement must contain only image publication operations."
  }

  assert {
    condition     = jsondecode(aws_iam_role_policy.github_artifact_publisher.policy).Statement[1].Resource == aws_ecr_repository.topo.arn
    error_message = "Image publication must be scoped to the exact golden ECR repository ARN."
  }
}

run "reject_wildcard_github_repository" {
  command = plan

  variables {
    eks_public_access_cidrs = ["198.51.100.10/32"]
    github_repository       = "*/*"
  }

  expect_failures = [var.github_repository]
}
