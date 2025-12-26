"""
Price enrichment engine for BOM items
Combines semantic matching, scraping, and caching

Uses quality-based filtering to prioritize reliable sellers.
Designed for future multi-source aggregation (Shopee, local stores, etc.)
"""

import re

from app.integrations.apify import get_best_price, scrape_tokopedia_prices
from app.services.semantic_matcher import enhance_search_term, match_material


async def enrich_single_material(material: dict) -> dict:
    """
    Enrich single material with pricing data

    Priority:
    1. Exact match from historical data
    2. Fuzzy match from historical data
    3. Real-time scraping from Tokopedia

    Args:
        material: Material dict with name, quantity, unit

    Returns:
        dict: Material enriched with pricing
    """
    material_name = material["material_name"]
    quantity = material["quantity"]

    # Try semantic matching first (exact + fuzzy)
    matched = await match_material(material_name)

    if matched:
        # Cache hit - use historical data
        unit_price = matched["unit_price_idr"]
        total_price = int(unit_price * quantity)

        return {
            "material_name": material_name,
            "english_name": material.get("english_name"),  # Pass through from OpenAI
            "quantity": quantity,
            "unit": material["unit"],
            "unit_price_idr": unit_price,
            "total_price_idr": total_price,
            "source": matched["source"],
            "confidence": matched["confidence"],
            "marketplace_url": matched.get("marketplace_url"),
        }

    # Cache miss - scrape Tokopedia with quality filtering
    try:
        # Enhance search term for better marketplace results
        search_term = await enhance_search_term(material_name)

        # Fetch more results for quality filtering (will filter down)
        products = await scrape_tokopedia_prices(search_term, max_results=10)

        # If no products found, try with simplified search term
        if not products:
            simplified_term = _extract_core_material(material_name)
            if simplified_term != search_term:
                print(f"Retrying with simplified term: '{simplified_term}' (was: '{search_term}')")
                products = await scrape_tokopedia_prices(simplified_term, max_results=10)

        if products:
            # Get best price using quality-based filtering
            # Filters unreliable sellers, uses median of trusted products
            price_result = get_best_price(products)

            if price_result["price_idr"] > 0:
                unit_price = price_result["price_idr"]
                total_price = int(unit_price * quantity)

                # Confidence based on quality filtering results
                # Higher confidence when more products qualified
                base_confidence = 0.75
                quality_bonus = min(0.15, price_result["products_qualified"] * 0.03)
                confidence = base_confidence + quality_bonus

                # Use best quality product's URL
                best_product = price_result["source_product"]
                marketplace_url = best_product["url"] if best_product else None

                return {
                    "material_name": material_name,
                    "english_name": material.get("english_name"),  # Pass through from OpenAI
                    "quantity": quantity,
                    "unit": material["unit"],
                    "unit_price_idr": unit_price,
                    "total_price_idr": total_price,
                    "source": "tokopedia",
                    "confidence": confidence,
                    "marketplace_url": marketplace_url,
                    "quality_score": price_result["quality_score"],
                    "products_analyzed": price_result["products_analyzed"],
                }

    except Exception as e:
        print(f"Scraping failed for {material_name}: {e}")

    # Fallback: Use estimation (very low confidence)
    estimated_price = estimate_price_fallback(material)
    total_price = int(estimated_price * quantity)

    return {
        "material_name": material_name,
        "english_name": material.get("english_name"),  # Pass through from OpenAI
        "quantity": quantity,
        "unit": material["unit"],
        "unit_price_idr": estimated_price,
        "total_price_idr": total_price,
        "source": "estimated",
        "confidence": 0.3,
        "marketplace_url": None,
    }


async def enrich_bom_with_prices(
    bom_items: list[dict],
    on_progress: callable = None,
) -> list[dict]:
    """
    Enrich entire BOM with pricing data

    Args:
        bom_items: List of materials from BOM generation
        on_progress: Optional callback(current, total, material_name, source) for progress updates

    Returns:
        list[dict]: Enriched materials with prices
    """
    enriched = []
    total = len(bom_items)

    for i, item in enumerate(bom_items):
        # Report progress before processing each item
        if on_progress:
            await on_progress(
                current=i,
                total=total,
                material_name=item.get("english_name") or item.get("material_name", ""),
                source="searching",
            )

        enriched_item = await enrich_single_material(item)
        enriched.append(enriched_item)

        # Report completion of this item with its source
        if on_progress:
            await on_progress(
                current=i + 1,
                total=total,
                material_name=item.get("english_name") or item.get("material_name", ""),
                source=enriched_item.get("source", "unknown"),
            )

    return enriched


def _extract_core_material(name: str) -> str:
    """
    Extract the core material name for fallback search.

    Simplifies technical names to basic Indonesian search terms.
    Example: "Campuran Beton 25 MPa" -> "beton" or "semen"
    """
    # Common material mappings to simple Indonesian search terms
    material_keywords = {
        # Structural
        "beton": "semen",
        "concrete": "semen",
        "semen": "semen 50kg",
        "cement": "semen 50kg",
        "besi": "besi beton",
        "iron": "besi beton",
        "steel": "besi beton",
        "baja": "baja ringan",
        # Finishing
        "keramik": "keramik lantai",
        "ceramic": "keramik lantai",
        "tile": "keramik lantai",
        "cat": "cat tembok",
        "paint": "cat tembok",
        "granit": "granit lantai",
        "granite": "granit lantai",
        # Plumbing
        "pipa": "pipa pvc",
        "pipe": "pipa pvc",
        "kran": "kran air",
        "faucet": "kran air",
        "closet": "closet duduk",
        "toilet": "closet duduk",
        # Waterproofing
        "waterproof": "waterproofing",
        "membran": "waterproofing",
        "membrane": "waterproofing",
        "bitumen": "waterproofing",
        # Electrical
        "kabel": "kabel listrik",
        "cable": "kabel listrik",
        "lampu": "lampu led",
        "lamp": "lampu led",
        "light": "lampu led",
        "saklar": "saklar",
        "switch": "saklar",
        # Pool specific
        "kolam": "keramik kolam",
        "pool": "keramik kolam",
        "filter": "filter kolam",
        "pompa": "pompa air",
        "pump": "pompa air",
    }

    name_lower = name.lower()

    # Try to find a matching keyword
    for keyword, search_term in material_keywords.items():
        if keyword in name_lower:
            return search_term

    # Fallback: extract first 2 words and remove numbers/specs
    words = re.sub(r"[0-9]+[a-zA-Z]*", "", name_lower).split()
    core_words = [w for w in words[:2] if len(w) > 2]

    return " ".join(core_words) if core_words else name[:20]


def estimate_price_fallback(material: dict) -> int:
    """
    Fallback price estimation when no data available
    Uses simple heuristics based on material category

    Args:
        material: Material dictionary

    Returns:
        int: Estimated unit price in IDR
    """
    category = material.get("category", "miscellaneous").lower()
    unit = material.get("unit", "pcs").lower()

    # Simple heuristic based on category and unit
    base_prices = {
        "structural": {"m2": 500000, "m3": 2000000, "kg": 15000, "pcs": 50000},
        "finishing": {"m2": 300000, "pcs": 25000, "liter": 100000, "kg": 50000},
        "electrical": {"pcs": 75000, "meter": 15000, "set": 200000},
        "plumbing": {"pcs": 100000, "meter": 25000, "set": 250000},
        "hvac": {"pcs": 500000, "set": 2000000},
        "landscaping": {"m2": 150000, "pcs": 50000, "kg": 20000},
        "fixtures": {"pcs": 150000, "set": 500000},
        "miscellaneous": {"pcs": 50000, "kg": 25000, "liter": 75000},
    }

    # Get category prices, default to miscellaneous
    category_prices = base_prices.get(category, base_prices["miscellaneous"])

    # Get unit price, default to 'pcs'
    return category_prices.get(unit, category_prices.get("pcs", 50000))
