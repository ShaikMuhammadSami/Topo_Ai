from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/cloud/cx0/escrow_secretstore_keyring.py"
SPEC = importlib.util.spec_from_file_location("cx0_secretstore_recovery", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load SecretStore recovery utility.")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def keyring_bytes() -> bytes:
    root = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii").rstrip("=")
    return json.dumps(
        {"keys": {"runtime-v1": root}, "version": 1},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class FakeAwsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeSecretsManager:
    def __init__(self, payload: bytes | None = None) -> None:
        self.payload = payload
        self.tags: list[dict[str, str]] = []
        self.create_calls = 0
        self.get_calls = 0
        self.describe_calls = 0
        self.version_id = "00000000-0000-4000-8000-000000000001"
        self.arn = (
            "arn:aws:secretsmanager:us-east-1:297361542190:secret:"
            "topo/golden/recovery/secret-store-keyring-v1-AbCdEf"
        )

    def describe_secret(self, *, SecretId: str):
        self.describe_calls += 1
        if self.payload is None:
            raise FakeAwsError("ResourceNotFoundException")
        return {
            "ARN": self.arn,
            "Name": SecretId,
            "Tags": list(self.tags),
            "VersionIdsToStages": {self.version_id: ["AWSCURRENT"]},
        }

    def create_secret(self, **kwargs):
        self.create_calls += 1
        if self.payload is not None:
            raise AssertionError("test fake refuses overwrite")
        self.payload = bytes(kwargs["SecretBinary"])
        self.tags = list(kwargs["Tags"])
        return {"ARN": self.arn, "Name": kwargs["Name"], "VersionId": self.version_id}

    def get_secret_value(self, **kwargs):
        self.get_calls += 1
        if self.payload is None:
            raise FakeAwsError("ResourceNotFoundException")
        return {
            "ARN": self.arn,
            "Name": kwargs["SecretId"],
            "VersionId": self.version_id,
            "SecretBinary": self.payload,
            "VersionStages": ["AWSCURRENT"],
        }


def live_evidence():
    raw = keyring_bytes()
    return MODULE.LiveKeyringEvidence(
        keyring_bytes=raw,
        active_key_id="runtime-v1",
        sha256=MODULE.hashlib.sha256(raw).hexdigest(),
        format_version=1,
        key_count=1,
    )


class SecretStoreRecoveryTests(unittest.TestCase):
    def test_kubernetes_reader_requests_only_the_two_approved_keys(self) -> None:
        raw = keyring_bytes()
        responses = {
            (
                "kubectl", "config", "get-contexts", "topo-golden",
                "--output", "name",
            ): b"topo-golden\n",
            (
                "kubectl", "--context", "topo-golden", "get", "secret",
                "topo-backend-runtime",
                "--namespace", "topo-system", "--output",
                r"jsonpath={.data.secret-store-keyring\.json}",
            ): base64.b64encode(raw),
            (
                "kubectl", "--context", "topo-golden", "get", "secret",
                "topo-backend-runtime",
                "--namespace", "topo-system", "--output",
                "jsonpath={.data.secret-store-active-key-id}",
            ): base64.b64encode(b"runtime-v1"),
        }
        calls = []

        def runner(arguments):
            key = tuple(arguments)
            calls.append(key)
            return responses[key]

        evidence = MODULE.read_live_keyring(runner=runner)
        self.assertEqual(evidence.keyring_bytes, raw)
        self.assertEqual(evidence.active_key_id, "runtime-v1")
        self.assertEqual(evidence.format_version, 1)
        self.assertEqual(evidence.key_count, 1)
        joined = "\n".join(" ".join(call) for call in calls)
        for forbidden in (
            "database-url", "migration-database-url", "bootstrap-token-hashes-json",
            "stringData", "--output=json",
        ):
            self.assertNotIn(forbidden, joined)

    def test_absent_secret_is_created_once_and_verified(self) -> None:
        live = live_evidence()
        client = FakeSecretsManager()
        recovery = MODULE.ensure_recovery_secret(
            client=client,
            live=live,
            create_if_absent=True,
        )
        self.assertTrue(recovery.created)
        self.assertEqual(client.create_calls, 1)
        self.assertEqual(client.payload, live.keyring_bytes)
        self.assertEqual(recovery.sha256, live.sha256)
        tags = {item["Key"]: item["Value"] for item in client.tags}
        self.assertEqual(tags, MODULE._required_tags(live))

    def test_existing_matching_secret_is_read_only_and_idempotent(self) -> None:
        live = live_evidence()
        client = FakeSecretsManager(live.keyring_bytes)
        client.tags = [
            {"Key": key, "Value": value}
            for key, value in MODULE._required_tags(live).items()
        ]
        recovery = MODULE.ensure_recovery_secret(
            client=client,
            live=live,
            create_if_absent=True,
        )
        self.assertFalse(recovery.created)
        self.assertEqual(client.create_calls, 0)
        self.assertEqual(recovery.sha256, live.sha256)

    def test_existing_mismatch_stops_without_create_or_update(self) -> None:
        live = live_evidence()
        client = FakeSecretsManager(b"different-keyring")
        client.tags = [
            {"Key": key, "Value": value}
            for key, value in MODULE._required_tags(live).items()
        ]
        with self.assertRaises(MODULE.RecoveryEscrowMismatch):
            MODULE.ensure_recovery_secret(
                client=client,
                live=live,
                create_if_absent=True,
            )
        self.assertEqual(client.create_calls, 0)

    def test_absent_verify_only_never_creates(self) -> None:
        client = FakeSecretsManager()
        with self.assertRaisesRegex(
            MODULE.RecoveryCustodyError, "RECOVERY_SECRET_ABSENT"
        ):
            MODULE.ensure_recovery_secret(
                client=client,
                live=live_evidence(),
                create_if_absent=False,
            )
        self.assertEqual(client.create_calls, 0)

    def test_source_has_no_update_rotation_delete_or_plaintext_file_path(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            ".put_secret_value(", ".update_secret(", ".rotate_secret(",
            ".delete_secret(", ".restore_secret(", "NamedTemporaryFile",
            "mkstemp", "SecretString=",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("SecretBinary=live.keyring_bytes", source)
        self.assertEqual(source.count("client.create_secret("), 1)


if __name__ == "__main__":
    unittest.main()
