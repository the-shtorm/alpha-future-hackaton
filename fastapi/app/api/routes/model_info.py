from fastapi import APIRouter, Depends, Request

from app.core.config import VERSIONS
from app.core.security import require_key
from app.schemas.responses import ERROR_RESPONSES, ModelInfo

router = APIRouter(prefix="/api/v1", tags=["model"], dependencies=[Depends(require_key)])


@router.get("/model-info", responses=ERROR_RESPONSES)
async def model_info(request: Request) -> ModelInfo:
    encoder = request.app.state.runner.ranker.encoder
    return ModelInfo(
        **{
            "modelId": encoder.model_id,
            "modelRevision": encoder.revision,
            "dimension": encoder.dimension,
            "maxSeqLength": 512,
            "device": "cpu",
            **VERSIONS,
        }
    )
