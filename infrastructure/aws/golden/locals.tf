locals {
  name = var.name_prefix

  availability_zones = slice(data.aws_availability_zones.available.names, 0, 2)
  az_index           = { for index, az in local.availability_zones : az => index }

  public_subnet_cidrs = {
    for az, index in local.az_index : az => cidrsubnet(var.vpc_cidr, 8, index)
  }
  private_subnet_cidrs = {
    for az, index in local.az_index : az => cidrsubnet(var.vpc_cidr, 8, index + 10)
  }
  database_subnet_cidrs = {
    for az, index in local.az_index : az => cidrsubnet(var.vpc_cidr, 8, index + 20)
  }

  common_tags = merge(
    var.additional_tags,
    {
      Project     = "TopoAI"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Scope       = "CLOUD-V1-1A.1"
    },
  )
}
