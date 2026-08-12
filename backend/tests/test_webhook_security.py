import base64
import hashlib
import hmac
import time

from app.services.webhook_security import (
    verify_github,
    verify_gitlab_signing_token,
    verify_terraform_cloud,
)


def test_github_signature() -> None:
    secret = "test-secret"

    body = b'{"hello":"world"}'

    signature = (
        "sha256="
        + hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    verify_github(
        secret=secret,
        body=body,
        signature=signature,
    )


def test_gitlab_signature() -> None:
    key = (
        b"01234567890123456789012345678901"
    )

    token = (
        "whsec_"
        + base64.b64encode(
            key
        ).decode()
    )

    body = (
        b'{"object_kind":"push"}'
    )

    webhook_id = "delivery-test"

    timestamp = str(
        int(time.time())
    )

    message = (
        f"{webhook_id}."
        f"{timestamp}."
    ).encode() + body

    signature = (
        "v1,"
        + base64.b64encode(
            hmac.new(
                key,
                message,
                hashlib.sha256,
            ).digest()
        ).decode()
    )

    verify_gitlab_signing_token(
        signing_token=token,
        body=body,
        webhook_id=webhook_id,
        timestamp=timestamp,
        signature=signature,
    )


def test_terraform_signature() -> None:
    secret = "terraform-secret"

    body = (
        b'{"run_id":"run-one"}'
    )

    signature = hmac.new(
        secret.encode(),
        body,
        hashlib.sha512,
    ).hexdigest()

    verify_terraform_cloud(
        secret=secret,
        body=body,
        signature=signature,
    )