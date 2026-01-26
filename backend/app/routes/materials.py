"""
Material pricing and catalog endpoints

Provides two main capabilities:
1. Catalog browsing - search cached materials
2. Live price lookup - get real-time prices (scrapes if needed)
"""

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.integrations.supabase import search_materials
from app.middleware.rate_limit import STANDARD_LIMIT, limiter
from app.schemas.estimate import (
    BatchPriceLookupRequest,
    BatchPriceLookupResponse,
    PriceLookupRequest,
    PriceLookupResponse,
)
from app.services.price_engine import enrich_single_material
from app.utils.affiliate import generate_affiliate_url

router = APIRouter()


@router.get("/", status_code=status.HTTP_200_OK)
@limiter.limit(STANDARD_LIMIT)
async def get_materials(
    request: Request, search: str | None = None, limit: int = 50
):
    """
    Get material pricing catalog

    Args:
        search: Optional search term for material names
        limit: Maximum number of results

    Returns:
        list[dict]: Material pricing data
    """
    if search:
        materials = await search_materials(search, limit)
    else:
        # Return recent materials if no search term
        materials = await search_materials("", limit)

    return {"materials": materials, "count": len(materials), "ok": True}


@router.get("/{material_name}/history", status_code=status.HTTP_200_OK)
@limiter.limit(STANDARD_LIMIT)
async def get_material_history(
    request: Request, material_name: str, limit: int = 20
):
    """
    Get price history for specific material

    Args:
        material_name: Material name to lookup
        limit: Maximum number of historical entries

    Returns:
        dict: Material price history
    """
    history = await search_materials(material_name, limit)

    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No pricing data found for '{material_name}'",
        )

    return {
        "material_name": material_name,
        "history": history,
        "count": len(history),
        "ok": True,
    }


# =============================================================================
# Live Price Lookup Endpoints (scrapes Tokopedia if not in cache)
# =============================================================================


@router.get("/price", status_code=status.HTTP_200_OK, response_model=PriceLookupResponse)
@limiter.limit(STANDARD_LIMIT)
async def get_material_price(
    request: Request,
    q: str = Query(
        ...,
        min_length=2,
        max_length=200,
        description="Material name to search (e.g., 'gypsum board', 'tempered glass 8mm')",
    ),
    qty: float = Query(
        default=1.0,
        gt=0,
        le=10000,
        description="Quantity needed (default: 1 for unit price)",
    ),
    unit: str = Query(
        default="pcs",
        description="Unit of measurement (m2, pcs, kg, liter, etc.)",
    ),
):
    """
    Get real-time price for a specific material.

    This endpoint:
    1. Checks cache first (instant, no cost)
    2. Scrapes Tokopedia if cache miss (~$0.01 per scrape)
    3. Caches result for future lookups

    Perfect for quick price checks like:
    - "How much is gypsum board per m²?"
    - "What's the price for 8mm tempered glass?"

    Args:
        q: Material name to search
        qty: Quantity needed (affects total_price_idr)
        unit: Unit of measurement

    Returns:
        PriceLookupResponse: Price data with source and confidence
    """
    # Use the existing enrichment logic that handles caching
    result = await enrich_single_material({
        "material_name": q,
        "quantity": qty,
        "unit": unit,
    })

    # Generate affiliate URL if marketplace URL exists
    marketplace_url = result.get("marketplace_url")
    affiliate_url = generate_affiliate_url(marketplace_url) if marketplace_url else None

    return PriceLookupResponse(
        material_name=result["material_name"],
        unit_price_idr=result["unit_price_idr"],
        total_price_idr=result["total_price_idr"],
        quantity=result["quantity"],
        unit=result["unit"],
        source=result["source"],
        confidence=result["confidence"],
        marketplace_url=marketplace_url,
        affiliate_url=affiliate_url,
    )


@router.post("/prices", status_code=status.HTTP_200_OK, response_model=BatchPriceLookupResponse)
@limiter.limit("10/minute")  # Stricter limit for batch operations
async def get_material_prices_batch(
    request: Request,
    body: BatchPriceLookupRequest,
):
    """
    Get prices for multiple materials in one request.

    Useful when you have a list of specific materials to price.
    Limited to 20 items per request to manage costs.

    Each item is processed with:
    1. Cache check (free)
    2. Tokopedia scrape if needed (~$0.01 each)
    3. Results cached for future lookups

    Args:
        body: List of materials with quantities and units

    Returns:
        BatchPriceLookupResponse: All prices with summary stats
    """
    prices = []
    total_cost = 0
    cache_hits = 0
    scrape_count = 0

    for item in body.materials:
        result = await enrich_single_material({
            "material_name": item.material_name,
            "quantity": item.quantity,
            "unit": item.unit,
        })

        # Track cache vs scrape
        source = result.get("source", "")
        if source in ("cached", "historical", "historical_fuzzy"):
            cache_hits += 1
        elif source == "tokopedia":
            scrape_count += 1

        # Generate affiliate URL
        marketplace_url = result.get("marketplace_url")
        affiliate_url = generate_affiliate_url(marketplace_url) if marketplace_url else None

        price_response = PriceLookupResponse(
            material_name=result["material_name"],
            unit_price_idr=result["unit_price_idr"],
            total_price_idr=result["total_price_idr"],
            quantity=result["quantity"],
            unit=result["unit"],
            source=result["source"],
            confidence=result["confidence"],
            marketplace_url=marketplace_url,
            affiliate_url=affiliate_url,
        )
        prices.append(price_response)
        total_cost += result["total_price_idr"]

    return BatchPriceLookupResponse(
        prices=prices,
        total_cost_idr=total_cost,
        items_priced=len(prices),
        cache_hits=cache_hits,
        scrape_count=scrape_count,
    )
