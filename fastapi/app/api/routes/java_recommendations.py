from fastapi import APIRouter, Depends, Request

from app.core.errors import ServiceError
from app.core.security import require_bearer
from app.schemas.java_exchange import JavaRankRequest, JavaRankResponse
from app.schemas.responses import ERROR_RESPONSES
from app.services.java_adapter import to_internal, to_java

router = APIRouter(
    prefix="/api/v1/recommendations", tags=["java-exchange"], dependencies=[Depends(require_bearer)]
)


@router.post("/rank-java", responses=ERROR_RESPONSES)
async def rank_java(body: JavaRankRequest, request: Request) -> JavaRankResponse:
    """Java automatic-selection envelope; full applicability conditions echoed unchanged. Up to 100 candidates."""
    request.state.request_id = str(body.requestId)
    if not request.app.state.ready:
        raise ServiceError(503, "MODEL_NOT_READY", "Model is not ready")
    try:
        result = await request.app.state.runner.run(to_internal(body))
        return to_java(body, result)
    except ServiceError:
        raise
    except Exception:
        raise ServiceError(500, "INTERNAL_ERROR", "Internal service error") from None
