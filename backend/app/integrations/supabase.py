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
    response = supabase.table("projects").select("*").eq("id", project_id).execute()
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
    response = supabase.table("projects").update(kwargs).eq("id", project_id).execute()
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
        supabase.table("materials").select("*").eq("category", category).execute()
    )
    return response.data if response.data else []


async def update_material_prices(
    material_id: str,
    price_min: float,
    price_max: float,
    price_avg: float,
    sample_size: int,
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
    supabase.table("materials").update(
        {
            "price_min": price_min,
            "price_max": price_max,
            "price_avg": price_avg,
            "price_sample_size": sample_size,
            "price_updated_at": "now()",
        }
    ).eq("id", material_id).execute()


# ============================================
# MATERIAL PRICE CACHE LAYER
# ============================================

CACHE_TTL_DAYS = 7  # Materials price cache validity period


async def get_cached_material_price(material_name: str) -> dict | None:
    """
    Look up cached price from materials table using name or alias matching.

    This is Tier 2 of the three-tier caching strategy:
    - Tier 1: In-memory TTLCache (60s) - checked first in apify.py
    - Tier 2: Supabase materials table (7 days) - this function
    - Tier 3: Live Apify scrape - fallback when cache misses

    Args:
        material_name: Material to search for (Indonesian or English name)

    Returns:
        dict | None: Cached price data if found and fresh, None otherwise
            {
                "material_id": "uuid",
                "name_id": "Semen Tiga Roda 40kg",
                "price_min": 75000,
                "price_max": 95000,
                "price_avg": 85000,
                "price_median": 84000,
                "price_sample_size": 5,
                "price_updated_at": "2025-12-20T10:00:00Z",
                "is_fresh": True
            }
    """
    from datetime import datetime, timedelta, timezone

    from app.utils.text import normalize_material_name

    supabase = get_supabase_client()

    # Generate canonical normalized name for deterministic lookup
    # This handles word order, spacing, and unit variations
    canonical_query = normalize_material_name(material_name)
    legacy_query = material_name.lower().strip()

    # Priority 1: Exact match on normalized_name column (fastest, most reliable)
    # This is the primary lookup mechanism for cache hits
    material = None
    if canonical_query:
        response = (
            supabase.table("materials")
            .select("*")
            .eq("normalized_name", canonical_query)
            .limit(1)
            .execute()
        )
        material = response.data[0] if response.data else None

    # Priority 2: Fallback to legacy name matching (for pre-migration data)
    if not material:
        response = (
            supabase.table("materials")
            .select("*")
            .or_(f"name_id.ilike.{legacy_query},name_en.ilike.{legacy_query}")
            .limit(1)
            .execute()
        )
        material = response.data[0] if response.data else None

    # Priority 3: Alias search (catches brand variations like "semen tiga roda")
    if not material:
        response = (
            supabase.table("materials")
            .select("*")
            .contains("aliases", [legacy_query])
            .limit(1)
            .execute()
        )
        material = response.data[0] if response.data else None

    # Priority 4: Fuzzy substring search on names (last resort)
    if not material:
        response = (
            supabase.table("materials")
            .select("*")
            .or_(f"name_id.ilike.%{legacy_query}%,name_en.ilike.%{legacy_query}%")
            .limit(1)
            .execute()
        )
        material = response.data[0] if response.data else None

    if not material:
        return None

    # Check if price data exists and is fresh
    price_updated_at = material.get("price_updated_at")
    if not price_updated_at or not material.get("price_avg"):
        return None  # No cached price data

    # Parse timestamp and check freshness
    try:
        if isinstance(price_updated_at, str):
            # Handle ISO format with or without timezone
            updated_at = datetime.fromisoformat(price_updated_at.replace("Z", "+00:00"))
        else:
            updated_at = price_updated_at

        # Make timezone-aware if needed
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        cache_expiry = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)
        is_fresh = updated_at > cache_expiry

    except (ValueError, TypeError):
        is_fresh = False

    return {
        "material_id": material.get("id"),
        "name_id": material.get("name_id"),
        "name_en": material.get("name_en"),
        "price_min": material.get("price_min"),
        "price_max": material.get("price_max"),
        "price_avg": material.get("price_avg"),
        "price_median": material.get("price_median"),
        "price_sample_size": material.get("price_sample_size", 0),
        "price_updated_at": price_updated_at,
        "is_fresh": is_fresh,
        "tokopedia_search": material.get("tokopedia_search"),
        "tokopedia_affiliate_url": material.get("tokopedia_affiliate_url"),
        "unit": material.get("unit"),
    }


async def save_material_price_cache(
    material_name: str,
    prices: list[dict],
    tokopedia_search: str | None = None,
) -> str | None:
    """
    Save scraped prices to materials table as cache.

    If material exists, updates price fields and seller stats.
    If material doesn't exist, creates a new entry.

    Args:
        material_name: Material name (used for lookup or creation)
        prices: List of scraped product prices from Tokopedia
            [{"price_idr": 85000, "name": "...", "rating": 4.8, "sold_count": 100, ...}, ...]
        tokopedia_search: Optional search query used for scraping

    Returns:
        str | None: Material ID if saved successfully, None otherwise
    """
    if not prices:
        return None

    # Calculate price statistics
    # Handle None values safely by converting to 0 first
    valid_prices = [
        p.get("price_idr", 0) or 0 for p in prices if (p.get("price_idr", 0) or 0) > 0
    ]
    if not valid_prices:
        return None

    import statistics

    valid_prices.sort()
    sample_size = len(valid_prices)
    price_min = valid_prices[0]
    price_max = valid_prices[-1]
    price_avg = sum(valid_prices) / sample_size
    # Use statistics.median for correct handling of even-length samples
    # This uses true division (not integer division) for proper precision
    price_median = statistics.median(valid_prices)

    # Calculate seller statistics from scraped data
    # Import the mapper from apify module
    from app.integrations.apify import (
        map_tokopedia_product,
        aggregate_seller_stats,
        get_best_price,
    )

    mapped_products = [map_tokopedia_product(p) for p in prices]
    seller_stats = aggregate_seller_stats(mapped_products)

    # Get the best quality product URL for affiliate links
    # This ensures cached lookups return a real Tokopedia product URL
    best_price_result = get_best_price(prices)
    best_product = best_price_result.get("source_product")
    best_product_url = best_product.get("url", "") if best_product else ""

    supabase = get_supabase_client()

    # Normalize material name for consistent storage and lookup
    # Strip whitespace, normalize to title case for display
    collapsed_name = " ".join(material_name.strip().split())  # Collapse whitespace
    display_name = collapsed_name.title()  # "semen portland" -> "Semen Portland"
    lookup_key = collapsed_name.lower()  # For case-insensitive matching

    # Generate canonical normalized name for deterministic cache lookups
    # This handles word order, spacing, and unit variations
    from app.utils.text import normalize_material_name

    canonical_name = normalize_material_name(material_name)

    # Build update payload with price and seller stats
    update_payload = {
        "normalized_name": canonical_name,  # Canonical form for exact-match lookups
        "price_min": price_min,
        "price_max": price_max,
        "price_avg": price_avg,
        "price_median": price_median,
        "price_sample_size": sample_size,
        "price_updated_at": "now()",
        # New seller quality fields
        "rating_avg": seller_stats.get("rating_avg"),
        "rating_sample_size": seller_stats.get("rating_sample_size", 0),
        "count_sold_total": seller_stats.get("count_sold_total", 0),
        "seller_location": seller_stats.get("seller_location"),
        "seller_tier": seller_stats.get("seller_tier"),
        # Store actual product URL for affiliate links (not just search term)
        "tokopedia_affiliate_url": best_product_url if best_product_url else None,
    }

    # Try to find existing material (case-insensitive)
    # Use ilike with exact match pattern (no wildcards = exact case-insensitive)
    response = (
        supabase.table("materials")
        .select("id")
        .or_(f"name_id.ilike.{lookup_key},name_en.ilike.{lookup_key}")
        .limit(1)
        .execute()
    )

    if response.data:
        # Update existing material
        material_id = response.data[0]["id"]
        supabase.table("materials").update(update_payload).eq(
            "id", material_id
        ).execute()
        return material_id

    # Also check aliases array (catches "semen tiga roda" -> "Semen Portland")
    alias_response = (
        supabase.table("materials")
        .select("id")
        .contains("aliases", [lookup_key])
        .limit(1)
        .execute()
    )

    if alias_response.data:
        material_id = alias_response.data[0]["id"]
        supabase.table("materials").update(update_payload).eq(
            "id", material_id
        ).execute()
        return material_id

    # Create new material entry (dynamic cache entry)
    # Generate a material code for new entries
    import uuid

    material_code = f"DYN-{uuid.uuid4().hex[:8].upper()}"

    # Infer unit from material name if possible
    unit = _infer_unit_from_name(collapsed_name)

    new_material = {
        "material_code": material_code,
        "name_id": display_name,  # Normalized title case
        "name_en": display_name,  # Same as ID for dynamic entries
        "category": "dynamic",  # Mark as dynamically cached
        "unit": unit,
        "tokopedia_search": tokopedia_search or collapsed_name,
        "aliases": [lookup_key],  # Store lowercase for matching
        **update_payload,  # Include all price and seller stats (including normalized_name)
    }

    response = supabase.table("materials").insert(new_material).execute()
    return response.data[0]["id"] if response.data else None


def _infer_unit_from_name(material_name: str) -> str:
    """
    Infer appropriate unit from material name patterns.

    Args:
        material_name: Normalized material name

    Returns:
        str: Inferred unit (e.g., "kg", "m²", "buah") or "pcs" as default
    """
    name_lower = material_name.lower()

    # Weight-based materials
    if any(w in name_lower for w in ["kg", "kilogram", "gram"]):
        return "kg"
    if any(w in name_lower for w in ["sak", "zak", "bag"]):
        return "sak"

    # Length/area-based materials
    if "m²" in name_lower or "m2" in name_lower or "meter persegi" in name_lower:
        return "m²"
    if "m³" in name_lower or "m3" in name_lower or "kubik" in name_lower:
        return "m³"
    if any(w in name_lower for w in ["meter", "4m", "6m"]):
        return "meter"

    # Sheet/board materials
    if any(
        w in name_lower for w in ["lembar", "sheet", "plywood", "gypsum", "triplek"]
    ):
        return "lembar"

    # Rod/bar materials
    if any(w in name_lower for w in ["batang", "besi", "pipa", "hollow"]):
        return "batang"

    # Liquid/volume materials
    if any(w in name_lower for w in ["liter", "galon"]):
        return "liter"

    # Individual items (tiles, bricks, fittings)
    if any(w in name_lower for w in ["bata", "keramik", "genteng", "kran", "saklar"]):
        return "buah"

    # Default to pieces
    return "pcs"


async def get_material_by_alias(alias: str) -> dict | None:
    """
    Look up material by alias using PostgreSQL array containment.

    Args:
        alias: Alias to search for (case-insensitive)

    Returns:
        dict | None: Material data if found
    """
    supabase = get_supabase_client()
    normalized_alias = alias.lower().strip()

    response = (
        supabase.table("materials")
        .select("*")
        .contains("aliases", [normalized_alias])
        .limit(1)
        .execute()
    )

    return response.data[0] if response.data else None


async def get_stale_materials(max_age_days: int = 7, limit: int = 50) -> list[dict]:
    """
    Get materials with stale or missing price data for cache refresh.

    Used by the weekly cache refresh job to identify materials
    that need price updates.

    Args:
        max_age_days: Consider prices older than this stale
        limit: Maximum number of materials to return

    Returns:
        list[dict]: Materials needing price refresh
    """
    from datetime import datetime, timedelta, timezone

    supabase = get_supabase_client()
    cutoff_date = (
        datetime.now(timezone.utc) - timedelta(days=max_age_days)
    ).isoformat()

    # Get materials with stale or missing prices
    # Priority: materials with no price_updated_at, then oldest first
    response = (
        supabase.table("materials")
        .select(
            "id, material_code, name_id, name_en, tokopedia_search, price_updated_at"
        )
        .or_(f"price_updated_at.is.null,price_updated_at.lt.{cutoff_date}")
        .order("price_updated_at", desc=False, nullsfirst=True)
        .limit(limit)
        .execute()
    )

    return response.data if response.data else []


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
    response = supabase.table("workers").select("*").eq("id", worker_id).execute()
    return response.data[0] if response.data else None


async def get_workers_by_specialization(
    specialization: str, area: str | None = None, limit: int = 20
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

    response = query.order("trust_score", desc=True).limit(limit).execute()
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
    worker_id: str, trust_score: int, trust_level: str, trust_breakdown: dict
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
    supabase.table("workers").update(
        {
            "trust_score": trust_score,
            "trust_level": trust_level,
            "trust_breakdown": trust_breakdown,
            "last_score_calculated_at": "now()",
        }
    ).eq("id", worker_id).execute()


async def bulk_insert_workers(workers: list[dict]) -> list[dict]:
    """
    Insert multiple workers at once (for scraper results).

    Handles deduplication by checking gmaps_place_id uniqueness.
    On conflict, updates existing records instead of inserting.

    Args:
        workers: List of worker dictionaries

    Returns:
        list[dict]: Inserted/updated worker records
    """
    if not workers:
        return []

    supabase = get_supabase_client()

    # Use upsert with gmaps_place_id as conflict target
    response = (
        supabase.table("workers")
        .upsert(workers, on_conflict="gmaps_place_id")
        .execute()
    )
    return response.data if response.data else []


async def get_cached_workers(
    specialization: str, max_age_hours: int = 168  # 7 days default
) -> list[dict] | None:
    """
    Check if we have recently scraped workers for a specialization.

    Args:
        specialization: Worker specialization (pool, bathroom, etc.)
        max_age_hours: Maximum cache age in hours (default 7 days = 168h)

    Returns:
        list[dict] | None: Cached workers if fresh, None if stale/missing
    """
    from datetime import datetime, timedelta, timezone

    supabase = get_supabase_client()
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    response = (
        supabase.table("workers")
        .select("*")
        .contains("specializations", [specialization])
        .eq("is_active", True)
        .gte("last_scraped_at", cutoff_time.isoformat())
        .order("trust_score", desc=True)
        .execute()
    )

    results = response.data if response.data else []

    # Return None if no results (cache miss), otherwise return workers
    return results if results else None


async def update_worker_scraped_timestamp(worker_ids: list[str]) -> None:
    """
    Update last_scraped_at timestamp for workers (bulk operation).

    Args:
        worker_ids: List of worker UUIDs to update
    """
    if not worker_ids:
        return

    from datetime import datetime, timezone

    supabase = get_supabase_client()

    # Batch update using IN clause
    now = datetime.now(timezone.utc).isoformat()
    supabase.table("workers").update({"last_scraped_at": now, "updated_at": now}).in_(
        "id", worker_ids
    ).execute()


async def search_workers(
    specialization: str | None = None,
    location: str | None = None,
    min_trust_score: int = 0,
    min_rating: float = 0.0,
    limit: int = 20,
) -> list[dict]:
    """
    Search workers with flexible filters.

    Args:
        specialization: Filter by specialization (pool, bathroom, etc.)
        location: Filter by location (Canggu, Ubud, etc.)
        min_trust_score: Minimum trust score (0-100)
        min_rating: Minimum Google Maps rating (0.0-5.0)
        limit: Maximum results

    Returns:
        list[dict]: Matching workers sorted by trust score
    """
    supabase = get_supabase_client()
    query = supabase.table("workers").select("*").eq("is_active", True)

    if specialization:
        query = query.contains("specializations", [specialization])

    if location:
        query = query.ilike("location", f"%{location}%")

    if min_trust_score > 0:
        query = query.gte("trust_score", min_trust_score)

    if min_rating > 0:
        query = query.gte("gmaps_rating", min_rating)

    response = query.order("trust_score", desc=True).limit(limit).execute()

    return response.data if response.data else []


# ============================================
# WORKER UNLOCKS
# ============================================


async def check_worker_unlock(worker_id: str, user_email: str) -> bool:
    """
    Check if user has unlocked a specific worker's contact information.

    Args:
        worker_id: UUID of the worker
        user_email: User's email address

    Returns:
        bool: True if unlocked, False otherwise
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("worker_unlocks")
        .select("id")
        .eq("worker_id", worker_id)
        .eq("user_email", user_email)
        .execute()
    )
    return len(response.data) > 0 if response.data else False


async def create_worker_unlock(
    worker_id: str,
    user_email: str,
    payment_id: str | None = None,
    unlock_price_idr: int = 50000,
) -> dict:
    """
    Create a worker unlock record after successful payment.

    Args:
        worker_id: UUID of the worker
        user_email: User's email address
        payment_id: UUID of the associated payment
        unlock_price_idr: Price paid to unlock (default 50000 IDR)

    Returns:
        dict: Created unlock record
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("worker_unlocks")
        .insert(
            {
                "worker_id": worker_id,
                "user_email": user_email,
                "payment_id": payment_id,
                "unlock_price_idr": unlock_price_idr,
            }
        )
        .execute()
    )
    return response.data[0] if response.data else {}


async def get_user_unlocked_workers(user_email: str) -> list[dict]:
    """
    Get all workers unlocked by a user.

    Args:
        user_email: User's email address

    Returns:
        list[dict]: List of unlock records with worker IDs
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("worker_unlocks")
        .select("*")
        .eq("user_email", user_email)
        .order("unlocked_at", desc=True)
        .execute()
    )
    return response.data if response.data else []


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
    response = supabase.table("payments").select("*").eq("id", payment_id).execute()
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


async def update_payment_status(payment_id: str, status: str, **kwargs) -> None:
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
    project_id: str, material_id: str, platform: str, user_session: str
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
    response = (
        supabase.table("affiliate_clicks")
        .insert(
            {
                "project_id": project_id,
                "material_id": material_id,
                "platform": platform,
                "user_session": user_session,
            }
        )
        .execute()
    )
    return response.data[0] if response.data else {}


async def update_affiliate_conversion(
    click_id: str, conversion_amount: float, commission_earned: float
) -> None:
    """
    Update affiliate click with conversion data

    Args:
        click_id: UUID of the click record
        conversion_amount: Purchase amount
        commission_earned: Commission from affiliate program
    """
    supabase = get_supabase_client()
    supabase.table("affiliate_clicks").update(
        {
            "converted": True,
            "conversion_amount": conversion_amount,
            "commission_earned": commission_earned,
            "converted_at": "now()",
        }
    ).eq("id", click_id).execute()


# ============================================
# SCRAPE JOBS
# ============================================


async def create_scrape_job(
    job_type: str, input_params: dict, apify_actor_id: str | None = None
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
    response = (
        supabase.table("scrape_jobs")
        .insert(
            {
                "job_type": job_type,
                "input_params": input_params,
                "apify_actor_id": apify_actor_id,
                "status": "pending",
            }
        )
        .execute()
    )
    return response.data[0] if response.data else {}


async def save_scrape_job(
    job_type: str,
    apify_actor_id: str,
    input_params: dict,
    estimated_cost_usd: float = 0.0,
) -> str:
    """
    Create a new scrape job with cost tracking.
    Alias for create_scrape_job with enhanced cost metadata.

    Args:
        job_type: Type of job (worker_discovery, material_pricing)
        apify_actor_id: Apify actor ID
        input_params: Actor input configuration
        estimated_cost_usd: Estimated cost for this run

    Returns:
        str: Job ID (UUID)
    """
    # Store cost metadata in input_params
    enhanced_params = {
        **input_params,
        "_meta": {
            "estimated_cost_usd": estimated_cost_usd,
            "created_by": "google_maps_scraper",
        },
    }

    job = await create_scrape_job(
        job_type=job_type, input_params=enhanced_params, apify_actor_id=apify_actor_id
    )
    return job["id"]


async def update_scrape_job(job_id: str, status: str, **kwargs) -> None:
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


async def update_scrape_job_status(
    job_id: str,
    status: str,
    apify_run_id: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    results_count: int | None = None,
    actual_cost_usd: float | None = None,
    output_data: dict | None = None,
    error_message: str | None = None,
) -> None:
    """
    Update scrape job status with detailed tracking.
    Enhanced version of update_scrape_job with cost tracking.

    Args:
        job_id: UUID of the job
        status: New status (pending, running, completed, failed)
        apify_run_id: Apify run ID
        started_at: Start timestamp
        completed_at: Completion timestamp
        results_count: Number of items scraped
        actual_cost_usd: Actual cost incurred
        output_data: Sample output data (stored in errors field for now)
        error_message: Error message if failed
    """
    update_data = {"status": status}

    if apify_run_id:
        update_data["apify_run_id"] = apify_run_id
    if started_at:
        update_data["started_at"] = started_at
    if completed_at:
        update_data["completed_at"] = completed_at
    if results_count is not None:
        update_data["items_scraped"] = results_count

    # Store cost and output metadata in errors field (JSONB)
    if (
        actual_cost_usd is not None
        or output_data is not None
        or error_message is not None
    ):
        metadata = {}
        if actual_cost_usd is not None:
            metadata["actual_cost_usd"] = actual_cost_usd
        if output_data is not None:
            metadata["sample_output"] = output_data
        if error_message is not None:
            metadata["error"] = error_message
        update_data["errors"] = metadata

    await update_scrape_job(
        job_id, status, **{k: v for k, v in update_data.items() if k != "status"}
    )
