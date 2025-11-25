"""
Cost estimation endpoints
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.integrations.supabase import get_project
from app.middleware.rate_limit import HEAVY_LIMIT, limiter
from app.schemas.estimate import EstimateStatusResponse
from app.schemas.project import ProjectInput
from app.services.bom_generator import create_estimate, process_estimate

router = APIRouter()


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(HEAVY_LIMIT)
async def create_cost_estimate(
    request: Request, project: ProjectInput, background_tasks: BackgroundTasks
):
    """
    Create new cost estimate (async processing)

    Returns 202 Accepted with estimate ID.
    Processing happens in background.
    Use GET /estimate/{id}/status to check progress.

    Args:
        project: Project details for estimation
        background_tasks: FastAPI background tasks

    Returns:
        dict: Initial estimate with pending status
    """
    # Create initial estimate record
    estimate = await create_estimate(project)

    # Trigger background processing
    background_tasks.add_task(process_estimate, estimate.estimate_id, project)

    return {
        "estimate_id": estimate.estimate_id,
        "status": estimate.status.value,
        "message": "Estimate is being processed. Check status endpoint for updates.",
        "ok": True,
    }


@router.get("/{estimate_id}/status", status_code=status.HTTP_200_OK)
@limiter.limit("120/minute")
async def get_estimate_status(request: Request, estimate_id: str):
    """
    Check estimate processing status

    Args:
        estimate_id: Estimate identifier

    Returns:
        EstimateStatusResponse: Current status and progress
    """
    estimate_data = await get_project(estimate_id)

    if not estimate_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found"
        )

    # Calculate progress based on status
    status_progress = {
        "pending": 0,
        "processing": 50,
        "completed": 100,
        "failed": 0,
    }

    progress = status_progress.get(estimate_data["status"], 0)

    return EstimateStatusResponse(
        estimate_id=estimate_id,
        status=estimate_data["status"],
        progress_percentage=progress,
        message=estimate_data.get("error_message"),
    )


@router.get("/{estimate_id}", status_code=status.HTTP_200_OK)
@limiter.limit("120/minute")
async def get_estimate_details(request: Request, estimate_id: str):
    """
    Get complete estimate with BOM breakdown

    Args:
        estimate_id: Estimate identifier

    Returns:
        EstimateResponse: Full estimate with pricing details
    """
    estimate_data = await get_project(estimate_id)

    if not estimate_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found"
        )

    return estimate_data
