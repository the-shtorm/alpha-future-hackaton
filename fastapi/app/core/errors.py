from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list | None = None):
        self.status, self.code, self.message = status, code, message
        self.details = details or []


def response(status, code, message, request_id=None, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "details": details or []},
            "requestId": request_id,
        },
        headers={"Retry-After": "1"} if code == "SERVICE_BUSY" else None,
    )


async def service_error(request: Request, error: ServiceError):
    return response(
        error.status, error.code, error.message, getattr(request.state, "request_id", None), error.details
    )


async def validation_error(request: Request, error: RequestValidationError):
    # Do not serialize Pydantic input, ctx, arbitrary field names, or user-controlled enum values.
    known = {
        "body",
        "requestId",
        "profile",
        "business",
        "sector",
        "request",
        "purpose",
        "usageMode",
        "description",
        "security",
        "collateralReady",
        "guarantorReady",
        "candidates",
        "product",
        "id",
        "version",
        "name",
        "type",
        "purposes",
        "usageModes",
        "targetScenario",
        "targetSectors",
        "specialization",
        "collateralRequirement",
        "guarantorRequirement",
        "securityNote",
        "eligibilityStatus",
        "pendingConditions",
        "code",
        "message",
        "topK",
        "schemaVersion",
        "semanticsVersion",
        "queryFields",
        "dictionaries",
        "sectors",
        "readiness",
        "productId",
        "productVersion",
        "synthetic",
        "result",
        "actual",
        "expected",
        "loanAmountUsd",
        "termMonths",
        "initialInterestRatePct",
        "interestRateType",
        "isRevolving",
        "hasCollateral",
        "businessType",
        "businessAgeCategory",
        "naicsCode",
    }
    details = [
        {"path": [p if isinstance(p, int) or p in known else "field" for p in e["loc"]]}
        for e in error.errors()[:20]
    ]
    contract = "Java exchange" if request.url.path.endswith("/rank-java") else "rank-v2"
    if request.url.path.startswith("/api/v1/scoring/"):
        contract = "sba-scoring-1"
    return response(422, "VALIDATION_ERROR", f"Request does not match {contract}", details=details)


async def unexpected_error(request: Request, error: Exception):
    return response(
        500, "INTERNAL_ERROR", "Internal service error", getattr(request.state, "request_id", None)
    )


async def http_error(request: Request, error: HTTPException):
    return response(error.status_code, "HTTP_ERROR", "HTTP request rejected")
