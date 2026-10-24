from fastapi import APIRouter, Request

from app.core.errors import ServiceError

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, str]:
    if not getattr(request.app.state, "ready", False):
        raise ServiceError(503, "MODEL_NOT_READY", "Model is not ready")
    return {"status": "ready"}
