"""
Apify client for Tokopedia product scraping

Includes quality-based filtering to prioritize reliable sellers.
Designed for future multi-source aggregation (Shopee, local stores, etc.)
"""

from dataclasses import dataclass
from functools import lru_cache

from apify_client import ApifyClient
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.utils.resilience import with_circuit_breaker


# =============================================================================
# Product Quality Scoring
# =============================================================================

@dataclass
class ProductScore:
    """Quality score breakdown for a product listing."""

    product: dict
    total_score: float
    rating_score: float
    sales_score: float
    price_score: float  # Relative to median (penalize outliers)


def score_product(product: dict, median_price: int) -> ProductScore:
    """
    Score a product based on seller reliability signals.

    Scoring weights (total = 1.0):
    - Rating: 0.4 (seller trustworthiness)
    - Sales volume: 0.35 (market validation)
    - Price proximity: 0.25 (outlier penalty)

    Args:
        product: Product dict with rating, sold_count, price_idr
        median_price: Median price for outlier detection

    Returns:
        ProductScore with breakdown
    """
    # Rating score (0-5 scale normalized to 0-1)
    rating = product.get("rating", 0)
    rating_score = min(rating / 5.0, 1.0)

    # Sales volume score (logarithmic scale, caps at 10k sales)
    sold = product.get("sold_count", 0)
    if sold <= 0:
        sales_score = 0.0
    elif sold >= 10000:
        sales_score = 1.0
    else:
        # Log scale: 10 sales = 0.25, 100 = 0.5, 1000 = 0.75, 10000 = 1.0
        import math

        sales_score = math.log10(sold + 1) / 4.0

    # Price proximity score (penalize outliers from median)
    price = product.get("price_idr", 0)
    if median_price > 0 and price > 0:
        # Calculate deviation from median (0-1 scale, 1 = at median)
        deviation = abs(price - median_price) / median_price
        # Score decreases as deviation increases (50% off = 0.5 score)
        price_score = max(0, 1.0 - deviation)
    else:
        price_score = 0.5  # Neutral if can't calculate

    # Weighted total
    total = (rating_score * 0.40) + (sales_score * 0.35) + (price_score * 0.25)

    return ProductScore(
        product=product,
        total_score=total,
        rating_score=rating_score,
        sales_score=sales_score,
        price_score=price_score,
    )


def filter_quality_products(
    products: list[dict], min_score: float = 0.3, top_n: int = 3
) -> list[dict]:
    """
    Filter and rank products by quality score.

    Args:
        products: Raw product listings
        min_score: Minimum quality score threshold (0-1)
        top_n: Maximum number of products to return

    Returns:
        list[dict]: Top quality products, sorted by score (highest first)
    """
    if not products:
        return []

    # Calculate median for price scoring
    valid_prices = [p["price_idr"] for p in products if p.get("price_idr", 0) > 0]
    if not valid_prices:
        return products[:top_n]  # Fallback to raw results

    valid_prices.sort()
    mid = len(valid_prices) // 2
    median_price = (
        valid_prices[mid]
        if len(valid_prices) % 2 == 1
        else (valid_prices[mid - 1] + valid_prices[mid]) // 2
    )

    # Score all products
    scored = [score_product(p, median_price) for p in products]

    # Filter by minimum score and sort by total score
    qualified = [s for s in scored if s.total_score >= min_score]

    # If no products meet threshold, return best available
    if not qualified:
        qualified = sorted(scored, key=lambda s: s.total_score, reverse=True)[:top_n]
    else:
        qualified = sorted(qualified, key=lambda s: s.total_score, reverse=True)[:top_n]

    return [s.product for s in qualified]


@lru_cache
def get_apify_client() -> ApifyClient:
    """
    Get singleton Apify client instance

    Returns:
        ApifyClient: Configured Apify client
    """
    settings = get_settings()
    return ApifyClient(settings.apify_token)


@with_circuit_breaker("apify")
@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
async def scrape_tokopedia_prices(
    material_name: str, max_results: int = 5
) -> list[dict]:
    """
    Scrape material prices from Tokopedia using Apify.

    Results are cached for 24 hours to reduce scraping costs.
    Uses retry logic for resilience against scraping failures.

    Args:
        material_name: Material to search for
        max_results: Maximum number of results to return

    Returns:
        list[dict]: Product listings with prices
            [
                {
                    "name": "Product name",
                    "price_idr": 150000,
                    "url": "https://tokopedia.com/...",
                    "seller": "Seller name",
                    "rating": 4.8,
                    "sold_count": 150
                }
            ]

    Raises:
        Exception: If scraping fails after retries
    """
    from app.utils.cache import price_scrape_cache

    # Build cache key
    cache_key = f"tokopedia:{material_name.lower()}:{max_results}"

    # Try cache first (saves Apify costs - $0.005/scrape)
    cached_result = await price_scrape_cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    client = get_apify_client()

    # Configure scraping task for Tokopedia
    run_input = {
        "query": [material_name],
        "limit": max_results,
    }

    try:
        # Run Tokopedia scraper actor
        run = client.actor("jupri/tokopedia-scraper").call(run_input=run_input)

        # Fetch results from dataset
        results = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            # Extract price from nested structure: price.number
            price_data = item.get("price", {})
            price_idr = price_data.get("number", 0) if isinstance(price_data, dict) else 0

            # Rating comes as string (e.g., "4.8"), convert to float
            rating_str = item.get("rating", "0")
            rating = float(rating_str) if rating_str else 0.0

            # Sold count is in stock.sold
            stock_data = item.get("stock", {})
            sold_count = stock_data.get("sold", 0) if isinstance(stock_data, dict) else 0

            results.append(
                {
                    "name": item.get("name", ""),
                    "price_idr": price_idr,
                    "url": item.get("url", ""),
                    "seller": item.get("shop", {}).get("name", ""),
                    "rating": rating,
                    "sold_count": sold_count,
                }
            )

        # Cache results for 24 hours
        await price_scrape_cache.set(cache_key, results, ttl=86400)

        return results

    except Exception as e:
        raise Exception(f"Tokopedia scraping failed for '{material_name}': {e}")


async def scrape_multiple_materials(materials: list[str]) -> dict[str, list[dict]]:
    """
    Scrape prices for multiple materials

    Args:
        materials: List of material names to search

    Returns:
        dict: Material name -> list of products
    """
    results = {}

    for material in materials:
        try:
            products = await scrape_tokopedia_prices(material, max_results=3)
            results[material] = products
        except Exception as e:
            # Log error but continue with other materials
            results[material] = []
            print(f"Scraping failed for {material}: {e}")

    return results


def calculate_median_price(products: list[dict]) -> int:
    """
    Calculate median price from scraped products

    Args:
        products: List of product dictionaries with 'price_idr' key

    Returns:
        int: Median price in IDR, or 0 if no products
    """
    if not products:
        return 0

    prices = sorted([p["price_idr"] for p in products if p.get("price_idr", 0) > 0])

    if not prices:
        return 0

    mid = len(prices) // 2
    if len(prices) % 2 == 0:
        return (prices[mid - 1] + prices[mid]) // 2
    else:
        return prices[mid]


def get_best_price(products: list[dict]) -> dict:
    """
    Get the best price from quality-filtered products.

    Uses quality scoring to filter unreliable sellers, then returns
    median price from remaining trusted products.

    This is the primary function for price lookups - use this instead
    of calculate_median_price for more robust results.

    Args:
        products: Raw product listings from scraper

    Returns:
        dict: Price result with metadata
            {
                "price_idr": int,        # Recommended price
                "source_product": dict,  # Best quality product
                "quality_score": float,  # Score of best product
                "products_analyzed": int,
                "products_qualified": int,
            }
    """
    if not products:
        return {
            "price_idr": 0,
            "source_product": None,
            "quality_score": 0,
            "products_analyzed": 0,
            "products_qualified": 0,
        }

    # Filter to quality products
    quality_products = filter_quality_products(products, min_score=0.3, top_n=5)

    if not quality_products:
        # Fallback to raw median if no quality products
        return {
            "price_idr": calculate_median_price(products),
            "source_product": products[0] if products else None,
            "quality_score": 0,
            "products_analyzed": len(products),
            "products_qualified": 0,
        }

    # Calculate median from quality products only
    median_price = calculate_median_price(quality_products)

    # Best product is first (highest score)
    best_product = quality_products[0]

    # Calculate score for reporting
    valid_prices = [p["price_idr"] for p in products if p.get("price_idr", 0) > 0]
    raw_median = calculate_median_price(products)
    score = score_product(best_product, raw_median)

    return {
        "price_idr": median_price,
        "source_product": best_product,
        "quality_score": score.total_score,
        "products_analyzed": len(products),
        "products_qualified": len(quality_products),
    }
