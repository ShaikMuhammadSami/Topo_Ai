from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend"
WORKFLOW_PATH = ROOT / ".github/workflows/topo-golden-frontend-image.yml"
PUBLISHER_PATH = ROOT / "infrastructure/aws/golden/ci_artifact_publisher.tf"


def _workflow() -> tuple[str, dict]:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    return source, yaml.load(source, Loader=yaml.BaseLoader)


class CloudV1FrontendArtifactContractTests(unittest.TestCase):
    def test_security_patch_versions_are_exact_and_lockfile_authoritative(self) -> None:
        package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((FRONTEND / "package-lock.json").read_text(encoding="utf-8"))

        self.assertEqual(package["dependencies"]["next"], "16.3.3")
        self.assertEqual(package["devDependencies"]["postcss"], "8.5.28")
        self.assertEqual(lock["packages"][""]["dependencies"]["next"], "16.3.3")
        self.assertEqual(lock["packages"][""]["devDependencies"]["postcss"], "8.5.28")
        self.assertEqual(lock["packages"]["node_modules/next"]["version"], "16.3.3")
        self.assertEqual(lock["packages"]["node_modules/postcss"]["version"], "8.5.28")
        self.assertNotIn("nodemon", package["dependencies"])
        self.assertNotIn("shadcn", package["dependencies"])
        self.assertEqual(package["devDependencies"]["nodemon"], "^3.1.14")
        self.assertEqual(package["devDependencies"]["shadcn"], "^4.8.0")
        self.assertNotIn("nodemon", lock["packages"][""]["dependencies"])
        self.assertNotIn("shadcn", lock["packages"][""]["dependencies"])
        self.assertEqual(lock["packages"][""]["devDependencies"]["nodemon"], "^3.1.14")
        self.assertEqual(lock["packages"][""]["devDependencies"]["shadcn"], "^4.8.0")
        self.assertEqual(lock["packages"]["node_modules/nodemon"]["version"], "3.1.14")
        self.assertTrue(lock["packages"]["node_modules/nodemon"]["dev"])
        self.assertEqual(lock["packages"]["node_modules/shadcn"]["version"], "4.11.0")
        self.assertTrue(lock["packages"]["node_modules/shadcn"]["dev"])
        self.assertNotIn("baseline-browser-mapping", package["dependencies"])
        self.assertNotIn("baseline-browser-mapping", package["devDependencies"])
        self.assertEqual(
            lock["packages"]["node_modules/baseline-browser-mapping"]["version"],
            "2.11.25",
        )

    def test_health_route_is_static_and_dependency_free(self) -> None:
        source = (FRONTEND / "app/healthz/route.ts").read_text(encoding="utf-8")

        self.assertIn('dynamic = "force-static"', source)
        self.assertIn('status: "ok"', source)
        self.assertIn('component: "frontend"', source)
        self.assertNotRegex(
            source,
            r"(?i)process\.env|fetch\(|database|TOPO_BACKEND_URL|credential|secret",
        )

    def test_next_build_is_standalone_and_browser_transport_remains_same_origin(
        self,
    ) -> None:
        configuration = (FRONTEND / "next.config.mjs").read_text(encoding="utf-8")
        transport = (FRONTEND / "lib/topo-api.ts").read_text(encoding="utf-8")

        self.assertIn('output: "standalone"', configuration)
        self.assertIn("process.env.TOPO_BACKEND_URL", configuration)
        self.assertIn('source: "/api/:path*"', configuration)
        self.assertNotIn("NEXT_PUBLIC_TOPO_API_URL", configuration)
        self.assertIn('path.startsWith("/api/")', transport)
        self.assertIn('credentials: "same-origin"', transport)
        self.assertNotIn("NEXT_PUBLIC_TOPO_API_URL", transport)

    def test_container_is_pinned_locked_non_root_and_standalone(self) -> None:
        dockerfile = (FRONTEND / "Dockerfile").read_text(encoding="utf-8")

        self.assertRegex(
            dockerfile,
            r"(?m)^FROM node:24-bookworm-slim@sha256:[0-9a-f]{64} AS base$",
        )
        self.assertIn("RUN npm ci", dockerfile)
        self.assertNotIn("npm install", dockerfile)
        self.assertIn("/opt/topo-frontend/.next/standalone", dockerfile)
        self.assertIn("/opt/topo-frontend/.next/static", dockerfile)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn('ENTRYPOINT ["node"]', dockerfile)
        self.assertIn('CMD ["server.js"]', dockerfile)
        self.assertIn('topo.component="frontend"', dockerfile)
        for label in (
            "org.opencontainers.image.source",
            "org.opencontainers.image.revision",
            "org.opencontainers.image.created",
            "org.opencontainers.image.version",
        ):
            self.assertIn(label, dockerfile)

    def test_build_context_is_an_explicit_runtime_source_allowlist(self) -> None:
        dockerignore = (FRONTEND / ".dockerignore").read_text(encoding="utf-8")

        self.assertTrue(dockerignore.startswith("**\n"))
        allowed = {
            line.strip() for line in dockerignore.splitlines() if line.startswith("!")
        }
        self.assertEqual(
            allowed,
            {
                "!Dockerfile",
                "!.dockerignore",
                "!package.json",
                "!package-lock.json",
                "!next.config.mjs",
                "!next-env.d.ts",
                "!postcss.config.mjs",
                "!tsconfig.json",
                "!app/",
                "!app/**",
                "!components/",
                "!components/**",
                "!lib/",
                "!lib/**",
                "!public/",
                "!public/**",
            },
        )
        for excluded in (
            "**/node_modules/",
            "**/.next/",
            "**/.git/",
            "**/.env*",
            "**/test/",
            "**/coverage/",
            "**/*.log",
        ):
            self.assertIn(excluded, dockerignore)

    def test_workflow_separates_untrusted_build_from_manual_main_publish(self) -> None:
        source, workflow = _workflow()
        self.assertEqual(workflow["name"], "Topo Golden Frontend Image")
        self.assertIn("pull_request", workflow["on"])
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})

        validate = workflow["jobs"]["validate-container"]
        dependency_security = workflow["jobs"]["validate-production-dependencies"]
        publish = workflow["jobs"]["publish"]
        self.assertEqual(validate["permissions"], {"contents": "read"})
        self.assertEqual(dependency_security["permissions"], {"contents": "read"})
        self.assertEqual(
            publish["permissions"],
            {"contents": "read", "id-token": "write"},
        )
        self.assertNotIn("id-token", validate["permissions"])
        self.assertIn("github.event_name == 'workflow_dispatch'", publish["if"])
        self.assertIn("github.ref == 'refs/heads/main'", publish["if"])
        self.assertIn("PUBLISH_GOLDEN_FRONTEND", publish["if"])
        self.assertEqual(
            set(publish["needs"]),
            {"validate-production-dependencies", "validate-container"},
        )

        dependency_source = yaml.safe_dump(dependency_security, sort_keys=True)
        self.assertIn("actions/setup-node@v6", dependency_source)
        self.assertIn("node-version: '24'", dependency_source)
        self.assertIn("working-directory: frontend", dependency_source)
        self.assertIn("npm ci", dependency_source)
        self.assertIn("npm audit --omit=dev --audit-level=high", dependency_source)
        self.assertNotIn("npm audit fix", dependency_source)

        validate_source = yaml.safe_dump(validate, sort_keys=True)
        self.assertNotIn("configure-aws-credentials", validate_source)
        self.assertNotIn("amazon-ecr-login", validate_source)
        self.assertIn("push: 'false'", validate_source)
        self.assertNotIn("AWS_ACCESS_KEY_ID", source)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", source)

    def test_receipt_is_component_specific_immutable_and_non_deploying(self) -> None:
        source, _ = _workflow()

        self.assertIn('"schema_version": "topo-cloud-golden-artifact-v1"', source)
        self.assertIn('"component": "frontend"', source)
        self.assertIn("steps.build.outputs.digest", source)
        self.assertIn('f"{repository}@{digest}"', source)
        self.assertIn("actions/upload-artifact@v7", source)
        self.assertIn(
            "frontend-sha-${GITHUB_SHA}-run-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}",
            source,
        )
        for field in (
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

        self.assertNotRegex(source, r"(?i)(?:image_tag|tags):?\s*latest")
        for forbidden in (
            "kubectl",
            "aws eks",
            "terraform apply",
            "route53",
            "acm",
            "wafv2",
        ):
            self.assertNotIn(forbidden, source.casefold())

    def test_existing_publisher_authority_is_sufficient_and_not_broadened(self) -> None:
        source, _ = _workflow()
        terraform = PUBLISHER_PATH.read_text(encoding="utf-8")

        self.assertIn("vars.TOPO_GOLDEN_AWS_ROLE_ARN", source)
        self.assertIn("vars.TOPO_GOLDEN_ECR_REPOSITORY_URL", source)
        self.assertIn("Resource = aws_ecr_repository.topo.arn", terraform)
        self.assertIn('"repo:${var.github_repository}:ref:refs/heads/main"', terraform)
        self.assertNotIn('Action = "*"', terraform)
        self.assertNotRegex(terraform, r'"(?:eks|ec2|rds|iam):')

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
