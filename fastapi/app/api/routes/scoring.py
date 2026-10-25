import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.core.config import ROOT
from app.core.errors import ServiceError
from app.core.security import require_bearer
from app.schemas.responses import ERROR_RESPONSES
from app.scoring.contracts import ScoringRequest, ScoringResponse
from app.scoring.package import ScoringPackage

router = APIRouter(prefix="/api/v1/scoring", tags=["scoring"], dependencies=[Depends(require_bearer)])


def load_scoring(settings):
    lock = json.loads((ROOT / "config/scoring-model.lock.json").read_text(encoding="utf-8"))
    model = ScoringPackage(Path(settings.scoring_model_path), lock["manifestSha256"])
    if model.manifest.modelVersion != lock["modelVersion"]:
        raise ValueError("Scoring model identity mismatch")
    return model


def require_ready(request):
    if not getattr(request.app.state, "scoring_ready", False):
        raise ServiceError(503, "MODEL_NOT_READY", "Scoring model is not ready")


@router.post("/evaluate", responses=ERROR_RESPONSES)
async def evaluate(payload: ScoringRequest, request: Request) -> ScoringResponse:
    request.state.request_id = str(payload.requestId)
    require_ready(request)
    return await request.app.state.scoring_runner.run(payload)


@router.get("/ready", responses=ERROR_RESPONSES)
async def ready(request: Request) -> dict[str, str]:
    require_ready(request)
    return {"status": "ready"}


@router.get("/model-info", responses=ERROR_RESPONSES)
async def model_info(request: Request) -> dict:
    require_ready(request)
    manifest = request.app.state.scoring_runner.scorer.manifest
    return {
        "modelVersion": manifest.modelVersion,
        "featureVersion": manifest.featureVersion,
        "calibrationVersion": manifest.calibrationVersion,
        "isDemo": True,
        "positiveClass": 1,
        "outcome": "CHGOFF",
        "naicsMode": manifest.naicsMode,
        "runtime": request.app.state.scoring_runner.status(),
    }
