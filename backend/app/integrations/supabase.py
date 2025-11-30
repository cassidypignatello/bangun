"""
Supabase client for database operations

Tables:
- projects: User estimates and project data
- materials: Construction materials catalog with pricing
- workers: Contractor database with trust scores
- payments: Midtrans payment records
- affiliate_clicks: Revenue tracking
- scrape_jobs: Apify job tracking
"""

from functools import lru_cache

from supabase import create_client, Client

from app.config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    """
    Get singleton Supabase client instance

    Returns:
        Client: Configured Supabase client with service key
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)


# ============================================
# PROJECTS (formerly "estimates")
# ============================================

async def save_project(project_data: dict) -> dict:
    """
    Save project/estimate to database

    Args:
        project_data: Project data dictionary

    Returns:
        dict: Saved project with database ID
    """
    supabase = get_supabase_client()
    response = supabase.table("projects").insert(project_data).execute()
    return response.data[0] if response.data else {}


async def get_project(project_id: str) -> dict | None:
    """
    Retrieve project by ID

    Args:
        project_id: UUID of the project

    Returns:
        dict | None: Project data or None if not found
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("projects").select("*").eq("id", project_id).execute()
    )
    return response.data[0] if response.data else None


async def get_project_by_session(session_id: str) -> dict | None:
    """
    Retrieve project by session ID (for anonymous users)

    Args:
        session_id: Session identifier

    Returns:
        dict | None: Project data or None if not found
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("projects")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


async def update_project(project_id: str, **kwargs) -> dict | None:
    """
    Update project fields

    Args:
        project_id: UUID of the project
        **kwargs: Fields to update

    Returns:
        dict | None: Updated project data
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("projects")
        .update(kwargs)
        .eq("id", project_id)
        .execute()
    )
    return response.data[0] if response.data else None


async def update_project_status(project_id: str, status: str, **kwargs) -> None:
    """
    Update project status and optional fields

    Args:
        project_id: UUID of the project
        status: New status value (draft, estimated, unlocked, completed)
        **kwargs: Additional fields to update
    """
    supabase = get_supabase_client()
    update_data = {"status": status, **kwargs}
    supabase.table("projects").update(update_data).eq("id", project_id).execute()


# ============================================
# MATERIALS
# ============================================

async def get_material_by_code(material_code: str) -> dict | None:
    """
    Get material by its unique code

    Args:
        material_code: Material code (e.g., "MAT001")

    Returns:
        dict | None: Material data or None if not found
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("materials")
        .select("*")
        .eq("material_code", material_code)
        .execute()
    )
    return response.data[0] if response.data else None


async def search_materials(query: str, limit: int = 10) -> list[dict]:
    """
    Search materials by name (Indonesian or English) or aliases.

    Results are cached for 1 hour to reduce database load.

    Args:
        query: Search query
        limit: Maximum results

    Returns:
        list[dict]: Matching materials
    """
    from app.utils.cache import material_search_cache

    # Build cache key
    cache_key = f"search:{query.lower()}:{limit}"

    # Try cache first
    cached_result = await material_search_cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    # Query database
    supabase = get_supabase_client()
    response = (
        supabase.table("materials")
        .select("*")
        .or_(f"name_id.ilike.%{query}%,name_en.ilike.%{query}%")
        .limit(limit)
        .execute()
    )
    result = response.data if response.data else []

    # Cache for 1 hour
    await material_search_cache.set(cache_key, result, ttl=3600)

    return result


async def get_materials_by_category(category: str) -> list[dict]:
    """
    Get all materials in a category

    Args:
        category: Category name (e.g., "cement_concrete", "tiles")

    Returns:
        list[dict]: Materials in category
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("materials")
        .select("*")
        .eq("category", category)
        .execute()
    )
    return response.data if response.data else []


async def update_material_prices(
    material_id: str,
    price_min: float,
    price_max: float,
    price_avg: float,
    sample_size: int
) -> None:
    """
    Update cached pricing for a material

    Args:
        material_id: UUID of the material
        price_min: Minimum price found
        price_max: Maximum price found
        price_avg: Average price
        sample_size: Number of price samples
    """
    supabase = get_supabase_client()
    supabase.table("materials").update({
        "price_min": price_min,
        "price_max": price_max,
        "price_avg": price_avg,
        "price_sample_size": sample_size,
        "price_updated_at": "now()"
    }).eq("id", material_id).execute()


# ============================================
# WORKERS
# ============================================

async def get_worker_by_id(worker_id: str) -> dict | None:
    """
    Get worker details by ID

    Args:
        worker_id: UUID of the worker

    Returns:
        dict | None: Worker data or None if not found
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("workers").select("*").eq("id", worker_id).execute()
    )
    return response.data[0] if response.data else None


async def get_workers_by_specialization(
    specialization: str,
    area: str | None = None,
    limit: int = 20
) -> list[dict]:
    """
    Get workers matching a specialization, optionally filtered by area

    Args:
        specialization: Type of work (e.g., "pool", "renovation")
        area: Optional area filter (e.g., "Canggu", "Ubud")
        limit: Maximum results

    Returns:
        list[dict]: Worker recommendations sorted by trust score
    """
    supabase = get_supabase_client()
    query = (
        supabase.table("workers")
        .select("*")
        .contains("specializations", [specialization])
        .eq("is_active", True)
    )

    if area:
        query = query.eq("area", area)

    response = (
        query
        .order("trust_score", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data if response.data else []


async def save_worker(worker_data: dict) -> dict:
    """
    Save new worker to database

    Args:
        worker_data: Worker data dictionary

    Returns:
        dict: Saved worker with ID
    """
    supabase = get_supabase_client()
    response = supabase.table("workers").insert(worker_data).execute()
    return response.data[0] if response.data else {}


async def update_worker_trust(
    worker_id: str,
    trust_score: int,
    trust_level: str,
    trust_breakdown: dict
) -> None:
    """
    Update worker's trust score

    Args:
        worker_id: UUID of the worker
        trust_score: Calculated score (0-100)
        trust_level: Level (low, medium, high, verified)
        trust_breakdown: Detailed score breakdown
    """
    supabase = get_supabase_client()
    supabase.table("workers").update({
        "trust_score": trust_score,
        "trust_level": trust_level,
        "trust_breakdown": trust_breakdown
    }).eq("id", worker_id).execute()


# ============================================
# PAYMENTS (formerly "transactions")
# ============================================

async def save_payment(payment_data: dict) -> dict:
    """
    Save payment record

    Args:
        payment_data: Payment details

    Returns:
        dict: Saved payment with ID
    """
    supabase = get_supabase_client()
    response = supabase.table("payments").insert(payment_data).execute()
    return response.data[0] if response.data else {}


async def get_payment(payment_id: str) -> dict | None:
    """
    Get payment by ID

    Args:
        payment_id: UUID of the payment

    Returns:
        dict | None: Payment data or None
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("payments").select("*").eq("id", payment_id).execute()
    )
    return response.data[0] if response.data else None


async def get_payment_by_gateway_id(gateway_transaction_id: str) -> dict | None:
    """
    Get payment by Midtrans transaction ID

    Args:
        gateway_transaction_id: Midtrans order/transaction ID

    Returns:
        dict | None: Payment data or None
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("payments")
        .select("*")
        .eq("gateway_transaction_id", gateway_transaction_id)
        .execute()
    )
    return response.data[0] if response.data else None


async def update_payment_status(
    payment_id: str,
    status: str,
    **kwargs
) -> None:
    """
    Update payment status

    Args:
        payment_id: UUID of the payment
        status: New status (pending, completed, failed, refunded)
        **kwargs: Additional fields (e.g., completed_at, gateway_response)
    """
    supabase = get_supabase_client()
    update_data = {"status": status, **kwargs}
    supabase.table("payments").update(update_data).eq("id", payment_id).execute()


# ============================================
# AFFILIATE CLICKS
# ============================================

async def track_affiliate_click(
    project_id: str,
    material_id: str,
    platform: str,
    user_session: str
) -> dict:
    """
    Track affiliate link click

    Args:
        project_id: UUID of the project
        material_id: UUID of the material
        platform: Platform name (tokopedia, shopee)
        user_session: Session identifier

    Returns:
        dict: Created click record
    """
    supabase = get_supabase_client()
    response = supabase.table("affiliate_clicks").insert({
        "project_id": project_id,
        "material_id": material_id,
        "platform": platform,
        "user_session": user_session
    }).execute()
    return response.data[0] if response.data else {}


async def update_affiliate_conversion(
    click_id: str,
    conversion_amount: float,
    commission_earned: float
) -> None:
    """
    Update affiliate click with conversion data

    Args:
        click_id: UUID of the click record
        conversion_amount: Purchase amount
        commission_earned: Commission from affiliate program
    """
    supabase = get_supabase_client()
    supabase.table("affiliate_clicks").update({
        "converted": True,
        "conversion_amount": conversion_amount,
        "commission_earned": commission_earned,
        "converted_at": "now()"
    }).eq("id", click_id).execute()


# ============================================
# SCRAPE JOBS
# ============================================

async def create_scrape_job(
    job_type: str,
    input_params: dict,
    apify_actor_id: str | None = None
) -> dict:
    """
    Create a new scrape job record

    Args:
        job_type: Type of job (materials, workers_olx, workers_gmaps)
        input_params: Apify actor input parameters
        apify_actor_id: Optional Apify actor ID

    Returns:
        dict: Created job record
    """
    supabase = get_supabase_client()
    response = supabase.table("scrape_jobs").insert({
        "job_type": job_type,
        "input_params": input_params,
        "apify_actor_id": apify_actor_id,
        "status": "pending"
    }).execute()
    return response.data[0] if response.data else {}


async def update_scrape_job(
    job_id: str,
    status: str,
    **kwargs
) -> None:
    """
    Update scrape job status

    Args:
        job_id: UUID of the job
        status: New status (pending, running, completed, failed)
        **kwargs: Additional fields (apify_run_id, items_scraped, errors, etc.)
    """
    supabase = get_supabase_client()
    update_data = {"status": status, **kwargs}
    supabase.table("scrape_jobs").update(update_data).eq("id", job_id).execute()


