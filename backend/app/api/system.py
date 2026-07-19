from fastapi import (
    APIRouter,
    HTTPException,
    Request,
)

from app.security.api_tokens import (
    AuthPrincipal,
)


router = APIRouter(
    prefix="/api/v1/system",
    tags=["system"],
)


@router.get("/whoami")
def whoami(
    request: Request,
) -> dict[str, object]:
    principal = getattr(
        request.state,
        "principal",
        None,
    )

    if not isinstance(
        principal,
        AuthPrincipal,
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Authentication identity "
                "is unavailable."
            ),
        )

    return {
        "subject":
            principal.subject,
        "display_name":
            principal.display_name,
        "roles":
            list(principal.roles),
        "authentication_type":
            principal
            .authentication_type,
    }