"""
Health check and monitoring endpoints
"""

from fastapi import APIRouter, status

from app.config import get_settings
from app.integrations.supabase import get_supabase_client

router = APIRouter()


@router.get("/", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Basic health check - is the API responding?

    Returns:
        dict: Health status
    """
    return {"status": "healthy", "ok": True}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """
    Readiness check - are dependencies available?

    Checks:
    - Database connection
    - Configuration loaded

    Returns:
        dict: Readiness status with dependency checks
    """
    settings = get_settings()
    checks = {"api": True, "config": True, "database": False}

    try:
        # Test database connection
        supabase = get_supabase_client()
        supabase.table("estimates").select("estimate_id").limit(1).execute()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    all_ready = all(checks.values())

    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": checks,
        "ok": all_ready,
    }


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def metrics():
    """
    Basic metrics endpoint

    Returns:
        dict: Application metrics
    """
    settings = get_settings()

    return {
        "environment": settings.env,
        "version": settings.api_version,
        "ok": True,
    }
