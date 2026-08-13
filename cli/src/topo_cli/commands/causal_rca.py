from __future__ import annotations

import typer

from topo_cli.output import (
    ColumnSpec,
    OutputFormat,
    emit_json,
    render_data,
    render_records,
)
from topo_cli.runtime import (
    api_call,
    get_runtime,
)


app = typer.Typer(
    help=(
        "Build and inspect "
        "evidence-backed causal RCA."
    ),
    no_args_is_help=True,
)


def _render_analysis(
    runtime,
    result: dict,
) -> None:
    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    top = result.get(
        "top_hypothesis"
    )

    summary = {
        "analysis_id":
            result.get(
                "analysis_id"
            ),

        "incident_id":
            result.get(
                "incident_id"
            ),

        "incident":
            result.get(
                "incident_title"
            ),

        "snapshot":
            result.get(
                "topology_snapshot_id"
            ),

        "candidates":
            result.get(
                "candidate_count"
            ),

        "hypotheses":
            result.get(
                "hypothesis_count"
            ),

        "top_score":
            (
                top.get("score")
                if isinstance(
                    top,
                    dict,
                )
                else None
            ),

        "top_confidence":
            (
                top.get(
                    "confidence"
                )
                if isinstance(
                    top,
                    dict,
                )
                else None
            ),

        "top_root_source":
            (
                top.get(
                    "root_source"
                )
                if isinstance(
                    top,
                    dict,
                )
                else None
            ),

        "top_root_cause":
            (
                top.get(
                    "root_title"
                )
                if isinstance(
                    top,
                    dict,
                )
                else None
            ),
    }

    render_data(
        summary,
        output_format=(
            runtime.output_format
        ),
        title="Causal RCA",
    )

    hypotheses = result.get(
        "hypotheses",
        [],
    )

    if hypotheses:
        values = []

        for item in hypotheses:
            values.append(
                {
                    "rank":
                        item.get(
                            "rank"
                        ),

                    "score":
                        item.get(
                            "score"
                        ),

                    "confidence":
                        item.get(
                            "confidence"
                        ),

                    "level":
                        item.get(
                            "confidence_level"
                        ),

                    "source":
                        item.get(
                            "root_source"
                        ),

                    "root":
                        item.get(
                            "root_title"
                        ),

                    "target":
                        item.get(
                            "target_title"
                        ),
                }
            )

        render_records(
            values,
            title=(
                "Causal Hypotheses"
            ),
            columns=[
                ColumnSpec(
                    "RANK",
                    ("rank",),
                ),
                ColumnSpec(
                    "SCORE",
                    ("score",),
                ),
                ColumnSpec(
                    "CONF",
                    ("confidence",),
                ),
                ColumnSpec(
                    "LEVEL",
                    ("level",),
                ),
                ColumnSpec(
                    "SOURCE",
                    ("source",),
                ),
                ColumnSpec(
                    "ROOT",
                    ("root",),
                    max_width=45,
                ),
                ColumnSpec(
                    "TARGET",
                    ("target",),
                    max_width=45,
                ),
            ],
        )

    if isinstance(
        top,
        dict,
    ):
        chain = top.get(
            "chain",
            [],
        )

        if chain:
            render_records(
                chain,
                title=(
                    "Top Causal Chain"
                ),
                columns=[
                    ColumnSpec(
                        "#",
                        ("order",),
                    ),
                    ColumnSpec(
                        "TYPE",
                        ("node_type",),
                    ),
                    ColumnSpec(
                        "LABEL",
                        ("label",),
                        max_width=60,
                    ),
                    ColumnSpec(
                        "RELATION",
                        (
                            "relation_from_previous",
                        ),
                    ),
                    ColumnSpec(
                        "CONF",
                        (
                            "confidence_from_previous",
                        ),
                    ),
                ],
            )


@app.command("analyze")
def analyze(
    context: typer.Context,

    incident_id: str = typer.Argument(
        ...
    ),

    lookback_minutes: int = typer.Option(
        180,
        "--lookback-minutes",
        min=1,
        max=10080,
    ),

    after_minutes: int = typer.Option(
        10,
        "--after-minutes",
        min=0,
        max=1440,
    ),

    minimum_change_score: float = (
        typer.Option(
            0,
            "--minimum-change-score",
            min=0,
            max=100,
        )
    ),

    max_topology_hops: int = (
        typer.Option(
            4,
            "--max-hops",
            min=0,
            max=10,
        )
    ),

    max_hypotheses: int = typer.Option(
        5,
        "--max-hypotheses",
        min=1,
        max=25,
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    result = api_call(
        lambda:
            runtime.client
            .analyze_causal_rca(
                incident_id=(
                    incident_id
                ),
                lookback_minutes=(
                    lookback_minutes
                ),
                after_minutes=(
                    after_minutes
                ),
                minimum_change_score=(
                    minimum_change_score
                ),
                max_topology_hops=(
                    max_topology_hops
                ),
                max_hypotheses=(
                    max_hypotheses
                ),
            )
    )

    _render_analysis(
        runtime,
        result,
    )


@app.command("latest")
def latest(
    context: typer.Context,

    incident_id: str = typer.Argument(
        ...
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    result = api_call(
        lambda:
            runtime.client
            .latest_causal_rca(
                incident_id=(
                    incident_id
                )
            )
    )

    _render_analysis(
        runtime,
        result,
    )


@app.command("get")
def get_analysis(
    context: typer.Context,

    analysis_id: str = typer.Argument(
        ...
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    result = api_call(
        lambda:
            runtime.client
            .get_causal_analysis(
                analysis_id=(
                    analysis_id
                )
            )
    )

    _render_analysis(
        runtime,
        result,
    )