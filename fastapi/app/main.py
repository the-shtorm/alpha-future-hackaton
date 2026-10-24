import os
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.routes import health, java_recommendations, model_info, recommendations
from app.core.body_limit import BodyLimitMiddleware
from app.core.config import Settings
from app.core.errors import ServiceError, http_error, service_error, unexpected_error, validation_error
from app.core.logging import configure_logging
from app.services.encoder import SentenceEncoder
from app.services.ranker import Ranker
from app.services.runner import RankRunner


def create_app(settings: Settings | None = None, encoder_factory=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        try:
            config = settings or Settings()
        except Exception:
            raise RuntimeError("Invalid service configuration") from None
        app.state.settings = config
        app.state.ready = False
        configure_logging(config.log_level)
        try:
            encoder = await anyio.to_thread.run_sync(lambda: (encoder_factory or SentenceEncoder)(config))
        except Exception:
            raise RuntimeError("Model initialization failed; verify local model and configuration") from None
        app.state.runner = RankRunner(
            Ranker(
                encoder,
                config.passage_cache_max_entries,
                max_cosine_distance=config.recommendation_max_cosine_distance,
            ),
            config,
        )
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            await app.state.runner.close()

    docs = settings.docs_enabled if settings else os.getenv("DOCS_ENABLED", "false").lower() == "true"
    app = FastAPI(
        title="Credit Cabinet Semantic Ranking",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.ready = False
    app.add_middleware(BodyLimitMiddleware, limit=lambda: app.state.settings.max_request_bytes)
    app.add_exception_handler(ServiceError, service_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(Exception, unexpected_error)
    app.include_router(health.router)
    app.include_router(recommendations.router)
    app.include_router(java_recommendations.router)
    app.include_router(model_info.router)
    return app


app = create_app()
