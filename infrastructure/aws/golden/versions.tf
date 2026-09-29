terraform {
  required_version = ">= 1.10, < 2.0"

  backend "s3" {
    bucket       = "topo-tfstate-297361542190-us-east-1"
    key          = "golden/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
