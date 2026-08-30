from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends
from fastapi import APIRouter, HTTPException, Query
from kubernetes.client.exceptions import ApiException

from app.collectors.kubernetes_collector import (
    KubernetesCollector,
)
from app.models.topology import GraphSnapshot

router = APIRouter(
    prefix="/api/v1/kubernetes",
    tags=["kubernetes"],
)


@router.get("/connection")
def check_kubernetes_connection(
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> dict:
    """
    Verify that the backend can reach the configured Kubernetes cluster.
    """
    try:
        collector = KubernetesCollector()

        return collector.connection_information()

    except ApiException as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Kubernetes API error "
                f"{exc.status}: {exc.reason}"
            ),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/discover",
    response_model=GraphSnapshot,
)
def discover_kubernetes_topology(
    namespace: str | None = Query(
        default=None,
        description=(
            "Optional namespace filter. " "Leave empty to discover all namespaces."
        ),
    ),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> GraphSnapshot:
    """
    Read Kubernetes resources and return a canonical graph snapshot.
    """
    try:
        collector = KubernetesCollector(
            namespace=namespace,
        )

        return collector.collect()

    except ApiException as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Kubernetes API error "
                f"{exc.status}: {exc.reason}"
            ),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
