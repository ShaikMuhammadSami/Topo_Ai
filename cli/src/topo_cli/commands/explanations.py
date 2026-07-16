from __future__ import annotations

import typer

from topo_cli.errors import (
    InputValidationFailure,
    abort,
)
from topo_cli.output import (
    ColumnSpec,
    console,
    emit_json,
    render_detail,
    render_records,
)
from topo_cli.runtime import (
    api_call,
    get_runtime,
)


app = typer.Typer(
    help=(
        "Generate and inspect grounded "
        "incident explanations."
    ),
    no_args_is_help=True,
)


VALID_PROVIDERS = {
    "auto",
    "groq",
    "deterministic",
}


def display_explanation(
    context: typer.Context,
    result: dict,
) -> None:
    runtime = get_runtime(context)

    if (
        runtime.output_format.value
        == "json"
    ):
        emit_json(result)
        return

    metadata = {
        "explanation_id":
            result.get(
                "explanation_id"
            ),
        "incident_id":
            result.get(
                "incident_id"
            ),
        "provider":
            result.get("provider"),
        "model_name":
            result.get("model_name"),
        "confidence":
            result.get("confidence"),
        "prompt_version":
            result.get(
                "prompt_version"
            ),
        "generated_at":
            result.get(
                "generated_at"
            ),
        "evidence_count": len(
            result.get(
                "evidence",
                [],
            )
        ),
    }

    render_detail(
        metadata,
        title="Explanation Metadata",
    )

    explanation = result.get(
        "explanation",
        {},
    )

    if isinstance(
        explanation,
        dict,
    ):
        sections = {
            "executive_summary":
                explanation.get(
                    "executive_summary"
                ),
            "technical_summary":
                explanation.get(
                    "technical_summary"
                ),
            "probable_root_cause":
                explanation.get(
                    "probable_root_cause"
                ),
            "business_impact":
                explanation.get(
                    "business_impact"
                ),
            "uncertainty":
                explanation.get(
                    "uncertainty"
                ),
            "overall_confidence":
                explanation.get(
                    "overall_confidence"
                ),
        }

        render_detail(
            sections,
            title="Incident Explanation",
        )

        claims = explanation.get(
            "claims",
            [],
        )

        if isinstance(claims, list) and claims:
            render_records(
                [
                    item
                    for item in claims
                    if isinstance(
                        item,
                        dict,
                    )
                ],
                title="Grounded Claims",
                columns=[
                    ColumnSpec(
                        "CLAIM",
                        ("text",),
                    ),
                    ColumnSpec(
                        "CONFIDENCE",
                        ("confidence",),
                    ),
                    ColumnSpec(
                        "EVIDENCE",
                        ("evidence_ids",),
                    ),
                ],
            )

    warnings = result.get(
        "warnings",
        [],
    )

    if warnings:
        console.print(
            "\n[bold yellow]"
            "Generation warnings"
            "[/bold yellow]"
        )

        for warning in warnings:
            console.print(
                f"• {warning}"
            )


def generate_and_display(
    context: typer.Context,
    *,
    incident_id: str,
    provider: str,
    force_regenerate: bool,
) -> None:
    normalized_provider = (
        provider.lower().strip()
    )

    if (
        normalized_provider
        not in VALID_PROVIDERS
    ):
        abort(
            InputValidationFailure(
                "Provider must be one of: "
                "auto, groq, deterministic."
            )
        )

    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .generate_explanation(
                incident_id=incident_id,
                provider=(
                    normalized_provider
                ),
                force_regenerate=(
                    force_regenerate
                ),
            )
    )

    display_explanation(
        context,
        result,
    )


@app.command("generate")
def generate_explanation(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    provider: str = typer.Option(
        "auto",
        "--provider",
        help=(
            "auto, groq, or "
            "deterministic"
        ),
    ),
    force_regenerate: bool = typer.Option(
        False,
        "--force",
        help="Ignore cached explanation.",
    ),
) -> None:
    generate_and_display(
        context,
        incident_id=incident_id,
        provider=provider,
        force_regenerate=(
            force_regenerate
        ),
    )


@app.command("latest")
def latest_explanation(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .latest_explanation(
                incident_id
            )
    )

    if result is None:
        console.print(
            "[dim]No explanation has been "
            "generated for this incident.[/dim]"
        )
        return

    display_explanation(
        context,
        result,
    )


@app.command("history")
def explanation_history(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    limit: int = typer.Option(
        20,
        min=1,
        max=100,
    ),
) -> None:
    runtime = get_runtime(context)

    results = api_call(
        lambda:
            runtime.client
            .explanation_history(
                incident_id=incident_id,
                limit=limit,
            )
    )

    if (
        runtime.output_format.value
        == "json"
    ):
        emit_json(results)
        return

    render_records(
        results,
        title="Explanation History",
        columns=[
            ColumnSpec(
                "GENERATED",
                ("generated_at",),
            ),
            ColumnSpec(
                "PROVIDER",
                ("provider",),
            ),
            ColumnSpec(
                "MODEL",
                ("model_name",),
            ),
            ColumnSpec(
                "CONFIDENCE",
                ("confidence",),
            ),
            ColumnSpec(
                "EXPLANATION ID",
                ("explanation_id",),
                max_width=60,
            ),
        ],
    )