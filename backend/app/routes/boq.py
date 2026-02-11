"""
BoQ (Bill of Quantity) Upload and Analysis API Routes.

Endpoints:
- POST /boq/upload - Upload PDF/Excel BoQ for analysis
- GET /boq/{job_id}/status - Check processing status
- GET /boq/{job_id}/results - Get analysis results
"""

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.schemas.boq import (
    BoQAnalysisResults,
    BoQFileFormat,
    BoQJobStatus,
    BoQJobStatusResponse,
    BoQUploadResponse,
)
from app.services.boq_processor import process_boq_job_sync
from app.integrations.supabase import get_supabase_client

router = APIRouter(prefix="/boq", tags=["BoQ Analysis"])

limiter = Limiter(key_func=get_remote_address)

# Rate limits
UPLOAD_LIMIT = "5/minute"  # Heavy operation
STATUS_LIMIT = "60/minute"  # Light polling
RESULTS_LIMIT = "30/minute"


# =============================================================================
# Helper Functions
# =============================================================================


def _get_file_format(filename: str) -> BoQFileFormat:
    """Determine file format from filename extension."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return BoQFileFormat.PDF
    elif lower.endswith(".xlsx"):
        return BoQFileFormat.XLSX
    elif lower.endswith(".xls"):
        return BoQFileFormat.XLS
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format. Supported: .pdf, .xlsx, .xls",
        )


def _get_session_id(request: Request) -> str:
    """Extract or generate session ID from request."""
    # Check header first
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        return session_id

    # Check query param
    session_id = request.query_params.get("session_id")
    if session_id:
        return session_id

    # Generate new one
    return str(uuid.uuid4())


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED, response_model=BoQUploadResponse)
@limiter.limit(UPLOAD_LIMIT)
async def upload_boq(
    request: Request,
    file: UploadFile = File(..., description="BoQ file (PDF or Excel)"),
):
    """
    Upload a BoQ (Bill of Quantity) file for analysis.

    Accepts PDF or Excel (.xlsx, .xls) files containing contractor quotes.
    Processing happens asynchronously - use the status endpoint to track progress.

    Returns:
        BoQUploadResponse: Job ID and initial status

    Example:
        ```
        curl -X POST /api/v1/boq/upload \\
          -F "file=@contractor_quote.pdf" \\
          -H "X-Session-ID: user-session-123"
        ```
    """
    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided",
        )

    file_format = _get_file_format(file.filename)

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: 10MB",
        )

    # Get session
    session_id = _get_session_id(request)

    # Create job record in Supabase
    job_id = str(uuid.uuid4())
    supabase = get_supabase_client()

    job_data = {
        "id": job_id,
        "session_id": session_id,
        "filename": file.filename,
        "file_format": file_format.value,
        "file_size_bytes": file_size,
        "status": BoQJobStatus.PENDING.value,
        "progress_percent": 0,
    }

    result = supabase.table("boq_jobs").insert(job_data).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create job record",
        )

    # Trigger background processing using ProcessPoolExecutor
    # This runs in a completely separate process, avoiding event loop conflicts
    # that occur with FastAPI's BackgroundTasks and httpx/OpenAI clients
    from app.main import boq_executor

    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        boq_executor,
        process_boq_job_sync,
        job_id,
        content,
        file_format,
        file.filename,
    )

    return BoQUploadResponse(
        job_id=job_id,
        status=BoQJobStatus.PENDING,
        message="BoQ upload received. Processing will begin shortly.",
        ok=True,
    )


@router.get("/{job_id}/status", response_model=BoQJobStatusResponse)
@limiter.limit(STATUS_LIMIT)
async def get_boq_status(request: Request, job_id: str):
    """
    Check the processing status of a BoQ analysis job.

    Poll this endpoint to track progress. Once status is 'completed',
    use the results endpoint to get the full analysis.

    Args:
        job_id: The job ID returned from upload

    Returns:
        BoQJobStatusResponse: Current status and progress
    """
    supabase = get_supabase_client()

    result = (
        supabase.table("boq_jobs")
        .select("*")
        .eq("id", job_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    job = result.data[0]

    # Determine message based on status
    message = None
    if job["status"] == BoQJobStatus.PROCESSING.value:
        progress = job.get("progress_percent", 0)
        if progress < 30:
            message = "Extracting items from document..."
        elif progress < 70:
            message = "Looking up material prices..."
        else:
            message = "Calculating savings..."
    elif job["status"] == BoQJobStatus.COMPLETED.value:
        message = "Analysis complete!"
    elif job["status"] == BoQJobStatus.FAILED.value:
        message = "Processing failed"

    return BoQJobStatusResponse(
        job_id=job_id,
        status=BoQJobStatus(job["status"]),
        progress_percent=job.get("progress_percent", 0),
        message=message,
        error_message=job.get("error_message"),
        total_items_extracted=job.get("total_items_extracted", 0),
        materials_count=job.get("materials_count", 0),
        labor_count=job.get("labor_count", 0),
        owner_supply_count=job.get("owner_supply_count", 0),
        created_at=job["created_at"],
        completed_at=job.get("completed_at"),
    )


@router.get("/{job_id}/results", response_model=BoQAnalysisResults)
@limiter.limit(RESULTS_LIMIT)
async def get_boq_results(request: Request, job_id: str):
    """
    Get the full analysis results for a completed BoQ job.

    Only available after job status is 'completed'.

    Args:
        job_id: The job ID returned from upload

    Returns:
        BoQAnalysisResults: Complete analysis with pricing comparisons

    Raises:
        404: Job not found
        409: Job not yet completed
    """
    supabase = get_supabase_client()

    # Get job
    job_result = (
        supabase.table("boq_jobs")
        .select("*")
        .eq("id", job_id)
        .execute()
    )

    if not job_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    job = job_result.data[0]

    # Check if completed
    if job["status"] != BoQJobStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job not yet completed. Current status: {job['status']}",
        )

    # Get all items
    items_result = (
        supabase.table("boq_items")
        .select("*")
        .eq("job_id", job_id)
        .execute()
    )

    items = items_result.data or []

    # Categorize items
    owner_supply_items = []
    overpriced_items = []
    all_materials = []
    labor_items = []

    for item in items:
        if item["item_type"] == "labor":
            labor_items.append(item)
        elif item["item_type"] == "material":
            all_materials.append(item)

            # Check if owner supply
            if item.get("is_owner_supply"):
                owner_supply_items.append(item)

            # Check if overpriced (>10% above market)
            diff_percent = item.get("price_difference_percent")
            if diff_percent and diff_percent > 10:
                overpriced_items.append(item)

    # Calculate summary
    contractor_total = job.get("contractor_total") or 0
    market_estimate = job.get("market_estimate") or 0
    potential_savings = job.get("potential_savings") or 0
    savings_percent = (potential_savings / contractor_total * 100) if contractor_total > 0 else 0

    priced_count = sum(1 for item in all_materials if item.get("tokopedia_price"))

    from app.schemas.boq import BoQMetadata, BoQSummary, BoQItemPriced, BoQItemExtracted

    return BoQAnalysisResults(
        job_id=job_id,
        status=BoQJobStatus.COMPLETED,
        metadata=BoQMetadata(
            project_name=job.get("project_name"),
            contractor_name=job.get("contractor_name"),
            project_location=job.get("project_location"),
            filename=job["filename"],
        ),
        summary=BoQSummary(
            contractor_total=contractor_total,
            market_estimate=market_estimate,
            potential_savings=potential_savings,
            savings_percent=round(savings_percent, 1),
            total_items=job.get("total_items_extracted", 0),
            materials_count=job.get("materials_count", 0),
            labor_count=job.get("labor_count", 0),
            owner_supply_count=job.get("owner_supply_count", 0),
            priced_count=priced_count,
        ),
        owner_supply_items=[BoQItemPriced(**item) for item in owner_supply_items],
        overpriced_items=[BoQItemPriced(**item) for item in overpriced_items],
        all_materials=[BoQItemPriced(**item) for item in all_materials],
        labor_items=[BoQItemExtracted(**item) for item in labor_items],
        completed_at=job.get("completed_at"),
    )
