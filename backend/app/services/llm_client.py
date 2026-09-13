from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from openai import OpenAI
from groq import Groq
from pydantic import BaseModel

from app.security.customer_data_policy import ExternalDataSink
from app.security.llm_data_boundary import (
    SafeLLMRequest,
    require_provider_safe_request,
)
from app.services.installation_secrets import (
    installation_secret_is_configured,
    installation_secret_text,
)
from app.security.egress_policy import Resolver, SystemResolver
from app.services.egress_http import groq_http_client, openai_http_client


DEFAULT_OPENAI_MODEL = "gpt-5-mini"

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
    return installation_secret_is_configured("openai")


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
        and installation_secret_is_configured("groq")
    ):
        return "groq"

    if openai_is_configured():
        return "openai"

    return "deterministic"


def _openai_client(
    *,
    resolver: Resolver | None = None,
) -> OpenAI:
    api_key = installation_secret_text("openai")

    if not api_key:
        raise OpenAIConfigurationError(
            "OpenAI installation credential is not configured."
        )

    return OpenAI(
        api_key=api_key,
        timeout=60.0,
        max_retries=2,
        http_client=openai_http_client(resolver=resolver or SystemResolver()),
    )


def create_groq_client(
    *,
    resolver: Resolver | None = None,
) -> Groq:
    api_key = installation_secret_text("groq")
    if not api_key:
        raise OpenAIConfigurationError(
            "Groq installation credential is not configured."
        )
    return Groq(
        api_key=api_key,
        timeout=60.0,
        max_retries=2,
        http_client=groq_http_client(resolver=resolver or SystemResolver()),
    )


def generate_openai_text(
    *,
    system_prompt: str,
    request: SafeLLMRequest,
    model_name: str | None = None,
    max_output_tokens: int = 800,
) -> OpenAITextResult:
    selected_model = (
        model_name
        or configured_openai_model()
    )
    require_provider_safe_request(
        request,
        sink=ExternalDataSink.OPENAI,
    )

    try:
        response = (
            _openai_client()
            .responses.create(
                model=selected_model,
                instructions=system_prompt,
                input=request.customer_context_json,
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
            f"failed ({type(exc).__name__})."
        ) from None

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
    request: SafeLLMRequest,
    response_model: type[ModelT],
    model_name: str | None = None,
    max_output_tokens: int = 3000,
) -> ModelT:
    selected_model = (
        model_name
        or configured_openai_model()
    )
    require_provider_safe_request(
        request,
        sink=ExternalDataSink.OPENAI,
    )

    try:
        response = (
            _openai_client()
            .responses.parse(
                model=selected_model,
                instructions=system_prompt,
                input=request.customer_context_json,
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
            f"failed ({type(exc).__name__})."
        ) from None

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

    except Exception:
        raise OpenAIProviderError(
            "OpenAI returned invalid structured output."
        ) from None


def generate_groq_structured(
    *,
    system_prompt: str,
    request: SafeLLMRequest,
    response_model: type[ModelT],
    schema_name: str,
    model_name: str,
    max_output_tokens: int = 3000,
) -> ModelT:
    require_provider_safe_request(
        request,
        sink=ExternalDataSink.GROQ,
    )
    try:
        response = create_groq_client().chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.customer_context_json},
            ],
            temperature=0,
            max_tokens=max_output_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        )
    except OpenAIProviderError:
        raise
    except Exception as exc:
        raise OpenAIProviderError(
            f"Groq structured request failed ({type(exc).__name__})."
        ) from None

    content = response.choices[0].message.content
    if not content:
        raise OpenAIProviderError("Groq returned an empty response.")
    try:
        return response_model.model_validate_json(content)
    except Exception:
        raise OpenAIProviderError(
            "Groq returned invalid structured output."
        ) from None
