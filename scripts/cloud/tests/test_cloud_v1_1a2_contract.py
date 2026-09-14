from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github/workflows/topo-golden-backend-image.yml"
DOCKERFILE_PATH = ROOT / "backend/Dockerfile"
DOCKERIGNORE_PATH = ROOT / "backend/.dockerignore"
LOCK_PATH = ROOT / "backend/requirements.lock"
TERRAFORM_PATH = ROOT / "infrastructure/aws/golden/ci_artifact_publisher.tf"


class CloudV1ArtifactContractTests(unittest.TestCase):
    def test_container_is_pinned_minimal_and_non_root(self) -> None:
        dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
        self.assertRegex(dockerfile, r"(?m)^FROM python:3\.12-slim@sha256:[0-9a-f]{64}$")
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("EXPOSE 8000", dockerfile)
        self.assertIn('["app.main:app", "--host", "0.0.0.0", "--port", "8000"', dockerfile)
        self.assertIn("org.opencontainers.image.source", dockerfile)
        self.assertIn("org.opencontainers.image.revision", dockerfile)
        self.assertNotIn("COPY .", dockerfile)

    def test_container_context_is_an_explicit_allowlist(self) -> None:
        dockerignore = DOCKERIGNORE_PATH.read_text(encoding="utf-8")
        self.assertTrue(dockerignore.startswith("**\n"))
        for allowed in ("!requirements.lock", "!alembic.ini", "!alembic/**", "!app/**"):
            self.assertIn(allowed, dockerignore)
        for excluded in ("app/**/__pycache__/", "app/**/*.py[cod]", "alembic/**/__pycache__/"):
            self.assertIn(excluded, dockerignore)

    def test_runtime_lock_contains_only_exact_requirements(self) -> None:
        requirements = [
            line.strip()
            for line in LOCK_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertGreater(len(requirements), 60)
        self.assertTrue(all(re.fullmatch(r"[a-z0-9-]+==[^\s]+", item) for item in requirements))

    def test_workflow_separates_untrusted_build_from_trusted_publish(self) -> None:
        source = WORKFLOW_PATH.read_text(encoding="utf-8")
        workflow = yaml.load(source, Loader=yaml.BaseLoader)
        self.assertIn("pull_request", workflow["on"])
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})

        validate = workflow["jobs"]["validate-container"]
        publish = workflow["jobs"]["publish"]
        self.assertEqual(validate["permissions"], {"contents": "read"})
        self.assertEqual(publish["permissions"], {"contents": "read", "id-token": "write"})
        self.assertIn("github.event_name == 'workflow_dispatch'", publish["if"])
        self.assertIn("github.ref == 'refs/heads/main'", publish["if"])
        self.assertIn("PUBLISH_GOLDEN_BACKEND", publish["if"])
        self.assertNotIn("id-token", validate["permissions"])

    def test_workflow_captures_digest_receipt_without_deployment(self) -> None:
        source = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("steps.build.outputs.digest", source)
        self.assertIn('f"{repository}@{digest}"', source)
        self.assertIn("topo-cloud-golden-artifact-v1", source)
        self.assertIn("actions/upload-artifact@v7", source)
        for receipt_field in (
            "source_repository",
            "git_commit_sha",
            "git_ref",
            "workflow_name",
            "workflow_ref",
            "workflow_run_id",
            "workflow_run_attempt",
            "ecr_repository",
            "image_digest",
            "immutable_image_ref",
        ):
            self.assertIn(f'"{receipt_field}"', source)
        self.assertNotRegex(source, r"(?i)(?:image_tag|tags):?\s*latest")
        self.assertNotIn("kubectl", source)
        self.assertNotIn("aws eks", source)
        self.assertNotIn("AWS_ACCESS_KEY_ID", source)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", source)

    def test_oidc_trust_and_ecr_permissions_are_exact(self) -> None:
        terraform = TERRAFORM_PATH.read_text(encoding="utf-8")
        self.assertIn('github_oidc_issuer   = "https://token.actions.githubusercontent.com"', terraform)
        self.assertIn('github_oidc_audience = "sts.amazonaws.com"', terraform)
        self.assertIn('"token.actions.githubusercontent.com:aud" = local.github_oidc_audience', terraform)
        self.assertIn('"token.actions.githubusercontent.com:sub" = local.github_oidc_subject', terraform)
        self.assertIn('"repo:${var.github_repository}:ref:refs/heads/main"', terraform)
        self.assertNotIn("thumbprint_list", terraform)
        self.assertNotIn("ignore_changes", terraform)
        self.assertNotRegex(terraform, r"(?i)\b[0-9a-f]{40}\b")
        self.assertNotIn('Action = "*"', terraform)
        self.assertIn("Resource = aws_ecr_repository.topo.arn", terraform)

        actions = set(re.findall(r'"(ecr:[A-Za-z]+)"', terraform))
        self.assertEqual(
            actions,
            {
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability",
                "ecr:BatchGetImage",
                "ecr:CompleteLayerUpload",
                "ecr:InitiateLayerUpload",
                "ecr:PutImage",
                "ecr:UploadLayerPart",
            },
        )


if __name__ == "__main__":
    unittest.main()
