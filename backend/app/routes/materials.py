"""
Material pricing and catalog endpoints
"""

from fastapi import APIRouter, HTTPException, Request, status

from app.integrations.supabase import get_material_price_history
from app.middleware.rate_limit import STANDARD_LIMIT, limiter

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
        materials = await get_material_price_history(search, limit)
    else:
        # Return recent materials if no search term
        materials = await get_material_price_history("", limit)

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
    history = await get_material_price_history(material_name, limit)

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
