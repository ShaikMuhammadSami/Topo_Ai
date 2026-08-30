from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.action_approvals import router as action_approvals_router
from app.api.agents import admin_router as agents_router
from app.api.agents import agent_router as agent_runtime_router
from app.api.automation import router as automation_router
from app.api.auth import router as auth_router
from app.api.blast_radius import router as blast_radius_router
from app.api.causal_rca import incident_router as causal_incident_router
from app.api.causal_rca import router as causal_analysis_router
from app.api.change_events import incident_router as incident_change_events_router
from app.api.change_events import router as change_events_router
from app.api.change_source_webhooks import router as change_source_webhooks_router
from app.api.change_sources import router as change_sources_router
from app.api.changes import router as changes_router
from app.api.clouds import router as clouds_router
from app.api.execution_intents import router as execution_intents_router
from app.api.execution_readiness import router as execution_readiness_router
from app.api.github import router as github_router
from app.api.identities import router as identities_router
from app.api.incident_briefing import router as incident_briefing_router
from app.api.incident_context import router as incident_context_router
from app.api.incident_copilot import router as incident_copilot_router
from app.api.incident_explanations import router as incident_explanations_router
from app.api.incident_memory import router as incident_memory_router
from app.api.incident_outcome import router as incident_outcome_router
from app.api.incident_records import router as incident_records_router
from app.api.incidents import router as incidents_router
from app.api.investigation_plans import router as investigation_plans_router
from app.api.kubernetes import router as kubernetes_router
from app.api.network_dependencies import router as network_dependencies_router
from app.api.orchestration import router as orchestration_router
from app.api.ownership import router as ownership_router
from app.api.post_incident_reports import router as post_incident_reports_router
from app.api.predeployment import router as predeployment_router
from app.api.recommendations import router as recommendations_router
from app.api.recovery import router as recovery_router
from app.api.response_intelligence import router as response_intelligence_router
from app.api.response_plan import router as response_plan_router
from app.api.signals import router as signals_router
from app.api.snapshots import router as snapshots_router
from app.api.system import router as system_router
from app.api.tenants import router as tenants_router
from app.api.topology import router as topology_router
from app.api.webhooks import router as webhooks_router
from app.db.database import DATABASE_URL, SessionLocal, init_db
from app.security.api_tokens import ApiTokenAuthMiddleware
from app.security.auth_config import (
    AuthConfiguration,
    AuthConfigurationError,
    AuthConfigurationFailure,
    AuthMode,
    load_auth_configuration,
)
from app.services.auth_api_credential_service import (
    has_active_human_admin_credential,
)


LOGGER = logging.getLogger(__name__)


load_dotenv()


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.ready = False
    application.state.database_initializer()
    configuration = application.state.auth_configuration
    if (
        configuration.mode is AuthMode.REQUIRED
        and not configuration.token_registry
    ):
        with application.state.session_factory() as session:
            if not has_active_human_admin_credential(session):
                raise AuthConfigurationError(
                    AuthConfigurationFailure.EMPTY_REQUIRED_AUTHORITY,
                    (
                        "required mode needs a valid static bootstrap mapping "
                        "or an active durable human admin API credential."
                    ),
                )
    application.state.ready = True
    try:
        yield
    finally:
        application.state.ready = False


def create_app(
    *,
    auth_configuration: AuthConfiguration | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    database_initializer: Callable[[], None] | None = None,
) -> FastAPI:
    configuration = auth_configuration or load_auth_configuration(
        database_url=DATABASE_URL
    )
    for warning in configuration.operator_warnings:
        LOGGER.warning("%s", warning)

    development_docs = configuration.mode is AuthMode.DEVELOPMENT_DISABLED
    application = FastAPI(
        title="Topo AI API",
        description="Evidence-based infrastructure intelligence backend",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url="/openapi.json" if development_docs else None,
        docs_url="/docs" if development_docs else None,
        redoc_url="/redoc" if development_docs else None,
    )
    application.state.auth_configuration = configuration
    application.state.session_factory = session_factory
    application.state.database_initializer = database_initializer or init_db
    application.state.ready = False

    application.add_middleware(
        ApiTokenAuthMiddleware,
        configuration=configuration,
        session_factory=session_factory,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(configuration.browser_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            "X-Topo-CSRF",
            "X-Topo-Tenant-ID",
        ],
    )

    application.include_router(topology_router)
    application.include_router(kubernetes_router)
    application.include_router(snapshots_router)
    application.include_router(identities_router)
    application.include_router(github_router)
    application.include_router(signals_router)
    application.include_router(changes_router)
    application.include_router(incidents_router)
    application.include_router(recommendations_router)
    application.include_router(recovery_router)
    application.include_router(orchestration_router)
    application.include_router(incident_records_router)
    application.include_router(blast_radius_router)
    application.include_router(predeployment_router)
    application.include_router(ownership_router)
    application.include_router(webhooks_router)
    application.include_router(network_dependencies_router)
    application.include_router(incident_explanations_router)
    application.include_router(incident_copilot_router)
    application.include_router(investigation_plans_router)
    application.include_router(post_incident_reports_router)
    application.include_router(auth_router)
    application.include_router(tenants_router)
    application.include_router(system_router)
    application.include_router(agents_router)
    application.include_router(agent_runtime_router)
    application.include_router(clouds_router)
    application.include_router(change_events_router)
    application.include_router(incident_change_events_router)
    application.include_router(change_sources_router)
    application.include_router(change_source_webhooks_router)
    application.include_router(causal_incident_router)
    application.include_router(causal_analysis_router)
    application.include_router(incident_context_router)
    application.include_router(response_plan_router)
    application.include_router(incident_outcome_router)
    application.include_router(incident_memory_router)
    application.include_router(response_intelligence_router)
    application.include_router(incident_briefing_router)
    application.include_router(execution_readiness_router)
    application.include_router(action_approvals_router)
    application.include_router(execution_intents_router)
    application.include_router(automation_router)

    @application.get(
        "/health",
        tags=["system"],
        include_in_schema=False,
    )
    def health() -> dict[str, str]:
        return {
            "status": "available",
            "service": "Topo AI",
            "version": "0.1.0",
        }

    @application.get(
        "/ready",
        tags=["system"],
        include_in_schema=False,
        response_model=None,
    )
    def ready(request: Request):
        if bool(getattr(request.app.state, "ready", False)):
            return {"status": "ready"}
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready"},
        )

    return application


app = create_app()
