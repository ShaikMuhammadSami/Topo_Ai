from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time


class WebhookAuthenticationError(
    ValueError
):
    pass


def resolve_secret(
    secret_ref: str | None,
) -> str:
    if not secret_ref:
        raise WebhookAuthenticationError(
            "No secret_ref configured."
        )

    secret = os.getenv(
        secret_ref
    )

    if not secret:
        raise WebhookAuthenticationError(
            (
                "Required environment "
                f"variable {secret_ref} "
                "is not set."
            )
        )

    return secret


def verify_github(
    *,
    secret: str,
    body: bytes,
    signature: str | None,
) -> None:
    if not signature:
        raise WebhookAuthenticationError(
            "GitHub signature missing."
        )

    expected = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(
        expected,
        signature,
    ):
        raise WebhookAuthenticationError(
            "GitHub signature invalid."
        )


def verify_gitlab_signing_token(
    *,
    signing_token: str,
    body: bytes,
    webhook_id: str | None,
    timestamp: str | None,
    signature: str | None,
    maximum_age_seconds: int = 300,
) -> None:
    if not webhook_id:
        raise WebhookAuthenticationError(
            "GitLab webhook-id missing."
        )

    if not timestamp:
        raise WebhookAuthenticationError(
            "GitLab webhook-timestamp "
            "missing."
        )

    if not signature:
        raise WebhookAuthenticationError(
            "GitLab webhook-signature "
            "missing."
        )

    try:
        timestamp_value = int(
            timestamp
        )

    except ValueError as exc:
        raise WebhookAuthenticationError(
            "Invalid GitLab timestamp."
        ) from exc

    age = abs(
        int(time.time())
        - timestamp_value
    )

    if age > maximum_age_seconds:
        raise WebhookAuthenticationError(
            "GitLab webhook exceeded "
            "the replay window."
        )

    token_value = signing_token

    if token_value.startswith(
        "whsec_"
    ):
        token_value = (
            token_value[6:]
        )

    try:
        raw_key = base64.b64decode(
            token_value,
            validate=True,
        )

    except Exception as exc:
        raise WebhookAuthenticationError(
            "Invalid GitLab signing token."
        ) from exc

    message = (
        f"{webhook_id}."
        f"{timestamp}."
    ).encode("utf-8") + body

    digest = hmac.new(
        raw_key,
        message,
        hashlib.sha256,
    ).digest()

    expected = (
        "v1,"
        + base64.b64encode(
            digest
        ).decode("ascii")
    )

    received = (
        signature.split()
    )

    if not any(
        hmac.compare_digest(
            expected,
            item,
        )
        for item in received
    ):
        raise WebhookAuthenticationError(
            "GitLab signature invalid."
        )


def verify_gitlab_secret_token(
    *,
    secret: str,
    supplied_token: str | None,
) -> None:
    if not supplied_token:
        raise WebhookAuthenticationError(
            "X-Gitlab-Token missing."
        )

    if not hmac.compare_digest(
        secret,
        supplied_token,
    ):
        raise WebhookAuthenticationError(
            "GitLab token invalid."
        )


def verify_terraform_cloud(
    *,
    secret: str,
    body: bytes,
    signature: str | None,
) -> None:
    if not signature:
        raise WebhookAuthenticationError(
            "HCP Terraform signature "
            "missing."
        )

    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(
        expected,
        signature,
    ):
        raise WebhookAuthenticationError(
            "HCP Terraform signature "
            "invalid."
        )


def verify_topo_hmac(
    *,
    secret: str,
    body: bytes,
    signature: str | None,
) -> None:
    if not signature:
        raise WebhookAuthenticationError(
            "Topo webhook signature "
            "missing."
        )

    expected = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(
        expected,
        signature,
    ):
        raise WebhookAuthenticationError(
            "Topo webhook signature "
            "invalid."
        )


def verify_basic_auth(
    *,
    username: str,
    secret: str,
    authorization: str | None,
) -> None:
    if (
        not authorization
        or not authorization.startswith(
            "Basic "
        )
    ):
        raise WebhookAuthenticationError(
            "Basic authentication "
            "missing."
        )

    try:
        decoded = (
            base64.b64decode(
                authorization[6:]
            )
            .decode("utf-8")
        )

    except Exception as exc:
        raise WebhookAuthenticationError(
            "Malformed Basic Auth."
        ) from exc

    supplied_user, separator, supplied_secret = (
        decoded.partition(":")
    )

    if not separator:
        raise WebhookAuthenticationError(
            "Malformed Basic Auth."
        )

    valid = (
        hmac.compare_digest(
            supplied_user,
            username,
        )
        and hmac.compare_digest(
            supplied_secret,
            secret,
        )
    )

    if not valid:
        raise WebhookAuthenticationError(
            "Basic Auth invalid."
        )