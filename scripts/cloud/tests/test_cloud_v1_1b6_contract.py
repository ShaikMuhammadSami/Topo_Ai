from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
FOUNDATION_PATH = (
    ROOT / "infrastructure/kubernetes/golden/foundation.yaml"
)
BACKEND_PATH = (
    ROOT / "infrastructure/kubernetes/golden/backend.yaml"
)
AWS_GOLDEN_DIR = ROOT / "infrastructure/aws/golden"
CONTRACT_PATH = (
    ROOT
    / "docs/architecture/"
    "cloud-v1-1b6-browser-session-production-acceptance-v1.md"
)

EXPECTED_ORIGIN = '["https://app.topoai.io"]'


def load_documents(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return [
            document
            for document in yaml.safe_load_all(handle)
            if isinstance(document, dict)
        ]


def find_resource(documents, kind, name):
    for document in documents:
        if (
            document.get("kind") == kind
            and document.get("metadata", {}).get("name") == name
        ):
            return document
    raise AssertionError(f"{kind}/{name} not found")


class CloudV11B6ContractTests(unittest.TestCase):
    def test_golden_origin_is_exact_production_origin(self):
        documents = load_documents(FOUNDATION_PATH)
        config_map = find_resource(
            documents,
            "ConfigMap",
            "topo-runtime-config",
        )

        value = config_map["data"]["browser-allowed-origins-json"]

        self.assertEqual(value, EXPECTED_ORIGIN)
        self.assertNotIn("*", value)
        self.assertEqual(value.count("https://"), 1)
        self.assertNotIn("http://", value)

    def test_backend_consumes_origin_from_runtime_config(self):
        documents = load_documents(BACKEND_PATH)
        deployment = find_resource(
            documents,
            "Deployment",
            "topo-backend",
        )

        containers = (
            deployment["spec"]["template"]["spec"]["containers"]
        )

        matching = []

        for container in containers:
            for env in container.get("env", []):
                if (
                    env.get("name")
                    == "TOPO_BROWSER_ALLOWED_ORIGINS_JSON"
                ):
                    matching.append(env)

        self.assertEqual(len(matching), 1)

        ref = matching[0]["valueFrom"]["configMapKeyRef"]

        self.assertEqual(ref["name"], "topo-runtime-config")
        self.assertEqual(
            ref["key"],
            "browser-allowed-origins-json",
        )

    def test_dns_remains_external_to_terraform(self):
        terraform = "\n".join(
            path.read_text(encoding="utf-8")
            for path in AWS_GOLDEN_DIR.glob("*.tf")
        )

        self.assertNotIn("aws_route53_", terraform)
        self.assertNotIn("aws_cloudfront_", terraform)

    def test_contract_preserves_safe_live_order(self):
        text = CONTRACT_PATH.read_text(encoding="utf-8")

        required = [
            "Publish only the app.topoai.io Porkbun application CNAME",
            "Verify that every authoritative Porkbun nameserver",
            "Apply the reviewed topo-runtime-config production-origin source",
            "Perform a controlled topo-backend rollout",
            "Only after all preceding gates pass may one transient human credential",
        ]

        positions = [text.index(item) for item in required]

        self.assertEqual(positions, sorted(positions))

    def test_contract_preserves_security_boundaries(self):
        text = CONTRACT_PATH.read_text(encoding="utf-8")

        self.assertIn(EXPECTED_ORIGIN, text)
        self.assertIn(
            "The existing ACM validation CNAME must remain untouched permanently.",
            text,
        )
        self.assertIn(
            "No wildcard origin is permitted.",
            text,
        )
        self.assertIn(
            "worker NodePorts",
            text,
        )
        self.assertIn(
            "No durable human bearer credential",
            text,
        )
        self.assertIn(
            "The browser must not require api.topoai.io.",
            text,
        )


if __name__ == "__main__":
    unittest.main()
