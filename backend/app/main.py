"""
FastAPI application entry point for Bali Renovation OS
Includes Sentry monitoring, CORS, rate limiting, and error handling
"""

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.middleware.error_handler import add_error_handlers
from app.routes import estimates, health, materials, payments, workers

settings = get_settings()

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

# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    debug=settings.debug,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
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

# Add custom error handlers
add_error_handlers(app)

# Include routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(estimates.router, prefix="/estimate", tags=["Estimates"])
app.include_router(workers.router, prefix="/workers", tags=["Workers"])
app.include_router(payments.router, prefix="", tags=["Payments"])
app.include_router(materials.router, prefix="/materials", tags=["Materials"])


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "environment": settings.env,
        "docs": "/docs" if settings.debug else "disabled",
    }
