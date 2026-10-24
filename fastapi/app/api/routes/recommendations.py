from fastapi import APIRouter, Depends, Request

from app.core.errors import ServiceError
from app.core.security import require_key
from app.schemas.requests import RankRequest
from app.schemas.responses import ERROR_RESPONSES, RankResponse

router = APIRouter(
    prefix="/api/v1/recommendations", tags=["recommendations"], dependencies=[Depends(require_key)]
)


@router.post("/rank", responses=ERROR_RESPONSES)
async def rank(body: RankRequest, request: Request) -> RankResponse:
    """Return all candidates ranked by cosine; recommend at most topK within the configured distance."""
    request.state.request_id = body.requestId
    if not request.app.state.ready:
        raise ServiceError(503, "MODEL_NOT_READY", "Model is not ready")
    try:
        return await request.app.state.runner.run(body)
    except ServiceError:
        raise
    except Exception:
        raise ServiceError(500, "INTERNAL_ERROR", "Internal service error") from None
