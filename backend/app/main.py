"""
FastAPI application entry point for Bangun
Includes Sentry monitoring, CORS, rate limiting, error handling, and background jobs
"""

import sentry_sdk
from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.middleware.error_handler import add_error_handlers
from app.middleware.timeout import TimeoutMiddleware
from app.routes import estimates, health, materials, payments, workers, workers_search
from app.services.background_jobs import start_background_jobs, stop_background_jobs

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.

    Startup:
    - Start background job scheduler (if enabled)

    Shutdown:
    - Stop background job scheduler gracefully
    """
    # Startup
    start_background_jobs()
    yield
    # Shutdown
    stop_background_jobs()

# Initialize Sentry for error tracking
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        traces_sample_rate=1.0 if settings.env == "development" else 0.1,
        profiles_sample_rate=1.0 if settings.env == "development" else 0.1,
    )

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI application with lifespan
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    debug=settings.debug,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
    redirect_slashes=False,  # Prevent 307 redirects for trailing slash mismatches
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add timeout middleware (process requests first to add timeout protection)
app.add_middleware(TimeoutMiddleware, default_timeout=30)

# Add custom error handlers
add_error_handlers(app)

# Create API v1 router
api_v1_router = APIRouter(prefix="/api/v1")

# Include all API routes under /api/v1
api_v1_router.include_router(health.router, prefix="/health", tags=["Health"])
api_v1_router.include_router(estimates.router, prefix="/estimates", tags=["Estimates"])
api_v1_router.include_router(workers_search.router, tags=["Workers"])  # New search endpoint
api_v1_router.include_router(workers.router, prefix="/workers", tags=["Workers"])  # Legacy endpoints
api_v1_router.include_router(payments.router, prefix="", tags=["Payments"])
api_v1_router.include_router(materials.router, prefix="/materials", tags=["Materials"])

# Mount the API v1 router
app.include_router(api_v1_router)


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "environment": settings.env,
        "docs": "/docs" if settings.debug else "disabled",
    }
