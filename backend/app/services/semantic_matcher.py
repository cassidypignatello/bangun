"""
Two-tier semantic matching for materials: exact match + fuzzy matching
"""

from difflib import SequenceMatcher

from app.integrations.openai_client import enhance_material_description
from app.integrations.supabase import get_supabase_client, search_materials
from app.utils.text import normalize_material_name


def calculate_similarity(str1: str, str2: str) -> float:
    """
    Calculate string similarity score

    Args:
        str1: First string
        str2: Second string

    Returns:
        float: Similarity score (0.0-1.0)
    """
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def get_material_display_name(entry: dict) -> str:
    """Get the best display name from a material entry (prefer Indonesian)."""
    return entry.get("name_id") or entry.get("name_en") or ""


async def find_exact_match(material_name: str) -> dict | None:
    """
    Attempt exact match from historical data

    Uses two strategies:
    1. Normalized name exact match (fast, uses index)
    2. Fuzzy ilike search with similarity check (fallback)

    Args:
        material_name: Material to match

    Returns:
        dict | None: Cached price data if found
    """
    # Strategy 1: Fast exact match using normalized_name (indexed column)
    # This handles variations in spacing, word order, and units
    normalized = normalize_material_name(material_name)
    if normalized:
        try:
            supabase = get_supabase_client()
            response = (
                supabase.table("materials")
                .select("*")
                .eq("normalized_name", normalized)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                entry = response.data[0]
                # Verify price data exists
                price_avg = entry.get("price_avg", 0) or 0
                if price_avg > 0:
                    return {
                        "material_name": get_material_display_name(entry),
                        "unit_price_idr": int(
                            price_avg
                        ),  # Convert Decimal/float to int for Pydantic
                        "source": "cached",  # Clear indicator of cache hit
                        "confidence": 1.0,  # Exact normalized match = perfect confidence
                        # Use actual product URL if available, not just search term
                        "marketplace_url": entry.get("tokopedia_affiliate_url"),
                    }
        except Exception:
            pass  # Fall through to fuzzy search

    # Strategy 2: Fuzzy ilike search with similarity check
    history = await search_materials(material_name, limit=5)

    if not history:
        return None

    # Look for high-confidence exact match (>0.95 similarity)
    for entry in history:
        # Check similarity against both Indonesian and English names
        name_id = entry.get("name_id", "")
        name_en = entry.get("name_en", "")

        similarity_id = calculate_similarity(material_name, name_id) if name_id else 0
        similarity_en = calculate_similarity(material_name, name_en) if name_en else 0
        similarity = max(similarity_id, similarity_en)

        if similarity > 0.95:
            return {
                "material_name": get_material_display_name(entry),
                "unit_price_idr": int(
                    entry.get("price_avg", 0) or 0
                ),  # Convert to int for Pydantic
                "source": "historical",
                "confidence": similarity,
                # Use actual product URL if available, not just search term
                "marketplace_url": entry.get("tokopedia_affiliate_url"),
            }

    return None


async def find_fuzzy_match(material_name: str, threshold: float = 0.90) -> dict | None:
    """
    Fuzzy matching with historical data

    Secondary fallback after normalized_name exact match fails.
    Higher threshold (0.90) reduces false positives while catching minor variations.

    Args:
        material_name: Material to match
        threshold: Minimum similarity threshold (default 0.90 for high precision)

    Returns:
        dict | None: Best fuzzy match if above threshold
    """
    history = await search_materials(material_name, limit=20)

    if not history:
        return None

    best_match = None
    best_score = threshold

    for entry in history:
        # Check similarity against both Indonesian and English names
        name_id = entry.get("name_id", "")
        name_en = entry.get("name_en", "")

        similarity_id = calculate_similarity(material_name, name_id) if name_id else 0
        similarity_en = calculate_similarity(material_name, name_en) if name_en else 0
        similarity = max(similarity_id, similarity_en)

        if similarity > best_score:
            best_score = similarity
            best_match = {
                "material_name": get_material_display_name(entry),
                "unit_price_idr": int(
                    entry.get("price_avg", 0) or 0
                ),  # Convert to int for Pydantic
                "source": "historical_fuzzy",
                "confidence": similarity,
                # Use actual product URL if available, not just search term
                "marketplace_url": entry.get("tokopedia_affiliate_url"),
            }

    return best_match


async def enhance_search_term(material_name: str, context: str = "") -> str:
    """
    Enhance material name for better marketplace searching

    Args:
        material_name: Original material name
        context: Additional context

    Returns:
        str: Enhanced search term
    """
    try:
        enhanced = await enhance_material_description(material_name, context)
        return enhanced
    except Exception:
        # Fallback to original name
        return material_name


async def match_material(material_name: str, context: str = "") -> dict | None:
    """
    Two-tier matching: exact -> fuzzy -> None

    Args:
        material_name: Material to match
        context: Additional context for matching

    Returns:
        dict | None: Matched price data or None if no match
    """
    # Tier 1: Exact match
    exact = await find_exact_match(material_name)
    if exact:
        return exact

    # Tier 2: Fuzzy match
    fuzzy = await find_fuzzy_match(material_name)
    if fuzzy:
        return fuzzy

    # No match found - will need to scrape
    return None
