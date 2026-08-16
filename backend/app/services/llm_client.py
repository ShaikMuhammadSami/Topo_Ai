from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    TypeVar,
)

from openai import OpenAI
from pydantic import BaseModel


DEFAULT_OPENAI_MODEL = "gpt-5-mini"

SENSITIVE_KEY_PARTS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "client_secret",
    "cookie",
}

BEARER_PATTERN = re.compile(
    r"(?i)\bBearer\s+"
    r"[A-Za-z0-9._~+/=-]{12,}"
)

ModelT = TypeVar(
    "ModelT",
    bound=BaseModel,
)


class OpenAIProviderError(Exception):
    pass


class OpenAIConfigurationError(
    OpenAIProviderError
):
    pass


@dataclass(frozen=True)
class OpenAITextResult:
    text: str
    model_name: str


def openai_is_configured() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY", "").strip()
    )


def configured_openai_model() -> str:
    value = os.getenv(
        "TOPO_OPENAI_MODEL",
        "",
    ).strip()

    return value or DEFAULT_OPENAI_MODEL


def resolve_configured_provider(
    requested: str,
) -> str:
    normalized = requested.strip().lower()

    if normalized != "auto":
        return normalized

    configured = os.getenv(
        "TOPO_AI_LLM_PROVIDER",
        "openai",
    ).strip().lower()

    if configured == "deterministic":
        return "deterministic"

    if (
        configured == "groq"
        and os.getenv("GROQ_API_KEY", "").strip()
    ):
        return "groq"

    if openai_is_configured():
        return "openai"

    return "deterministic"


def _is_sensitive_key(value: str) -> bool:
    normalized = (
        value.lower()
        .replace("-", "_")
        .replace(".", "_")
    )

    return any(
        part in normalized
        for part in SENSITIVE_KEY_PARTS
    )


def sanitize_untrusted_data(
    value: Any,
    *,
    depth: int = 0,
) -> Any:
    if depth >= 6:
        return str(value)[:500]

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, BaseModel):
        return sanitize_untrusted_data(
            value.model_dump(mode="json"),
            depth=depth + 1,
        )

    if isinstance(value, dict):
        result: dict[str, Any] = {}

        for key, item in list(
            value.items()
        )[:100]:
            key_value = str(key)

            result[key_value] = (
                "[REDACTED]"
                if _is_sensitive_key(
                    key_value
                )
                else sanitize_untrusted_data(
                    item,
                    depth=depth + 1,
                )
            )

        return result

    if isinstance(
        value,
        (list, tuple, set),
    ):
        return [
            sanitize_untrusted_data(
                item,
                depth=depth + 1,
            )
            for item in list(value)[:100]
        ]

    if isinstance(value, str):
        return BEARER_PATTERN.sub(
            "Bearer [REDACTED]",
            value,
        )[:5000]

    return value


def _openai_client() -> OpenAI:
    api_key = os.getenv(
        "OPENAI_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise OpenAIConfigurationError(
            "OPENAI_API_KEY is not configured."
        )

    return OpenAI(
        api_key=api_key,
        timeout=60.0,
        max_retries=2,
    )


def generate_openai_text(
    *,
    system_prompt: str,
    evidence_payload: Any,
    model_name: str | None = None,
    max_output_tokens: int = 800,
) -> OpenAITextResult:
    selected_model = (
        model_name
        or configured_openai_model()
    )
    payload = sanitize_untrusted_data(
        evidence_payload
    )

    try:
        response = (
            _openai_client()
            .responses.create(
                model=selected_model,
                instructions=system_prompt,
                input=json.dumps(
                    {
                        "untrusted_evidence_data": (
                            payload
                        )
                    },
                    sort_keys=True,
                    default=str,
                ),
                max_output_tokens=(
                    max_output_tokens
                ),
                store=False,
            )
        )

    except OpenAIProviderError:
        raise

    except Exception as exc:
        raise OpenAIProviderError(
            "OpenAI Responses API request "
            "failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    text = str(
        getattr(response, "output_text", "")
        or ""
    ).strip()

    if not text:
        raise OpenAIProviderError(
            "OpenAI returned an empty response."
        )

    return OpenAITextResult(
        text=text,
        model_name=selected_model,
    )


def generate_openai_structured(
    *,
    system_prompt: str,
    evidence_payload: Any,
    response_model: type[ModelT],
    model_name: str | None = None,
    max_output_tokens: int = 3000,
) -> ModelT:
    selected_model = (
        model_name
        or configured_openai_model()
    )
    payload = sanitize_untrusted_data(
        evidence_payload
    )

    try:
        response = (
            _openai_client()
            .responses.parse(
                model=selected_model,
                instructions=system_prompt,
                input=json.dumps(
                    {
                        "untrusted_evidence_data": (
                            payload
                        )
                    },
                    sort_keys=True,
                    default=str,
                ),
                text_format=response_model,
                max_output_tokens=(
                    max_output_tokens
                ),
                store=False,
            )
        )

    except OpenAIProviderError:
        raise

    except Exception as exc:
        raise OpenAIProviderError(
            "OpenAI Responses API request "
            "failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    parsed = getattr(
        response,
        "output_parsed",
        None,
    )

    if parsed is None:
        raise OpenAIProviderError(
            "OpenAI returned no structured output."
        )

    if isinstance(parsed, response_model):
        return parsed

    try:
        return response_model.model_validate(
            parsed
        )

    except Exception as exc:
        raise OpenAIProviderError(
            "OpenAI returned invalid structured "
            f"output: {exc}"
        ) from exc
