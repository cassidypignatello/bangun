"""
Price enrichment engine for BOM items
Combines semantic matching, scraping, and caching
"""

from app.integrations.apify import calculate_median_price, scrape_tokopedia_prices
from app.services.semantic_matcher import match_material, enhance_search_term


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
            "quantity": quantity,
            "unit": material["unit"],
            "unit_price_idr": unit_price,
            "total_price_idr": total_price,
            "source": matched["source"],
            "confidence": matched["confidence"],
            "marketplace_url": matched.get("marketplace_url"),
        }

    # Cache miss - scrape Tokopedia
    try:
        # Enhance search term for better results
        search_term = await enhance_search_term(material_name)

        products = await scrape_tokopedia_prices(search_term, max_results=5)

        if products:
            # Calculate median price for robustness
            median_price = calculate_median_price(products)

            if median_price > 0:
                total_price = int(median_price * quantity)

                # Note: Prices are now embedded in materials table
                # Use update_material_prices() for batch updates

                return {
                    "material_name": material_name,
                    "quantity": quantity,
                    "unit": material["unit"],
                    "unit_price_idr": median_price,
                    "total_price_idr": total_price,
                    "source": "tokopedia",
                    "confidence": 0.85,
                    "marketplace_url": products[0]["url"],
                }

    except Exception as e:
        print(f"Scraping failed for {material_name}: {e}")

    # Fallback: Use estimation (very low confidence)
    estimated_price = estimate_price_fallback(material)
    total_price = int(estimated_price * quantity)

    return {
        "material_name": material_name,
        "quantity": quantity,
        "unit": material["unit"],
        "unit_price_idr": estimated_price,
        "total_price_idr": total_price,
        "source": "estimated",
        "confidence": 0.3,
        "marketplace_url": None,
    }


async def enrich_bom_with_prices(bom_items: list[dict]) -> list[dict]:
    """
    Enrich entire BOM with pricing data

    Args:
        bom_items: List of materials from BOM generation

    Returns:
        list[dict]: Enriched materials with prices
    """
    enriched = []

    for item in bom_items:
        enriched_item = await enrich_single_material(item)
        enriched.append(enriched_item)

    return enriched


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
