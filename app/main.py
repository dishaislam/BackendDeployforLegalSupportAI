import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.db.base import Base
from app.api.routes import auth, chat, health
from app.api.routes import documents
from app.api.routes import ratings
from app.api.routes import lawyers
from app.api.routes import case_studies

# Import all models so SQLAlchemy can register them
import app.models.user  # noqa: F401
import app.models.chat  # noqa: F401
import app.models.message  # noqa: F401
import app.models.rating  # noqa: F401
import app.models.lawyer  # noqa: F401
import app.models.case_study  # noqa: F401

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Starting LegalSupportAI backend...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info(" Database tables initialized successfully.")
    except Exception as e:
        logger.error(f" Database initialization failed: {e}")
        raise

    yield

    logger.info("Shutting down LegalSupportAI backend...")
    await engine.dispose()


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Bangladesh Legal Support AI — RAG-powered legal assistant API",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @application.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Please try again later."},
        )

    # Register routers
    application.include_router(health.router, tags=["Health"])
    application.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
    application.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
    application.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
    application.include_router(ratings.router, prefix="/api/ratings", tags=["Ratings"])
    application.include_router(lawyers.router, prefix="/api/lawyers", tags=["Lawyers"])
    application.include_router(case_studies.router, prefix="/api/cases", tags=["Case Studies"])
    
    return application


app = create_application()
