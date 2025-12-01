"""
Worker discovery and preview endpoints
"""

from fastapi import APIRouter, HTTPException, Request, status

from app.integrations.supabase import get_worker_by_id, get_workers_by_specialization
from app.middleware.rate_limit import STANDARD_LIMIT, limiter
from app.schemas.worker import WorkerPreview
from app.services.trust_calculator import (
    create_trust_score_from_worker_dict,
    mask_worker_name,
)

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
    workers = await get_workers_by_specialization(project_type, limit=limit)

    previews = []
    for worker in workers:
        trust_score = create_trust_score_from_worker_dict(worker)

        preview = WorkerPreview(
            id=worker["worker_id"],
            preview_name=mask_worker_name(worker.get("full_name", worker.get("business_name", "Unknown"))),
            trust_score=trust_score,
            location=worker.get("location", "Bali"),
            specializations=worker.get("specializations", [worker.get("specialization", "general")]),
            preview_review=worker.get("preview_review"),
            photos_count=worker.get("gmaps_photos_count", 0),
            opening_hours=worker.get("opening_hours"),
            price_idr_per_day=worker.get("daily_rate_idr") or worker.get("olx_price_idr"),
            contact_locked=True,
            unlock_price_idr=50000,
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

    trust_score = create_trust_score_from_worker_dict(worker)

    preview = WorkerPreview(
        id=worker["worker_id"],
        preview_name=mask_worker_name(worker.get("full_name", worker.get("business_name", "Unknown"))),
        trust_score=trust_score,
        location=worker.get("location", "Bali"),
        specializations=worker.get("specializations", [worker.get("specialization", "general")]),
        preview_review=worker.get("preview_review"),
        photos_count=worker.get("gmaps_photos_count", 0),
        opening_hours=worker.get("opening_hours"),
        price_idr_per_day=worker.get("daily_rate_idr") or worker.get("olx_price_idr"),
        contact_locked=True,
        unlock_price_idr=50000,
    )

    return preview
