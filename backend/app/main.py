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
from dotenv import load_dotenv


load_dotenv()
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
app = FastAPI(
    title="Topo AI API",
    description=(
        "Evidence-based infrastructure intelligence backend",
    ),
    version="0.1.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://topo-ai-hxhm.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
@app.get("/health")
def health_check() -> dict:
    return {
        "status": "healthy",
        "service": "topo-ai-backend",
        "version": "0.1.0",
        "phase": "graph-contract",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }