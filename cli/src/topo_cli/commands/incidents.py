from __future__ import annotations

import typer

from topo_cli.commands.blast_radius import (
    display_blast_radius,
)
from topo_cli.commands.explanations import (
    generate_and_display,
)
from topo_cli.output import (
    ColumnSpec,
    emit_json,
    render_data,
    render_records,
    OutputFormat,
)
from topo_cli.runtime import (
    api_call,
    collect_pages,
    get_runtime,
)


app = typer.Typer(
    help="List and inspect incidents.",
    no_args_is_help=True,
)


def _contains(
    value: object,
    query: str,
) -> bool:
    return (
        query.lower()
        in str(value).lower()
    )


@app.command("list")
def list_incidents(
    context: typer.Context,
    limit: int = typer.Option(
        50,
        min=1,
        max=1000,
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by incident status.",
    ),
    severity: str | None = typer.Option(
        None,
        "--severity",
        help="Filter by severity.",
    ),
    search: str | None = typer.Option(
        None,
        "--search",
        "-s",
        help=(
            "Search incident ID, title, "
            "summary or entity."
        ),
    ),
    all_pages: bool = typer.Option(
        False,
        "--all",
        help="Retrieve every available page.",
    ),
    page_size: int = typer.Option(
       100,
       "--page-size",
       min=1,
       max=100,
    ),
    maximum_items: int | None = (
        typer.Option(
            None,
            "--max-items",
            min=1,
            help=(
               "Stop after this many records "
               "when using --all."
            ),
        )
    ),
) -> None:
    runtime = get_runtime(context) 
    if all_pages:
     incidents = collect_pages(
         lambda offset, size:
             runtime.client.list_incidents(
                 limit=size,
                 offset=offset,
                ),
         page_size=page_size,
         maximum_items=maximum_items,
        )
    
    else:
        incidents = api_call(
         lambda:
             runtime.client.list_incidents(
                 limit=limit,
                 offset = 0,
                )
        )
    
       
    if status:
        incidents = [
            incident
            for incident in incidents
            if _contains(
                incident.get("status"),
                status,
            )
        ]

    if severity:
        incidents = [
            incident
            for incident in incidents
            if _contains(
                incident.get("severity"),
                severity,
            )
        ]

    if search:
        incidents = [
            incident
            for incident in incidents
            if any(
                _contains(
                    incident.get(field),
                    search,
                )
                for field in (
                    "incident_id",
                    "title",
                    "summary",
                    "affected_object_name",
                    "affected_entity_id",
                )
            )
        ]

    if (
        runtime.output_format.value
        == "json"
    ):
        emit_json(incidents)
        return

    render_records(
        incidents,
        title="Topo Incidents",
        columns=[
            ColumnSpec(
                "SEVERITY",
                ("severity",),
            ),
            ColumnSpec(
                "STATUS",
                ("status",),
            ),
            ColumnSpec(
                "TITLE",
                (
                    "title",
                    "summary",
                ),
                max_width=50,
            ),
            ColumnSpec(
                "AFFECTED ENTITY",
                (
                    "affected_object_name",
                    "affected_entity_name",
                    "affected_entity_id",
                ),
                max_width=45,
            ),
            ColumnSpec(
                "LAST OBSERVED",
                (
                    "last_observed_at",
                    "updated_at",
                ),
            ),
            ColumnSpec(
                "INCIDENT ID",
                ("incident_id",),
                max_width=70,
            ),
        ],
    )


@app.command("get")
def get_incident(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    incident = api_call(
        lambda:
            runtime.client.get_incident(
                incident_id
            )
    )

    render_data(
        incident,
        output_format=(
            runtime.output_format
        ),
        title="Incident Detail",
    )


@app.command("blast-radius")
def incident_blast_radius(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
) -> None:
    display_blast_radius(
        context,
        incident_id,
    )


@app.command("operational-context")
def operational_context(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .incident_operational_context(
                incident_id
            )
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    ownership = result.get(
        "root_cause_ownership"
    )

    if not isinstance(ownership, dict):
        ownership = {}

    impact = result.get(
        "overall_business_impact"
    )

    if not isinstance(impact, dict):
        impact = {}

    resolved_count = impact.get(
        "resolved_entity_count"
    )
    unresolved_count = impact.get(
        "unresolved_entity_count"
    )

    summary = {
        "Root Cause": result.get(
            "root_event_title"
        ),
        "Root Source": result.get(
            "root_event_source"
        ),
        "Causal Confidence": result.get(
            "causal_confidence"
        ),
        "Root Entity": result.get(
            "root_entity_id"
        ),
        "Root Owner Team": ownership.get(
            "owner_team"
        ),
        "Owner Email": ownership.get(
            "owner_email"
        ),
        "On-call": ownership.get(
            "oncall_contact"
        ),
        "Technical Service": ownership.get(
            "service_name"
        ),
        "Repository": ownership.get(
            "repository_url"
        ),
        "Business Capability": ownership.get(
            "business_capability"
        ),
        "Criticality": ownership.get(
            "criticality"
        ),
        "Overall Business Impact": impact.get(
            "business_impact_level"
        ),
        "Affected Teams": impact.get(
            "owner_teams",
            [],
        ),
        "Affected Capabilities": impact.get(
            "business_capabilities",
            [],
        ),
        "Affected Entities": impact.get(
            "affected_entity_count"
        ),
        "Ownership Resolved / Unresolved": (
            f"{resolved_count} / "
            f"{unresolved_count}"
        ),
        "Routing Recommendation": impact.get(
            "routing_recommendation"
        ),
        "Escalation Targets": result.get(
            "escalation_targets",
            [],
        ),
        "Warnings": result.get(
            "warnings",
            [],
        ),
    }

    render_data(
        summary,
        output_format=(
            runtime.output_format
        ),
        title="Incident Operational Context",
    )


@app.command("response-plan")
def response_plan(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client
            .incident_response_plan(
                incident_id
            )
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    root = result.get("root_cause")

    if not isinstance(root, dict):
        root = {}

    owner = result.get("primary_owner")

    if not isinstance(owner, dict):
        owner = {}

    business = result.get(
        "business_context"
    )

    if not isinstance(business, dict):
        business = {}

    summary = {
        "Incident": result.get(
            "incident_id"
        ),
        "Response Priority": result.get(
            "response_priority"
        ),
        "Priority Reason": result.get(
            "response_priority_reason"
        ),
        "Root Cause": root.get(
            "event_title"
        ),
        "Root Source": root.get(
            "event_source"
        ),
        "Root Entity": root.get(
            "entity_id"
        ),
        "Causal Confidence": root.get(
            "causal_confidence"
        ),
        "Target Change": root.get(
            "target_event_title"
        ),
        "Target Change Kind": root.get(
            "target_event_kind"
        ),
        "Primary Owner": owner.get(
            "owner_team"
        ),
        "Owner Email": owner.get(
            "owner_email"
        ),
        "On-call": owner.get(
            "oncall_contact"
        ),
        "Service": owner.get(
            "service_name"
        ),
        "Repository": owner.get(
            "repository_url"
        ),
        "Business Impact": business.get(
            "business_impact_level"
        ),
        "Highest Criticality": business.get(
            "highest_criticality"
        ),
        "Affected Teams": business.get(
            "owner_teams",
            [],
        ),
        "Affected Capabilities": business.get(
            "business_capabilities",
            [],
        ),
        "Affected Entities": business.get(
            "affected_entity_count"
        ),
        "Escalation Targets": result.get(
            "escalation_targets",
            [],
        ),
        "Warnings": result.get(
            "warnings",
            [],
        ),
    }

    render_data(
        summary,
        output_format=(
            runtime.output_format
        ),
        title="Incident Response Plan",
    )

    action_columns = [
        ColumnSpec(
            "#",
            ("sequence",),
        ),
        ColumnSpec(
            "PRIORITY",
            ("priority",),
        ),
        ColumnSpec(
            "CATEGORY",
            ("category",),
        ),
        ColumnSpec(
            "TITLE",
            ("title",),
            max_width=55,
        ),
        ColumnSpec(
            "REASON",
            ("reason",),
            max_width=80,
        ),
        ColumnSpec(
            "RISK",
            ("risk",),
        ),
        ColumnSpec(
            "HUMAN APPROVAL",
            (
                "requires_human_approval",
            ),
        ),
    ]

    actions = result.get(
        "recommended_actions",
        [],
    )

    if isinstance(actions, list) and actions:
        render_records(
            [
                item
                for item in actions
                if isinstance(item, dict)
            ],
            title="Recommended Actions",
            columns=action_columns,
        )

    validation = result.get(
        "validation_checks",
        [],
    )

    if (
        isinstance(validation, list)
        and validation
    ):
        render_records(
            [
                item
                for item in validation
                if isinstance(item, dict)
            ],
            title="Validation Checks",
            columns=action_columns,
        )

    rollback = result.get(
        "rollback_candidate"
    )

    if isinstance(rollback, dict):
        render_data(
            {
                "Available": rollback.get(
                    "available"
                ),
                "Change Event": rollback.get(
                    "change_event_id"
                ),
                "Reason": rollback.get(
                    "reason"
                ),
                "Human Approval Required": (
                    rollback.get(
                        "requires_human_approval"
                    )
                ),
            },
            output_format=(
                runtime.output_format
            ),
            title="Rollback Candidate",
        )

    runbooks = result.get("runbooks", [])

    if isinstance(runbooks, list) and runbooks:
        render_records(
            [
                item
                for item in runbooks
                if isinstance(item, dict)
            ],
            title="Runbooks",
            columns=[
                ColumnSpec(
                    "TITLE",
                    ("title",),
                ),
                ColumnSpec(
                    "URL",
                    ("url",),
                    max_width=100,
                ),
                ColumnSpec(
                    "SOURCE",
                    ("source",),
                ),
            ],
        )


@app.command("outcome")
def incident_outcome(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
) -> None:
    runtime = get_runtime(context)

    result = api_call(
        lambda:
            runtime.client.incident_outcome(
                incident_id
            )
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    original = result.get(
        "original_root_cause"
    )

    if not isinstance(original, dict):
        original = {}

    final = result.get("final_root_cause")

    if not isinstance(final, dict):
        final = {}

    primary = result.get(
        "primary_resolution_action"
    )

    if not isinstance(primary, dict):
        primary = {}

    summary = {
        "Incident": result.get(
            "incident_id"
        ),
        "Outcome Status": result.get(
            "status"
        ),
        "Started": result.get(
            "started_at"
        ),
        "Mitigated": result.get(
            "mitigated_at"
        ),
        "Resolved": result.get(
            "resolved_at"
        ),
        "Time to Mitigation (seconds)": (
            result.get(
                "time_to_mitigation_seconds"
            )
        ),
        "Time to Resolution (seconds)": (
            result.get(
                "time_to_resolution_seconds"
            )
        ),
        "Original Root Cause": (
            original.get("title")
        ),
        "Original Root Event": (
            original.get("event_id")
        ),
        "Original Root Source": (
            original.get("event_source")
        ),
        "Final Root Cause": final.get(
            "title"
        ),
        "Final Root Event": final.get(
            "event_id"
        ),
        "Final Root Source": final.get(
            "event_source"
        ),
        "RCA Verdict": result.get(
            "rca_verdict"
        ),
        "RCA Confidence": result.get(
            "rca_confidence"
        ),
        "Primary Resolution Action": (
            primary.get("title")
        ),
        "Recommendations Followed": (
            result.get(
                "recommendations_followed",
                [],
            )
        ),
        "Recommendations Not Followed": (
            result.get(
                "recommendations_not_followed",
                [],
            )
        ),
        "Recommendations Unknown": (
            result.get(
                "recommendations_unknown",
                [],
            )
        ),
        "Effective Actions": result.get(
            "effective_action_ids",
            [],
        ),
        "Ineffective Actions": result.get(
            "ineffective_action_ids",
            [],
        ),
        "Resolution Summary": result.get(
            "resolution_summary"
        ),
        "Evidence Events": result.get(
            "evidence_event_ids",
            [],
        ),
        "Evidence": result.get(
            "evidence_ids",
            [],
        ),
        "Warnings": result.get(
            "warnings",
            [],
        ),
    }

    render_data(
        summary,
        output_format=(
            runtime.output_format
        ),
        title="Incident Outcome",
    )

    actions = result.get(
        "actions_taken",
        [],
    )

    if isinstance(actions, list) and actions:
        render_records(
            [
                item
                for item in actions
                if isinstance(item, dict)
            ],
            title="Actions Taken",
            columns=[
                ColumnSpec(
                    "ACTION",
                    ("title",),
                    max_width=55,
                ),
                ColumnSpec(
                    "TYPE",
                    ("action_type",),
                ),
                ColumnSpec(
                    "ACTOR",
                    ("actor",),
                ),
                ColumnSpec(
                    "RESULT",
                    ("result",),
                ),
                ColumnSpec(
                    "EFFECTIVENESS",
                    ("effectiveness",),
                ),
                ColumnSpec(
                    "COMPLETED",
                    ("completed_at",),
                ),
                ColumnSpec(
                    "PLAN ACTION",
                    (
                        "response_plan_action_id",
                    ),
                    max_width=55,
                ),
            ],
        )

    plan_actions = result.get(
        "response_plan_actions",
        [],
    )

    if (
        isinstance(plan_actions, list)
        and plan_actions
    ):
        render_records(
            [
                item
                for item in plan_actions
                if isinstance(item, dict)
            ],
            title=(
                "Response Plan Follow-through"
            ),
            columns=[
                ColumnSpec(
                    "ACTION",
                    ("title",),
                    max_width=55,
                ),
                ColumnSpec(
                    "CATEGORY",
                    ("category",),
                ),
                ColumnSpec(
                    "FOLLOW-THROUGH",
                    ("follow_through",),
                ),
                ColumnSpec(
                    "EFFECTIVENESS",
                    ("effectiveness",),
                ),
                ColumnSpec(
                    "REASON",
                    ("reason",),
                    max_width=80,
                ),
            ],
        )


@app.command("response-intelligence")
def response_intelligence(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    history_limit: int = typer.Option(
        5,
        "--history-limit",
        min=1,
        max=20,
        help="Maximum historical matches.",
    ),
    min_similarity: float = typer.Option(
        0.5,
        "--min-similarity",
        min=0.0,
        max=1.0,
        help=(
            "Minimum deterministic similarity "
            "score."
        ),
    ),
    include_ai: bool = typer.Option(
        False,
        "--ai/--no-ai",
        help=(
            "Add one optional OpenAI explanation "
            "after deterministic analysis."
        ),
    ),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda:
            runtime.client
            .incident_response_intelligence(
                incident_id,
                history_limit=history_limit,
                min_similarity=(
                    min_similarity
                ),
                include_ai=include_ai,
            )
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    plan = result.get(
        "baseline_response_plan"
    )

    if not isinstance(plan, dict):
        plan = {}

    root = plan.get("root_cause")

    if not isinstance(root, dict):
        root = {}

    render_data(
        {
            "Incident": result.get(
                "incident_id"
            ),
            "Response Priority": result.get(
                "response_priority"
            ),
            "Overall Historical Support": (
                result.get(
                    "overall_historical_support"
                )
            ),
            "Root Cause": root.get(
                "event_title"
            ),
            "Causal Confidence": root.get(
                "causal_confidence"
            ),
            "Deterministic Summary": result.get(
                "deterministic_summary"
            ),
            "AI Summary": result.get(
                "ai_summary"
            ),
            "AI Status": result.get(
                "ai_status"
            ),
            "Warnings": result.get(
                "warnings",
                [],
            ),
        },
        output_format=(
            runtime.output_format
        ),
        title=(
            "Incident Response Intelligence"
        ),
    )

    rows = []
    raw_actions = result.get("actions", [])

    if isinstance(raw_actions, list):
        for action in raw_actions:
            if not isinstance(action, dict):
                continue

            support = action.get(
                "historical_support"
            )

            if not isinstance(support, dict):
                support = {}

            rows.append(
                {
                    "rank": action.get(
                        "baseline_rank"
                    ),
                    "group": action.get(
                        "baseline_group"
                    ),
                    "title": action.get("title"),
                    "priority": action.get(
                        "priority"
                    ),
                    "family": action.get(
                        "action_family"
                    ),
                    "risk": action.get("risk"),
                    "approval": action.get(
                        "requires_human_approval"
                    ),
                    "current_evidence": (
                        action.get(
                            "current_evidence_strength"
                        )
                    ),
                    "historical_support": (
                        support.get("level")
                    ),
                    "similar_cases": support.get(
                        "similar_incident_count"
                    ),
                    "observed": support.get(
                        "action_observed_count"
                    ),
                    "effective": support.get(
                        "effective_count"
                    ),
                    "ineffective": support.get(
                        "ineffective_count"
                    ),
                    "support_reasons": support.get(
                        "support_reasons",
                        [],
                    ),
                    "cautions": support.get(
                        "caution_reasons",
                        [],
                    ),
                }
            )

    if rows:
        render_records(
            rows,
            title="Action Support",
            columns=[
                ColumnSpec("#", ("rank",)),
                ColumnSpec("GROUP", ("group",)),
                ColumnSpec(
                    "TITLE",
                    ("title",),
                    max_width=50,
                ),
                ColumnSpec(
                    "PRIORITY",
                    ("priority",),
                ),
                ColumnSpec(
                    "FAMILY",
                    ("family",),
                ),
                ColumnSpec("RISK", ("risk",)),
                ColumnSpec(
                    "HUMAN APPROVAL",
                    ("approval",),
                ),
                ColumnSpec(
                    "CURRENT EVIDENCE",
                    ("current_evidence",),
                ),
                ColumnSpec(
                    "HISTORICAL SUPPORT",
                    ("historical_support",),
                ),
                ColumnSpec(
                    "SIMILAR",
                    ("similar_cases",),
                ),
                ColumnSpec(
                    "OBSERVED",
                    ("observed",),
                ),
                ColumnSpec(
                    "EFFECTIVE",
                    ("effective",),
                ),
                ColumnSpec(
                    "INEFFECTIVE",
                    ("ineffective",),
                ),
                ColumnSpec(
                    "WHY HISTORY SUPPORTS IT",
                    ("support_reasons",),
                    max_width=70,
                ),
                ColumnSpec(
                    "CAUTIONS",
                    ("cautions",),
                    max_width=70,
                ),
            ],
        )

    rollback = result.get(
        "rollback_candidate"
    )

    if isinstance(rollback, dict):
        baseline = rollback.get("baseline")
        support = rollback.get(
            "historical_support"
        )

        if not isinstance(baseline, dict):
            baseline = {}

        if not isinstance(support, dict):
            support = {}

        render_data(
            {
                "Baseline Available": baseline.get(
                    "available"
                ),
                "Change Event": baseline.get(
                    "change_event_id"
                ),
                "Human Approval Required": (
                    baseline.get(
                        "requires_human_approval"
                    )
                ),
                "Historical Support": support.get(
                    "level"
                ),
                "Historical Score": support.get(
                    "score"
                ),
                "Supporting Incidents": (
                    support.get(
                        "supporting_incident_ids",
                        [],
                    )
                ),
                "Contradicting Incidents": (
                    support.get(
                        "contradicting_incident_ids",
                        [],
                    )
                ),
                "Cautions": support.get(
                    "caution_reasons",
                    [],
                ),
            },
            output_format=(
                runtime.output_format
            ),
            title="Rollback Candidate",
        )

    patterns = result.get(
        "historical_resolution_patterns",
        [],
    )

    if isinstance(patterns, list) and patterns:
        render_records(
            [
                item
                for item in patterns
                if isinstance(item, dict)
            ],
            title=(
                "Historical Resolution Patterns"
            ),
            columns=[
                ColumnSpec(
                    "ACTION TYPE",
                    ("action_type",),
                ),
                ColumnSpec(
                    "OBSERVED",
                    ("observed_cases",),
                ),
                ColumnSpec(
                    "EFFECTIVE",
                    ("effective_cases",),
                ),
                ColumnSpec(
                    "INEFFECTIVE",
                    ("ineffective_cases",),
                ),
                ColumnSpec(
                    "UNKNOWN",
                    (
                        "unknown_effectiveness_cases",
                    ),
                ),
            ],
        )


@app.command("history")
def incident_history(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        min=1,
        max=20,
        help="Maximum historical matches.",
    ),
    min_similarity: float = typer.Option(
        0.25,
        "--min-similarity",
        min=0.0,
        max=1.0,
        help=(
            "Minimum deterministic similarity "
            "score."
        ),
    ),
    include_ai: bool = typer.Option(
        False,
        "--ai/--no-ai",
        help=(
            "Add one optional OpenAI summary "
            "after deterministic matching."
        ),
    ),
) -> None:
    runtime = get_runtime(context)
    result = api_call(
        lambda:
            runtime.client
            .incident_historical_intelligence(
                incident_id,
                limit=limit,
                min_similarity=(
                    min_similarity
                ),
                include_ai=include_ai,
            )
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    analysis = result.get(
        "analysis_context"
    )

    if not isinstance(analysis, dict):
        analysis = {}

    render_data(
        {
            "Incident": result.get(
                "incident_id"
            ),
            "Historical Support": result.get(
                "historical_support_level"
            ),
            "Current Root Cause": analysis.get(
                "root_event_title"
            ),
            "Root Entity": analysis.get(
                "root_entity_id"
            ),
            "Root Service": analysis.get(
                "root_service_name"
            ),
            "Causal Change Kind": analysis.get(
                "causal_change_kind"
            ),
            "Business Capability": analysis.get(
                "business_capability"
            ),
            "Summary": result.get("summary"),
            "AI Historical Summary": result.get(
                "ai_summary"
            ),
            "AI Status": result.get(
                "ai_status"
            ),
            "Warnings": result.get(
                "warnings",
                [],
            ),
        },
        output_format=(
            runtime.output_format
        ),
        title=(
            "Incident Historical Intelligence"
        ),
    )

    raw_matches = result.get("matches", [])
    match_rows = []

    if isinstance(raw_matches, list):
        for item in raw_matches:
            if not isinstance(item, dict):
                continue

            resolution = item.get(
                "resolution"
            )

            if not isinstance(resolution, dict):
                resolution = {}

            action = resolution.get(
                "primary_resolution_action"
            )

            if not isinstance(action, dict):
                action = {}

            match_rows.append(
                {
                    "incident_id": item.get(
                        "incident_id"
                    ),
                    "similarity": item.get(
                        "similarity_score"
                    ),
                    "why": item.get(
                        "matched_factors",
                        [],
                    ),
                    "differences": item.get(
                        "differing_factors",
                        [],
                    ),
                    "verdict": resolution.get(
                        "rca_verdict"
                    ),
                    "resolution": action.get(
                        "title"
                    ) or resolution.get(
                        "resolution_summary"
                    ),
                    "effectiveness": action.get(
                        "effectiveness"
                    ),
                    "mitigation_seconds": (
                        resolution.get(
                            "time_to_mitigation_seconds"
                        )
                    ),
                    "resolution_seconds": (
                        resolution.get(
                            "time_to_resolution_seconds"
                        )
                    ),
                }
            )

    if match_rows:
        render_records(
            match_rows,
            title="Historical Matches",
            columns=[
                ColumnSpec(
                    "INCIDENT ID",
                    ("incident_id",),
                    max_width=45,
                ),
                ColumnSpec(
                    "SIMILARITY",
                    ("similarity",),
                ),
                ColumnSpec(
                    "WHY IT MATCHES",
                    ("why",),
                    max_width=65,
                ),
                ColumnSpec(
                    "DIFFERENCES",
                    ("differences",),
                    max_width=65,
                ),
                ColumnSpec(
                    "RCA VERDICT",
                    ("verdict",),
                ),
                ColumnSpec(
                    "RESOLUTION",
                    ("resolution",),
                    max_width=55,
                ),
                ColumnSpec(
                    "EFFECTIVENESS",
                    ("effectiveness",),
                ),
                ColumnSpec(
                    "MITIGATION (S)",
                    ("mitigation_seconds",),
                ),
                ColumnSpec(
                    "RESOLUTION (S)",
                    ("resolution_seconds",),
                ),
            ],
        )

    patterns = result.get(
        "resolution_patterns",
        [],
    )

    if isinstance(patterns, list) and patterns:
        render_records(
            [
                item
                for item in patterns
                if isinstance(item, dict)
            ],
            title="Resolution Patterns",
            columns=[
                ColumnSpec(
                    "ACTION TYPE",
                    ("action_type",),
                ),
                ColumnSpec(
                    "OBSERVED",
                    ("observed_cases",),
                ),
                ColumnSpec(
                    "EFFECTIVE",
                    ("effective_cases",),
                ),
                ColumnSpec(
                    "INEFFECTIVE",
                    ("ineffective_cases",),
                ),
                ColumnSpec(
                    "UNKNOWN",
                    (
                        "unknown_effectiveness_cases",
                    ),
                ),
                ColumnSpec(
                    "INCIDENTS",
                    (
                        "supporting_incident_ids",
                    ),
                    max_width=60,
                ),
            ],
        )


@app.command("explain")
def explain_incident(
    context: typer.Context,
    incident_id: str = typer.Argument(
        help="Stable incident ID.",
    ),
    provider: str = typer.Option(
        "auto",
        "--provider",
    ),
    force_regenerate: bool = typer.Option(
        False,
        "--force",
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

@app.command("change-events")
def incident_change_events(
    context: typer.Context,

    incident_id: str = typer.Argument(
        ...,
    ),

    lookback_minutes: int = typer.Option(
        120,
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

    limit: int = typer.Option(
        100,
        "--limit",
        min=1,
        max=1000,
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    result = api_call(
        lambda:
            runtime.client
            .get_incident_change_events(
                incident_id=incident_id,
                lookback_minutes=(
                    lookback_minutes
                ),
                after_minutes=(
                    after_minutes
                ),
                limit=limit,
            )
    )

    render_data(
        result,
        output_format=(
            runtime.output_format
        ),
        title=(
            "Incident Change Events"
        ),
    )


@app.command("suspected-changes")
def suspected_changes(
    context: typer.Context,

    incident_id: str = typer.Argument(
        ...,
    ),

    lookback_minutes: int = typer.Option(
        120,
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

    minimum_score: float = typer.Option(
        25,
        "--minimum-score",
        min=0,
        max=100,
    ),

    limit: int = typer.Option(
        20,
        "--limit",
        min=1,
        max=100,
    ),
) -> None:
    runtime = get_runtime(
        context
    )

    result = api_call(
        lambda:
            runtime.client
            .get_suspected_change_events(
                incident_id=incident_id,
                lookback_minutes=(
                    lookback_minutes
                ),
                after_minutes=(
                    after_minutes
                ),
                minimum_score=(
                    minimum_score
                ),
                limit=limit,
            )
    )

    if (
        runtime.output_format
        == OutputFormat.JSON
    ):
        emit_json(result)
        return

    raw_values = result.get(
     "candidates",
     [],
    )

    values = []

    for candidate in raw_values:
        event = candidate.get(
          "event",
          {},
        )
        if not isinstance(
           event,
           dict,
        ):event = {}

        values.append(
         {
             "score":
                 candidate.get(
                     "score"
                    ),

             "minutes":
                 candidate.get(
                     "minutes_before_incident"
                    ),

             "source":
                 event.get(
                     "source"
                    ),

             "kind":
                 event.get(
                     "kind"
                    ),

             "risk_score":
                 event.get(
                     "risk_score"
                    ),

             "risk_level":
                 event.get(
                     "risk_level"
                    ),

             "title":
                 event.get(
                     "title"
                    ),

             "event_id":
                 event.get(
                     "event_id"
                ),
            }
        )

    render_records(
        values,
        title="Suspected Changes",
        columns=[
            ColumnSpec(
                "SCORE",
                ("score",),
            ),
            ColumnSpec(
                "MINUTES",
                (
                    "minutes",
                ),
            ),
            ColumnSpec(
                "SOURCE",
                (
                    "source",
                ),
            ),
            ColumnSpec(
                "KIND",
                (
                    "kind",
                ),
            ),
            ColumnSpec(
                "RISK",
                (
                    "risk_score",
                ),
            ),
            ColumnSpec(
                "TITLE",
                (
                    "title",
                ),
                max_width=55,
            ),
            ColumnSpec(
                "EVENT ID",
                (
                    "event_id",
                ),
                max_width=55,
            ),
        ],
    )
