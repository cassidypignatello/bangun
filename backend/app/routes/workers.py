"""
Worker discovery and preview endpoints
"""

from fastapi import APIRouter, HTTPException, Request, status

from app.integrations.supabase import get_worker_by_id, get_workers_for_project
from app.middleware.rate_limit import STANDARD_LIMIT, limiter
from app.schemas.worker import WorkerPreview
from app.services.trust_calculator import create_trust_score, mask_worker_name

router = APIRouter()


@router.get("/preview/{project_type}", status_code=status.HTTP_200_OK)
@limiter.limit(STANDARD_LIMIT)
async def get_worker_previews(
    request: Request, project_type: str, limit: int = 20
) -> list[WorkerPreview]:
    """
    Get worker previews for project type (before unlock)

    Returns masked worker information sorted by trust score.
    Full details require payment unlock.

    Args:
        project_type: Type of construction project
        limit: Maximum number of workers to return

    Returns:
        list[WorkerPreview]: Worker previews with trust scores
    """
    workers = await get_workers_for_project(project_type, limit)

    previews = []
    for worker in workers:
        trust_score = create_trust_score(worker)

        preview = WorkerPreview(
            worker_id=worker["worker_id"],
            name_preview=mask_worker_name(worker["full_name"]),
            specialization=worker["specialization"],
            trust_score=trust_score,
            location=worker["location"],
            hourly_rate_idr=worker["hourly_rate_idr"],
            daily_rate_idr=worker["daily_rate_idr"],
            portfolio_images=worker.get("portfolio_images", []),
            certifications=worker.get("certifications", []),
            languages=worker.get("languages", ["Indonesian"]),
            is_unlocked=False,
        )
        previews.append(preview)

    return previews


@router.get("/{worker_id}/preview", status_code=status.HTTP_200_OK)
@limiter.limit(STANDARD_LIMIT)
async def get_single_worker_preview(request: Request, worker_id: str) -> WorkerPreview:
    """
    Get preview for specific worker

    Args:
        worker_id: Worker identifier

    Returns:
        WorkerPreview: Worker preview with masked details
    """
    worker = await get_worker_by_id(worker_id)

    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found"
        )

    trust_score = create_trust_score(worker)

    preview = WorkerPreview(
        worker_id=worker["worker_id"],
        name_preview=mask_worker_name(worker["full_name"]),
        specialization=worker["specialization"],
        trust_score=trust_score,
        location=worker["location"],
        hourly_rate_idr=worker["hourly_rate_idr"],
        daily_rate_idr=worker["daily_rate_idr"],
        portfolio_images=worker.get("portfolio_images", []),
        certifications=worker.get("certifications", []),
        languages=worker.get("languages", ["Indonesian"]),
        is_unlocked=False,
    )

    return preview
