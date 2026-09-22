variable "aws_region" {
  description = "Single AWS region used by the internal golden environment."
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a valid AWS region name."
  }
}

variable "name_prefix" {
  description = "Lowercase prefix applied to golden-environment resources."
  type        = string
  default     = "topo-golden"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.name_prefix))
    error_message = "name_prefix must be 3-24 lowercase alphanumeric/hyphen characters and start with a letter."
  }
}

variable "environment" {
  description = "Environment tag value."
  type        = string
  default     = "internal-golden"
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the isolated golden VPC."
  type        = string
  default     = "10.40.0.0/16"

  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 8, 0))
    error_message = "vpc_cidr must be an IPv4 CIDR with enough space for /24 subnets."
  }
}

variable "eks_public_access_cidrs" {
  description = "Operator-controlled IPv4 CIDRs allowed to reach the public EKS API. Supply narrow office/VPN addresses; world-open CIDRs are rejected."
  type        = list(string)

  validation {
    condition = (
      length(var.eks_public_access_cidrs) > 0 &&
      alltrue([for cidr in var.eks_public_access_cidrs : can(cidrnetmask(cidr))]) &&
      !contains(var.eks_public_access_cidrs, "0.0.0.0/0")
    )
    error_message = "Provide at least one valid narrow IPv4 EKS API CIDR; 0.0.0.0/0 is not accepted."
  }
}

variable "edge_validation_ipv4_cidrs" {
  description = "Temporary IPv4 /32 host CIDRs allowed to perform non-secret HTTP edge validation before TLS, WAF, and application DNS publication. Do not persist a personal operator address in source."
  type        = list(string)
  default     = []

  validation {
    condition = (
      length(var.edge_validation_ipv4_cidrs) == length(distinct(var.edge_validation_ipv4_cidrs)) &&
      alltrue([
        for cidr in var.edge_validation_ipv4_cidrs :
        can(cidrnetmask(cidr)) && endswith(cidr, "/32") && cidr != "0.0.0.0/0"
      ])
    )
    error_message = "edge_validation_ipv4_cidrs must contain unique valid IPv4 /32 host CIDRs and must not contain 0.0.0.0/0."
  }
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version. Keep this on standard support."
  type        = string
  default     = "1.35"
}

variable "node_instance_types" {
  description = "Instance types for each of the two one-node managed node groups."
  type        = list(string)
  default     = ["t3.small"]

  validation {
    condition     = length(var.node_instance_types) > 0
    error_message = "At least one EKS node instance type is required."
  }
}

variable "node_root_volume_gib" {
  description = "Encrypted gp3 root volume size for each worker node."
  type        = number
  default     = 30

  validation {
    condition     = var.node_root_volume_gib >= 20
    error_message = "node_root_volume_gib must be at least 20 GiB."
  }
}

variable "nat_gateway_per_az" {
  description = "Create one NAT gateway per AZ. False uses one lower-cost NAT gateway and accepts an internal-golden availability tradeoff."
  type        = bool
  default     = false
}

variable "eks_control_plane_log_types" {
  description = "EKS control-plane log types retained in CloudWatch."
  type        = set(string)
  default     = ["api", "audit", "authenticator"]

  validation {
    condition = length(setsubtract(
      var.eks_control_plane_log_types,
      toset(["api", "audit", "authenticator", "controllerManager", "scheduler"]),
    )) == 0
    error_message = "Unsupported EKS control-plane log type."
  }
}

variable "eks_log_retention_days" {
  description = "CloudWatch retention for EKS control-plane logs."
  type        = number
  default     = 7
}

variable "ecr_force_delete" {
  description = "Allow terraform destroy to remove a non-empty golden ECR repository. Disabled by default to protect evidence-bearing images."
  type        = bool
  default     = false
}

variable "database_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "topo"

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,62}$", var.database_name))
    error_message = "database_name must be a valid PostgreSQL identifier up to 63 characters."
  }
}

variable "database_master_username" {
  description = "RDS master username. The password is generated and held by AWS Secrets Manager, never supplied to Terraform."
  type        = string
  default     = "topo_admin"

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,62}$", var.database_master_username))
    error_message = "database_master_username must be a valid identifier up to 63 characters."
  }
}

variable "rds_engine_version" {
  description = "RDS PostgreSQL major version aligned with TopoAI's accepted PostgreSQL baseline."
  type        = string
  default     = "16"
}

variable "rds_instance_class" {
  description = "Cost-sensitive Single-AZ RDS instance class for the internal golden."
  type        = string
  default     = "db.t4g.micro"
}

variable "rds_allocated_storage_gib" {
  description = "Initial encrypted gp3 RDS storage allocation."
  type        = number
  default     = 20

  validation {
    condition     = var.rds_allocated_storage_gib >= 20
    error_message = "RDS gp3 storage must be at least 20 GiB."
  }
}

variable "rds_max_allocated_storage_gib" {
  description = "RDS storage autoscaling ceiling. Set equal to initial storage to avoid growth."
  type        = number
  default     = 40

  validation {
    condition     = var.rds_max_allocated_storage_gib >= var.rds_allocated_storage_gib
    error_message = "rds_max_allocated_storage_gib must be at least rds_allocated_storage_gib."
  }
}

variable "rds_backup_retention_days" {
  description = "Automated RDS backup retention for the disposable golden."
  type        = number
  default     = 1

  validation {
    condition     = var.rds_backup_retention_days >= 0 && var.rds_backup_retention_days <= 35
    error_message = "rds_backup_retention_days must be between 0 and 35."
  }
}

variable "rds_deletion_protection" {
  description = "Protect RDS from deletion. Disabled by default because this environment must remain disposable."
  type        = bool
  default     = false
}

variable "rds_skip_final_snapshot" {
  description = "Skip the final snapshot during destroy. True is the disposable golden default."
  type        = bool
  default     = true
}

variable "additional_tags" {
  description = "Additional non-secret resource tags."
  type        = map(string)
  default     = {}
}

variable "github_repository" {
  description = "Exact GitHub owner/repository allowed to publish the golden backend artifact."
  type        = string

  validation {
    condition = (
      can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository)) &&
      !strcontains(var.github_repository, "*")
    )
    error_message = "github_repository must be one exact owner/repository without wildcards."
  }
}

variable "github_oidc_provider_arn" {
  description = "Optional existing same-account GitHub OIDC provider ARN. Null creates the provider in this Terraform root."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.github_oidc_provider_arn == null ||
      can(regex("^arn:aws(-[a-z]+)?:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.github_oidc_provider_arn))
    )
    error_message = "github_oidc_provider_arn must be an AWS IAM provider ARN for token.actions.githubusercontent.com."
  }
}
