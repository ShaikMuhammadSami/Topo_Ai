from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.topology import router as topology_router
from app.api.kubernetes import router as kubernetes_router

from contextlib import asynccontextmanager

from app.db.database import init_db
from app.api.snapshots import router as snapshots_router
from app.api.identities import (
    router as identities_router,
)
from app.api.github import (
    router as github_router,
)
from app.api.signals import (
    router as signals_router,
)
from app.api.changes import (
    router as changes_router,
)
from app.api.incidents import (
    router as incidents_router,
)
from app.api.recommendations import (
    router as recommendations_router,
)
from app.api.recovery import (
    router as recovery_router,
)
from app.api.orchestration import (
    router as orchestration_router,
)
from app.api.incident_records import (
    router as incident_records_router,
)
from app.api.blast_radius import (
    router as blast_radius_router,
)
from app.api.predeployment import (
    router as predeployment_router,
)
from app.api.ownership import (
    router as ownership_router,
)
from app.api.webhooks import (
    router as webhooks_router,
)
from app.api.network_dependencies import (
    router as network_dependencies_router,
)
from app.api.incident_explanations import (
    router as incident_explanations_router,
)
from app.api.incident_copilot import (
    router as incident_copilot_router,
)
from app.api.investigation_plans import (
    router as investigation_plans_router,
)
from app.api.post_incident_reports import (
    router as post_incident_reports_router,
)
from app.api.system import (
    router as system_router,
)
from app.security.api_tokens import (
    ApiTokenAuthMiddleware,
)
from app.api.agents import (
    admin_router as agents_router,
    agent_router as agent_runtime_router,
)
from app.api.clouds import (
    router as clouds_router,
)
from app.api.change_events import (
    incident_router as incident_change_events_router,
    router as change_events_router,
)
from app.api.change_sources import (
    router as change_sources_router,
)
from app.api.change_source_webhooks import (
    router as change_source_webhooks_router,
)
from dotenv import load_dotenv


load_dotenv()
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
app = FastAPI(
    title="Topo AI API",
    description=(
        "Evidence-based infrastructure intelligence backend"
    ),
    version="0.1.0",
    lifespan=lifespan,
)


app.add_middleware(
    ApiTokenAuthMiddleware
)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:3000",
#         "http://127.0.0.1:3000",
#         "http://localhost:5173",
#         "http://127.0.0.1:5173",
#         "https://topo-ai-hxhm.vercel.app",
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


app.include_router(topology_router)
app.include_router(kubernetes_router)
app.include_router(snapshots_router)
app.include_router(identities_router)
app.include_router(github_router)
app.include_router(signals_router)
app.include_router(changes_router)
app.include_router(incidents_router)
app.include_router(
    recommendations_router
)
app.include_router(recovery_router)
app.include_router(
    orchestration_router
)
app.include_router(
    incident_records_router
)
app.include_router(
    blast_radius_router
)
app.include_router(
    predeployment_router
)
app.include_router(
    ownership_router
)
app.include_router(
    webhooks_router
)
app.include_router(
    network_dependencies_router
)
app.include_router(
    incident_explanations_router
)
app.include_router(
    incident_copilot_router
)  
app.include_router(
    investigation_plans_router
)
app.include_router(
    post_incident_reports_router
)
app.include_router(
    system_router
)
app.include_router(
    agents_router
)

app.include_router(
    agent_runtime_router
)
app.include_router(
    clouds_router
)
app.include_router(
    change_events_router
)

app.include_router(
    incident_change_events_router
)

app.include_router(
    change_sources_router
)

app.include_router(
    change_source_webhooks_router
)
# @app.get("/health")
# def health_check() -> dict:
#     return {
#         "status": "healthy",
#         "service": "topo-ai-backend",
#         "version": "0.1.0",
#         "phase": "graph-contract",
#         "timestamp": datetime.now(timezone.utc).isoformat(),
#     }

@app.get(
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