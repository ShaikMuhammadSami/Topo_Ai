from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github/workflows/topo-golden-observer-image.yml"
BACKEND_WORKFLOW_PATH = ROOT / ".github/workflows/topo-golden-backend-image.yml"
DOCKERFILE_PATH = ROOT / "agent/Dockerfile"
DOCKERIGNORE_PATH = ROOT / "agent/.dockerignore"
LOCK_PATH = ROOT / "agent/requirements.lock"
MANIFEST_PATH = ROOT / "infrastructure/kubernetes/golden/observer.yaml"
PUBLISHER_PATH = ROOT / "infrastructure/aws/golden/ci_artifact_publisher.tf"
DOCUMENT_PATH = ROOT / "docs/architecture/cloud-v1-1a4c1-live-artifacts-v1.md"


def _workflow() -> tuple[str, dict]:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    return source, yaml.load(source, Loader=yaml.BaseLoader)


def _observer_deployment() -> dict:
    resources = [
        document
        for document in yaml.safe_load_all(MANIFEST_PATH.read_text(encoding="utf-8"))
        if isinstance(document, dict)
    ]
    matches = [
        document
        for document in resources
        if document.get("kind") == "Deployment"
        and document.get("metadata", {}).get("name") == "topo-observer"
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one topo-observer Deployment; found {len(matches)}")
    return matches[0]


class CloudV1ObserverArtifactContractTests(unittest.TestCase):
    def test_observer_container_is_pinned_locked_and_non_root(self) -> None:
        dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            dockerfile,
            r"(?m)^FROM python:3\.12-slim@sha256:[0-9a-f]{64}$",
        )
        self.assertIn("--requirement requirements.lock", dockerfile)
        self.assertIn("--no-deps", dockerfile)
        self.assertIn("python -m pip check", dockerfile)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn('["python", "-m", "topo_agent"]', dockerfile)
        self.assertIn('CMD ["run"]', dockerfile)
        self.assertIn('topo.component="observer"', dockerfile)
        self.assertNotIn("COPY .", dockerfile)
        self.assertNotIn("pyproject.toml", dockerfile)

        requirements = [
            line.strip()
            for line in LOCK_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertGreater(len(requirements), 60)
        self.assertTrue(
            all(re.fullmatch(r"[A-Za-z0-9._-]+==[^\s]+", item) for item in requirements)
        )

    def test_observer_build_context_is_an_explicit_allowlist(self) -> None:
        dockerignore = DOCKERIGNORE_PATH.read_text(encoding="utf-8")
        self.assertTrue(dockerignore.startswith("**\n"))
        self.assertEqual(
            {
                line.strip()
                for line in dockerignore.splitlines()
                if line.startswith("!")
            },
            {"!Dockerfile", "!.dockerignore", "!requirements.lock", "!src/", "!src/**"},
        )
        self.assertIn("**/*.egg-info/", dockerignore)
        for forbidden in (".env", ".git", "terraform.tfstate", "kubeconfig"):
            self.assertNotIn(f"!{forbidden}", dockerignore.casefold())

    def test_pr_build_is_credential_free_and_publish_is_main_manual_only(self) -> None:
        source, workflow = _workflow()
        self.assertIn("pull_request", workflow["on"])
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})

        validate = workflow["jobs"]["validate-container"]
        publish = workflow["jobs"]["publish"]
        self.assertEqual(validate["permissions"], {"contents": "read"})
        self.assertEqual(publish["permissions"], {"contents": "read", "id-token": "write"})
        self.assertNotIn("id-token", validate["permissions"])
        self.assertIn("github.event_name == 'workflow_dispatch'", publish["if"])
        self.assertIn("github.ref == 'refs/heads/main'", publish["if"])
        self.assertIn("PUBLISH_GOLDEN_OBSERVER", publish["if"])

        validate_source = yaml.safe_dump(validate, sort_keys=True)
        self.assertNotIn("configure-aws-credentials", validate_source)
        self.assertNotIn("amazon-ecr-login", validate_source)
        self.assertIn("push: 'false'", validate_source)
        self.assertNotIn("AWS_ACCESS_KEY_ID", source)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", source)

    def test_publication_reuses_exact_ecr_role_without_deployment_authority(self) -> None:
        source, _ = _workflow()
        terraform = PUBLISHER_PATH.read_text(encoding="utf-8")
        self.assertIn("vars.TOPO_GOLDEN_AWS_ROLE_ARN", source)
        self.assertIn("vars.TOPO_GOLDEN_ECR_REPOSITORY_URL", source)
        self.assertIn('Resource = aws_ecr_repository.topo.arn', terraform)
        self.assertIn('"repo:${var.github_repository}:ref:refs/heads/main"', terraform)
        self.assertNotIn('Action = "*"', terraform)

        actions = set(re.findall(r'"(ecr:[A-Za-z]+)"', terraform))
        self.assertEqual(
            actions,
            {
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability",
                "ecr:CompleteLayerUpload",
                "ecr:InitiateLayerUpload",
                "ecr:PutImage",
                "ecr:UploadLayerPart",
            },
        )
        self.assertNotRegex(terraform, r'"(?:eks|ec2|rds|iam):')
        self.assertNotIn("kubectl", source)
        self.assertNotIn("aws eks", source)

    def test_receipt_proves_observer_commit_run_and_digest_identity(self) -> None:
        source, _ = _workflow()
        self.assertIn('"component": "observer"', source)
        self.assertIn("steps.build.outputs.digest", source)
        self.assertIn('f"{repository}@{digest}"', source)
        self.assertIn("topo-cloud-golden-artifact-v1", source)
        self.assertIn("actions/upload-artifact@v7", source)
        for field in (
            "component",
            "source_repository",
            "git_commit_sha",
            "git_ref",
            "workflow_name",
            "workflow_ref",
            "workflow_run_id",
            "workflow_run_attempt",
            "ecr_repository",
            "image_tag",
            "image_digest",
            "immutable_image_ref",
        ):
            self.assertIn(f'"{field}"', source)
        self.assertIn("observer-sha-${GITHUB_SHA}-run-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}", source)
        self.assertNotRegex(source, r"(?i)(?:image_tag|tags):?\s*latest")

    def test_manifest_is_compatible_and_digest_oriented(self) -> None:
        deployment = _observer_deployment()
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        environment = {item["name"]: item for item in container["env"]}

        self.assertRegex(container["image"], r"@sha256:[0-9a-f]{64}$")
        self.assertNotIn(":latest", container["image"].casefold())
        self.assertEqual(container["args"], ["run"])
        self.assertEqual(pod["securityContext"]["runAsUser"], 10001)
        self.assertEqual(pod["securityContext"]["runAsGroup"], 10001)
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(environment["TOPO_ENABLED_PLUGINS"]["value"], "kubernetes")
        for provider in ("AWS", "AZURE", "GCP"):
            self.assertEqual(environment[f"TOPO_CHANGE_WATCH_{provider}"]["value"], "false")
        self.assertTrue(pod["automountServiceAccountToken"])
        self.assertEqual(environment["TOPO_AGENT_HOME"]["value"], "/var/lib/topo-agent")
        self.assertIn("/var/lib/topo-agent", {
            mount["mountPath"] for mount in container["volumeMounts"]
        })
        self.assertIn("/tmp", {mount["mountPath"] for mount in container["volumeMounts"]})

    def test_backend_artifact_pipeline_remains_separate_and_immutable(self) -> None:
        backend = BACKEND_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("PUBLISH_GOLDEN_BACKEND", backend)
        self.assertIn("steps.build.outputs.digest", backend)
        self.assertIn("vars.TOPO_GOLDEN_AWS_ROLE_ARN", backend)
        self.assertNotRegex(backend, r"(?i)(?:image_tag|tags):?\s*latest")

    def test_c1b_requires_both_live_publications_before_deployment(self) -> None:
        document = " ".join(DOCUMENT_PATH.read_text(encoding="utf-8").split())
        for required_contract in (
            "Run C1-B only after this source is reviewed and merged to `main`",
            "expected live `topo-golden/topo` repository",
            "exact configured GitHub repository on `refs/heads/main`",
            "Topo Golden Backend Image",
            "PUBLISH_GOLDEN_BACKEND",
            "repository@sha256:<backend-digest>",
            "Topo Golden Observer Image",
            "PUBLISH_GOLDEN_OBSERVER",
            "repository@sha256:<observer-digest>",
            "workflow-produced digest",
            "receipt digest",
            "AWS/ECR-reported digest",
            "ECR contains both component images",
            "neither component uses `latest`",
            "no Kubernetes deployment has occurred",
        ):
            self.assertIn(required_contract, document)


if __name__ == "__main__":
    unittest.main()
