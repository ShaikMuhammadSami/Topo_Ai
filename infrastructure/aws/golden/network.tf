data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

resource "aws_vpc" "golden" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${local.name}-vpc"
  }
}

resource "aws_internet_gateway" "golden" {
  vpc_id = aws_vpc.golden.id

  tags = {
    Name = "${local.name}-igw"
  }
}

resource "aws_subnet" "public" {
  for_each = local.public_subnet_cidrs

  vpc_id                  = aws_vpc.golden.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = false

  tags = {
    Name                                  = "${local.name}-public-${each.key}"
    "kubernetes.io/cluster/${local.name}" = "shared"
    "kubernetes.io/role/elb"              = "1"
    "topo.ai/subnet-purpose"              = "public-alb-and-nat"
  }
}

resource "aws_subnet" "private" {
  for_each = local.private_subnet_cidrs

  vpc_id                  = aws_vpc.golden.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = false

  tags = {
    Name                                  = "${local.name}-private-${each.key}"
    "kubernetes.io/cluster/${local.name}" = "shared"
    "kubernetes.io/role/internal-elb"     = "1"
    "topo.ai/subnet-purpose"              = "private-eks-workers"
  }
}

resource "aws_subnet" "database" {
  for_each = local.database_subnet_cidrs

  vpc_id                  = aws_vpc.golden.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = false

  tags = {
    Name                     = "${local.name}-database-${each.key}"
    "topo.ai/subnet-purpose" = "private-rds"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.golden.id

  tags = {
    Name = "${local.name}-public"
  }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.golden.id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count = var.nat_gateway_per_az ? 2 : 1

  domain = "vpc"

  depends_on = [aws_internet_gateway.golden]

  tags = {
    Name = "${local.name}-nat-${count.index + 1}"
  }
}

resource "aws_nat_gateway" "golden" {
  count = var.nat_gateway_per_az ? 2 : 1

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[local.availability_zones[count.index]].id

  depends_on = [aws_internet_gateway.golden]

  tags = {
    Name = "${local.name}-nat-${count.index + 1}"
  }
}

resource "aws_route_table" "private" {
  for_each = local.az_index

  vpc_id = aws_vpc.golden.id

  tags = {
    Name = "${local.name}-private-${each.key}"
  }
}

resource "aws_route" "private_internet" {
  for_each = aws_route_table.private

  route_table_id         = each.value.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id = aws_nat_gateway.golden[
    var.nat_gateway_per_az ? local.az_index[each.key] : 0
  ].id
}

resource "aws_route_table_association" "private" {
  for_each = aws_subnet.private

  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}

resource "aws_route_table" "database" {
  for_each = local.az_index

  vpc_id = aws_vpc.golden.id

  tags = {
    Name = "${local.name}-database-${each.key}"
  }
}

resource "aws_route_table_association" "database" {
  for_each = aws_subnet.database

  subnet_id      = each.value.id
  route_table_id = aws_route_table.database[each.key].id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.golden.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for route_table in aws_route_table.private : route_table.id]

  tags = {
    Name = "${local.name}-s3"
  }
}
