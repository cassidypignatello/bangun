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
        estimate_id: Estimate identifier (project ID)

    Returns:
        EstimateStatusResponse: Current status and progress
    """
    project_data = await get_project(estimate_id)

    if not project_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found"
        )

    # Map database status to estimate status
    db_status = project_data.get("status", "draft")
    status_mapping = {
        "draft": "pending",
        "estimated": "completed",
        "unlocked": "completed",
        "completed": "completed",
    }
    estimate_status = status_mapping.get(db_status, "pending")

    # Calculate progress based on status
    status_progress = {
        "pending": 0,
        "processing": 50,
        "completed": 100,
        "failed": 0,
    }

    progress = status_progress.get(estimate_status, 0)

    # Check for errors in price_range JSONB
    error_message = None
    price_range = project_data.get("price_range")
    if isinstance(price_range, dict) and price_range.get("status") == "failed":
        error_message = price_range.get("error")
        estimate_status = "failed"

    return EstimateStatusResponse(
        estimate_id=estimate_id,
        status=estimate_status,
        progress_percentage=progress,
        message=error_message,
    )


@router.get("/{estimate_id}", status_code=status.HTTP_200_OK)
@limiter.limit("120/minute")
async def get_estimate_details(request: Request, estimate_id: str):
    """
    Get complete estimate with BOM breakdown

    Args:
        estimate_id: Estimate identifier (project ID)

    Returns:
        EstimateResponse: Full estimate with pricing details
    """
    project_data = await get_project(estimate_id)

    if not project_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found"
        )

    # Map database schema to API response format
    from app.schemas.estimate import EstimateResponse, EstimateStatus, BOMItem
    from datetime import datetime

    # Map database status to estimate status
    db_status = project_data.get("status", "draft")
    status_mapping = {
        "draft": EstimateStatus.PENDING,
        "estimated": EstimateStatus.COMPLETED,
        "unlocked": EstimateStatus.COMPLETED,
        "completed": EstimateStatus.COMPLETED,
    }
    estimate_status = status_mapping.get(db_status, EstimateStatus.PENDING)

    # Parse BOM items from JSONB
    bom_data = project_data.get("bom", [])
    bom_items = [BOMItem(**item) for item in bom_data] if bom_data else []

    # Check for errors
    error_message = None
    price_range = project_data.get("price_range")
    if isinstance(price_range, dict) and price_range.get("status") == "failed":
        error_message = price_range.get("error")
        estimate_status = EstimateStatus.FAILED

    return EstimateResponse(
        estimate_id=project_data["id"],
        status=estimate_status,
        project_type=project_data.get("project_type", ""),
        bom_items=bom_items,
        total_cost_idr=int(project_data.get("material_total") or 0),
        labor_cost_idr=int(project_data.get("labor_total") or 0),
        grand_total_idr=int(project_data.get("total_estimate") or 0),
        created_at=datetime.fromisoformat(project_data["created_at"].replace("Z", "+00:00"))
        if isinstance(project_data.get("created_at"), str)
        else project_data.get("created_at"),
        updated_at=datetime.fromisoformat(project_data["updated_at"].replace("Z", "+00:00"))
        if isinstance(project_data.get("updated_at"), str)
        else project_data.get("updated_at"),
        error_message=error_message,
    )
