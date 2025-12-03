"""
Worker search endpoint with intelligent cache-or-scrape strategy.

Flow:
1. Check cache for recent workers (7-day TTL)
2. If cache hit: deduplicate → rank → return
3. If cache miss: trigger background scrape → return empty with 202 status
4. Background scrape: scrape → deduplicate → save → calculate trust scores
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.integrations.google_maps_scraper import scrape_google_maps_workers
from app.integrations.supabase import (
    bulk_insert_workers,
    get_cached_workers,
    update_worker_scraped_timestamp,
)
from app.middleware.rate_limit import STANDARD_LIMIT, limiter
from app.schemas.worker import WorkerPreview
from app.services.trust_calculator import calculate_trust_score, mask_worker_name
from app.services.worker_deduplication import deduplicate_workers
from app.services.worker_matcher import rank_workers

router = APIRouter(prefix="/workers", tags=["workers"])


class WorkerSearchResponse(BaseModel):
    """Response for worker search with status"""

    status: str  # 'cache_hit' or 'scraping'
    workers: list[WorkerPreview]
    total_count: int
    cache_age_hours: int | None = None
    estimated_scrape_time_seconds: int | None = None


class WorkerSearchRequest(BaseModel):
    """Worker search filters"""

    project_type: str
    location: str = "Bali"
    budget_range: str | None = None  # 'low', 'medium', 'high'
    min_trust_score: int = 40
    max_results: int = 10


async def background_scrape_and_save(
    project_type: str,
    location: str,
) -> None:
    """
    Background task to scrape, deduplicate, and save workers.

    Args:
        project_type: Project type for scraping (pool, bathroom, etc.)
        location: Location for scraping (default: Bali)
    """
    try:
        # Step 1: Scrape from Google Maps
        raw_workers = await scrape_google_maps_workers(
            project_type=project_type,
            location=location,
            max_results_per_search=20,
            min_rating=4.0
        )

        if not raw_workers:
            return

        # Step 2: Deduplicate workers
        deduplicated_workers = deduplicate_workers(raw_workers)

        # Step 3: Calculate trust scores
        workers_with_trust = []
        for worker in deduplicated_workers:
            trust_result = calculate_trust_score(worker)
            worker.update({
                "trust_score": trust_result.score,
                "trust_level": trust_result.level.value,
                "trust_breakdown": trust_result.breakdown,
                "last_score_calculated_at": datetime.now(timezone.utc).isoformat(),
            })
            workers_with_trust.append(worker)

        # Step 4: Bulk insert to database (upsert by gmaps_place_id)
        saved_workers = await bulk_insert_workers(workers_with_trust)

        # Step 5: Update scraped timestamps
        worker_ids = [w["id"] for w in saved_workers if "id" in w]
        if worker_ids:
            await update_worker_scraped_timestamp(worker_ids)

    except Exception as e:
        # Log error but don't fail (background task)
        print(f"Background scrape error for {project_type}: {str(e)}")


def transform_to_preview(worker: dict[str, Any]) -> WorkerPreview:
    """
    Transform database worker to preview response with masking.

    Args:
        worker: Worker dictionary from database

    Returns:
        WorkerPreview: Masked worker preview
    """
    # Mask contact information
    masked_name = mask_worker_name(
        worker.get("business_name") or worker.get("name", "Unknown")
    )

    return WorkerPreview(
        id=worker["id"],
        preview_name=masked_name,
        trust_score_detailed={
            "score": worker.get("trust_score", 0),
            "level": worker.get("trust_level", "LOW"),
            "breakdown": worker.get("trust_breakdown", {}),
        },
        location=worker.get("location", "Bali"),
        specializations=worker.get("specializations", []),
        preview_review=worker.get("preview_review"),
        gmaps_rating=worker.get("gmaps_rating"),
        gmaps_review_count=worker.get("gmaps_review_count", 0),
        gmaps_photos_count=worker.get("gmaps_photos_count", 0),
        opening_hours=worker.get("opening_hours"),
        price_idr_per_day=worker.get("olx_price_idr"),
        contact_locked=True,
        unlock_price_idr=50000,
    )


@router.post("/search", status_code=status.HTTP_200_OK)
@limiter.limit(STANDARD_LIMIT)
async def search_workers(
    request: Request,
    search_request: WorkerSearchRequest,
    background_tasks: BackgroundTasks,
) -> WorkerSearchResponse:
    """
    Search for workers with intelligent cache-or-scrape strategy.

    **Cache Strategy**:
    - Checks for recent workers (7-day cache)
    - If cache hit: returns deduplicated + ranked workers immediately
    - If cache miss: triggers background scrape, returns 202 with empty results

    **Background Scraping**:
    - Scrapes Google Maps in background (cost: ~$0.08-$0.40)
    - Deduplicates workers by phone/place_id/name
    - Calculates trust scores
    - Saves to database for future requests

    **Rate Limiting**: 10 requests per minute to prevent API abuse

    Args:
        search_request: Search filters (project_type, location, budget, etc.)
        background_tasks: FastAPI background tasks for async scraping

    Returns:
        WorkerSearchResponse: Status + workers list + metadata

    Example:
        ```json
        POST /workers/search
        {
            "project_type": "pool_construction",
            "location": "Canggu",
            "budget_range": "medium",
            "min_trust_score": 60,
            "max_results": 10
        }
        ```

    Response (cache hit):
        ```json
        {
            "status": "cache_hit",
            "workers": [...],
            "total_count": 15,
            "cache_age_hours": 48
        }
        ```

    Response (cache miss):
        ```json
        {
            "status": "scraping",
            "workers": [],
            "total_count": 0,
            "estimated_scrape_time_seconds": 30
        }
        ```
    """
    # Step 1: Check cache for recent workers (7-day TTL)
    cached_workers = await get_cached_workers(
        specialization=search_request.project_type,
        max_age_hours=168  # 7 days
    )

    # CASE 1: Cache Hit - Return ranked workers immediately
    if cached_workers:
        # Deduplicate (in case of duplicates from multiple sources)
        deduplicated = deduplicate_workers(cached_workers)

        # Rank by project requirements
        ranked = rank_workers(
            workers=deduplicated,
            project_type=search_request.project_type,
            location=search_request.location,
            min_trust_score=search_request.min_trust_score,
            budget_range=search_request.budget_range,
            max_results=search_request.max_results
        )

        # Transform to preview format with masking
        previews = [transform_to_preview(w) for w in ranked]

        # Calculate cache age
        if ranked and ranked[0].get("last_scraped_at"):
            cache_age = datetime.now(timezone.utc) - datetime.fromisoformat(
                ranked[0]["last_scraped_at"]
            )
            cache_age_hours = int(cache_age.total_seconds() / 3600)
        else:
            cache_age_hours = None

        return WorkerSearchResponse(
            status="cache_hit",
            workers=previews,
            total_count=len(previews),
            cache_age_hours=cache_age_hours
        )

    # CASE 2: Cache Miss - Trigger background scrape
    background_tasks.add_task(
        background_scrape_and_save,
        project_type=search_request.project_type,
        location=search_request.location
    )

    return WorkerSearchResponse(
        status="scraping",
        workers=[],
        total_count=0,
        estimated_scrape_time_seconds=30
    )


@router.get("/{worker_id}/preview", status_code=status.HTTP_200_OK)
@limiter.limit(STANDARD_LIMIT)
async def get_worker_preview(
    request: Request,
    worker_id: str
) -> WorkerPreview:
    """
    Get masked preview for a specific worker.

    Contact information (phone, email) remains locked until payment.

    Args:
        worker_id: UUID of the worker

    Returns:
        WorkerPreview: Masked worker preview

    Raises:
        HTTPException: 404 if worker not found
    """
    from app.integrations.supabase import get_worker_by_id

    worker = await get_worker_by_id(worker_id)

    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker {worker_id} not found"
        )

    return transform_to_preview(worker)
