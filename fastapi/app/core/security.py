import secrets
from typing import Annotated

from fastapi import Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import ServiceError

internal_key = APIKeyHeader(name="X-Internal-API-Key", auto_error=False)
bearer_key = HTTPBearer(auto_error=False)


async def require_key(request: Request, supplied: Annotated[str | None, Security(internal_key)]):
    if supplied is None:
        raise ServiceError(401, "AUTH_REQUIRED", "Internal API key required")
    if not secrets.compare_digest(supplied.encode(), request.app.state.settings.ml_internal_api_key.encode()):
        raise ServiceError(401, "AUTH_INVALID", "Invalid internal API key")


async def require_bearer(
    request: Request, supplied: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_key)]
):
    if supplied is None:
        missing = request.headers.get("Authorization") is None
        raise ServiceError(
            401, "AUTH_REQUIRED" if missing else "AUTH_INVALID", "Internal Bearer key required"
        )
    if not secrets.compare_digest(
        supplied.credentials.encode(), request.app.state.settings.ml_internal_api_key.encode()
    ):
        raise ServiceError(401, "AUTH_INVALID", "Invalid internal API key")
