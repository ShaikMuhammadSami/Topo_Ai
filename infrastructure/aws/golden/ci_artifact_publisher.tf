locals {
  github_oidc_issuer   = "https://token.actions.githubusercontent.com"
  github_oidc_audience = "sts.amazonaws.com"
  github_oidc_subject = (
    "repo:${var.github_repository}:ref:refs/heads/main"
  )
  github_oidc_provider_arn = (
    var.github_oidc_provider_arn != null
    ? var.github_oidc_provider_arn
    : aws_iam_openid_connect_provider.github[0].arn
  )
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.github_oidc_provider_arn == null ? 1 : 0

  url             = local.github_oidc_issuer
  client_id_list  = [local.github_oidc_audience]
  thumbprint_list = []

  tags = {
    Name = "${local.name}-github-actions"
  }
}

resource "aws_iam_role" "github_artifact_publisher" {
  name                 = "${local.name}-github-artifact-publisher"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ExactRepositoryMainBranch"
      Effect = "Allow"
      Principal = {
        Federated = local.github_oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = local.github_oidc_audience
          "token.actions.githubusercontent.com:sub" = local.github_oidc_subject
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_artifact_publisher" {
  name = "${local.name}-ecr-publish"
  role = aws_iam_role.github_artifact_publisher.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrAuthentication"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "PublishOnlyToGoldenRepository"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:CompleteLayerUpload",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
        ]
        Resource = aws_ecr_repository.topo.arn
      },
    ]
  })
}
