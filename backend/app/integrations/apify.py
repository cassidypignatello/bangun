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


@dataclass
class BestSellerScore:
    """
    Best Seller score breakdown using weighted ranking algorithm.

    Formula: Score = (Rating * 0.4) + (Sales * 0.4) + (Price * 0.2)

    Weights:
    - Rating: 40% - Seller trustworthiness and product quality
    - Sales: 40% - Market validation and popularity
    - Price: 20% - Lower price gets higher score
    """

    product: dict
    total_score: float
    rating_score: float  # Higher rating = higher score (0.4 weight)
    sales_score: float  # Higher sales = higher score (0.4 weight)
    price_score: float  # Lower price = higher score (0.2 weight)


def score_best_seller(product: dict, min_price: int, max_price: int) -> BestSellerScore:
    """
    Score a product using weighted ranking algorithm.

    Formula: Score = (Rating * 0.4) + (Sales * 0.4) + (Price * 0.2)

    Scoring weights:
    - Rating: 0.4 (higher rating = higher score, 0-5 scale normalized)
    - Sales: 0.4 (higher sales = higher score, normalized to min/max range)
    - Price: 0.2 (lower price = higher score, normalized to min/max range)

    Args:
        product: Product dict with price_idr, rating, sold_count
        min_price: Minimum price in result set (for normalization)
        max_price: Maximum price in result set (for normalization)

    Returns:
        BestSellerScore with component breakdown
    """
    # Rating score: 0-5 scale normalized to 0-1
    rating = product.get("rating", 0) or product.get("rating_average", 0) or 0
    rating_score = min(float(rating) / 5.0, 1.0) if rating > 0 else 0.0

    # Sales score: normalized to min/max range within result set
    sold = product.get("sold_count", 0) or product.get("count_sold", 0) or 0
    # Get min/max sales from products for normalization (calculated in rank_best_sellers)
    # For now, use logarithmic scale capped at 10k as fallback
    import math

    if sold <= 0:
        sales_score = 0.0
    elif sold >= 10000:
        sales_score = 1.0
    else:
        # log10 scale: 10 sales ≈ 0.25, 100 ≈ 0.5, 1000 ≈ 0.75, 10000 = 1.0
        sales_score = math.log10(sold + 1) / 4.0

    # Price score: lower price = higher score (inverted normalization)
    price = product.get("price_idr", 0) or 0
    if max_price > min_price and price > 0:
        # Normalize to 0-1 where lowest price = 1.0
        price_score = 1.0 - ((price - min_price) / (max_price - min_price))
    elif price > 0:
        price_score = 0.5  # All same price = neutral
    else:
        price_score = 0.0

    # Weighted total: Rating 40% + Sales 40% + Price 20%
    total = (rating_score * 0.4) + (sales_score * 0.4) + (price_score * 0.2)

    return BestSellerScore(
        product=product,
        total_score=total,
        rating_score=rating_score,
        sales_score=sales_score,
        price_score=price_score,
    )


def _is_product_available(product: dict, required_quantity: float = None) -> bool:
    """
    Check if product is available for purchase with sufficient stock.

    Filters out products that are:
    - Out of stock (stock = 0)
    - Not active status
    - Insufficient stock for required quantity (if specified)

    Args:
        product: Product dict from Tokopedia scrape
        required_quantity: Minimum stock needed (from BOM). If None, only checks > 0.

    Returns:
        bool: True if product is available with sufficient stock, False otherwise
    """
    # Check stock - handle various field names
    stock = product.get("stock", product.get("stockCount", product.get("stock_count")))
    if stock is not None:
        try:
            stock_int = int(stock)
            # Must have at least 1 in stock
            if stock_int <= 0:
                return False
            # Must have enough stock for the required quantity
            if required_quantity is not None and stock_int < required_quantity:
                return False
        except (ValueError, TypeError):
            pass

    # Check status - must be 'active' if status field exists
    status = product.get("status", "").lower() if product.get("status") else ""
    if status and status != "active":
        return False

    return True


def rank_best_sellers(
    products: list[dict],
    top_n: int = 5,
    required_quantity: float = None,
) -> list[BestSellerScore]:
    """
    Rank products using weighted ranking algorithm and return top N.

    Filters out:
    - Products with stock = 0
    - Products with status != 'active'
    - Products with insufficient stock for required_quantity (if specified)

    Args:
        products: List of product dicts from Tokopedia scrape
        top_n: Number of top products to return (default 5)
        required_quantity: Minimum stock needed (from BOM). If None, only checks > 0.

    Returns:
        List of BestSellerScore objects, sorted by total_score descending
    """
    if not products:
        return []

    # Filter out unavailable products (out of stock, inactive, or insufficient quantity)
    available_products = [
        p for p in products if _is_product_available(p, required_quantity)
    ]

    if not available_products:
        return []

    # Calculate price range for normalization (handle None values)
    valid_prices = [
        p.get("price_idr", 0) or 0
        for p in available_products
        if (p.get("price_idr", 0) or 0) > 0
    ]
    if not valid_prices:
        return []

    min_price = min(valid_prices)
    max_price = max(valid_prices)

    # Score only products with valid prices
    products_with_price = [
        p for p in available_products if (p.get("price_idr", 0) or 0) > 0
    ]
    scored = [score_best_seller(p, min_price, max_price) for p in products_with_price]

    # Sort by total score descending and return top N
    scored.sort(key=lambda s: s.total_score, reverse=True)
    return scored[:top_n]


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


# =============================================================================
# Price/Rating/Sold Extraction Helpers
# =============================================================================


def _extract_price(item: dict) -> int:
    """
    Extract price from various Tokopedia actor output formats.

    Supports:
    - fatihtahta format: item.price (string like "Rp85.000" or int)
    - 123webdata format: item.priceInt or item.price (int)
    - jupri format: item.price.number (nested dict)
    - Direct number formats

    Args:
        item: Product data from Apify actor

    Returns:
        int: Price in IDR, or 0 if not found
    """
    import re

    # Try priceInt field (123webdata)
    if "priceInt" in item and item["priceInt"]:
        return int(item["priceInt"])

    # Try price field (multiple formats)
    if "price" in item:
        price = item["price"]
        if isinstance(price, dict):  # jupri format: {number: 150000}
            return int(price.get("number", 0))
        elif isinstance(price, int):  # Direct int
            return price
        elif isinstance(price, float):  # Direct float
            return int(price)
        elif isinstance(price, str):
            # fatihtahta format: "Rp85.000" or "85000" or "85,000"
            # Remove currency prefix and formatting
            cleaned = re.sub(r"[^\d]", "", price)
            if cleaned:
                try:
                    return int(cleaned)
                except (ValueError, TypeError):
                    pass

    # Try priceOriginal field (some actors)
    if "priceOriginal" in item:
        price = item["priceOriginal"]
        if isinstance(price, (int, float)):
            return int(price)
        elif isinstance(price, str):
            cleaned = re.sub(r"[^\d]", "", price)
            if cleaned:
                try:
                    return int(cleaned)
                except (ValueError, TypeError):
                    pass

    return 0


def _extract_rating(item: dict) -> float:
    """
    Extract rating from various formats.

    Supports:
    - fatihtahta format: item.rating (float or string)
    - 123webdata format: item.rating (float)
    - jupri format: item.rating (nested or direct)

    Args:
        item: Product data from Apify actor

    Returns:
        float: Rating (0.0-5.0), or 0.0 if not found
    """
    # Try direct rating field (only if key exists and has truthy value)
    rating = item.get("rating")
    if rating is not None:
        if isinstance(rating, (int, float)) and rating > 0:
            return float(rating)
        elif isinstance(rating, str):
            try:
                parsed = float(rating)
                if parsed > 0:
                    return parsed
            except ValueError:
                pass

    # Try ratingAverage field (some actors use this instead)
    rating_avg = item.get("ratingAverage") or item.get("rating_average")
    if rating_avg is not None:
        if isinstance(rating_avg, (int, float)) and rating_avg > 0:
            return float(rating_avg)
        elif isinstance(rating_avg, str):
            try:
                parsed = float(rating_avg)
                if parsed > 0:
                    return parsed
            except ValueError:
                pass

    # Try nested stats.rating (some actors)
    stats = item.get("stats")
    if isinstance(stats, dict):
        stat_rating = stats.get("rating")
        if isinstance(stat_rating, (int, float)) and stat_rating > 0:
            return float(stat_rating)

    return 0.0


def _extract_sold_count(item: dict) -> int:
    """
    Extract sold count from various formats.

    Supports:
    - fatihtahta format: item.sold (string like "500+ terjual" or int)
    - 123webdata format: item.sold (int)
    - jupri format: item.stock.sold (nested)

    Args:
        item: Product data from Apify actor

    Returns:
        int: Number of units sold, or 0 if not found
    """
    import re

    # Try direct sold field
    if "sold" in item and item["sold"]:
        sold = item["sold"]
        if isinstance(sold, int):
            return sold
        elif isinstance(sold, str):
            # fatihtahta format: "500+ terjual" or "1rb+ terjual"
            # Extract numbers, handle "rb" (ribu = thousand)
            if "rb" in sold.lower():
                # Handle Indonesian "rb" (ribu = thousand) format
                # Indonesian uses . as thousands separator, , as decimal
                # Examples: "1.500rb" = 1,500,000, "2rb" = 2,000, "1,5rb" = 1,500
                match = re.search(r"([\d.,]+)\s*rb", sold.lower())
                if match:
                    try:
                        num_str = match.group(1).strip()
                        # Normalize Indonesian number format to Python float
                        has_dot = "." in num_str
                        has_comma = "," in num_str
                        if has_dot and not has_comma:
                            # Dots are thousands separators: "1.500" -> "1500"
                            num_str = num_str.replace(".", "")
                        elif has_comma and not has_dot:
                            # Comma is decimal separator: "1,5" -> "1.5"
                            num_str = num_str.replace(",", ".")
                        elif has_dot and has_comma:
                            # Both present: "1.234,56" -> "1234.56"
                            num_str = num_str.replace(".", "").replace(",", ".")
                        num = float(num_str)
                        return int(num * 1000)
                    except (ValueError, TypeError):
                        pass
            # Regular number extraction
            cleaned = re.sub(r"[^\d]", "", sold)
            if cleaned:
                try:
                    return int(cleaned)
                except (ValueError, TypeError):
                    pass

    # Try soldCount field (some actors)
    if "soldCount" in item:
        sold_count = item["soldCount"]
        if isinstance(sold_count, int):
            return sold_count
        elif isinstance(sold_count, str):
            cleaned = re.sub(r"[^\d]", "", sold_count)
            if cleaned:
                try:
                    return int(cleaned)
                except (ValueError, TypeError):
                    pass

    # Try nested stock.sold field (jupri)
    if "stock" in item:
        stock_data = item["stock"]
        if isinstance(stock_data, dict) and "sold" in stock_data:
            try:
                return int(stock_data["sold"])
            except (ValueError, TypeError):
                pass

    # Try stats.sold (some actors)
    stats = item.get("stats", {})
    if isinstance(stats, dict):
        stat_sold = stats.get("sold", 0)
        if isinstance(stat_sold, (int, float)):
            return int(stat_sold)

    return 0


def _build_tokopedia_search_url(material_name: str) -> str:
    """
    Build Tokopedia search URL from material name.

    The 123webdata/tokopedia-scraper actor requires actual URLs, not search queries.
    We construct search result URLs that the actor can scrape.

    Args:
        material_name: Material to search for

    Returns:
        str: Tokopedia search URL
    """
    import urllib.parse

    # Clean and encode search term
    search_term = material_name.strip()
    encoded_term = urllib.parse.quote_plus(search_term)

    # Construct Tokopedia search URL
    # Format: https://www.tokopedia.com/search?q=<search_term>
    return f"https://www.tokopedia.com/search?q={encoded_term}"


# =============================================================================
# Tokopedia Scraper Output Mapper
# =============================================================================


@dataclass
class TokopediaProduct:
    """
    Normalized product data from Tokopedia scrapers.

    Maps output from fatihtahta/tokopedia-scraper (and compatible actors)
    to our internal Material model fields.
    """

    name: str
    price_idr: int
    rating: float
    sold_count: int
    seller_name: str
    seller_location: str
    seller_tier: str  # official_store, power_merchant, regular
    url: str


def map_tokopedia_product(raw_item: dict) -> TokopediaProduct:
    """
    Map fatihtahta/tokopedia-scraper output to internal TokopediaProduct.

    The fatihtahta actor returns items with these fields:
    - title/name: Product title
    - price: Price string like "Rp85.000" or int
    - rating: Float rating (0.0-5.0)
    - sold: String like "500+ terjual" or "1rb+ terjual"
    - shop: Dict with name, location, badge info or string
    - url/link: Product URL

    Args:
        raw_item: Raw product dict from Apify actor

    Returns:
        TokopediaProduct: Normalized product data
    """
    # Extract basic fields using existing helpers
    price_idr = _extract_price(raw_item)
    rating = _extract_rating(raw_item)
    sold_count = _extract_sold_count(raw_item)

    # Extract product name
    name = raw_item.get("name") or raw_item.get("title") or ""

    # Extract URL
    url = raw_item.get("url") or raw_item.get("link") or ""

    # Extract seller info - handle both dict and string formats
    shop = raw_item.get("shop")
    seller_name = ""
    seller_location = ""
    seller_tier = "regular"

    if isinstance(shop, dict):
        seller_name = shop.get("name", "")
        seller_location = shop.get("location", shop.get("city", ""))

        # Determine seller tier from badge/official status
        # fatihtahta format uses badge field or isOfficial/isPowerMerchant
        badge = shop.get("badge", "").lower()
        is_official = shop.get("isOfficial", shop.get("is_official", False))
        is_power = shop.get("isPowerMerchant", shop.get("is_power_merchant", False))

        if is_official or "official" in badge:
            seller_tier = "official_store"
        elif is_power or "power" in badge or "pm" in badge:
            seller_tier = "power_merchant"
    elif isinstance(shop, str):
        seller_name = shop
    else:
        # Fallback to seller field
        seller_name = raw_item.get("seller", "")

    # Try alternate location fields if not found in shop
    if not seller_location:
        seller_location = raw_item.get("location") or raw_item.get("city") or ""

    return TokopediaProduct(
        name=name,
        price_idr=price_idr,
        rating=rating,
        sold_count=sold_count,
        seller_name=seller_name,
        seller_location=seller_location,
        seller_tier=seller_tier,
        url=url,
    )


def aggregate_seller_stats(products: list[TokopediaProduct]) -> dict:
    """
    Aggregate seller statistics from a list of mapped products.

    Calculates:
    - rating_avg: Average rating across products with ratings
    - rating_sample_size: Number of products with ratings
    - count_sold_total: Sum of all sold counts
    - seller_location: Most common seller location
    - seller_tier: Highest tier among sellers (official > power > regular)

    Args:
        products: List of TokopediaProduct instances

    Returns:
        dict: Aggregated stats ready for materials table update
    """
    if not products:
        return {}

    # Calculate average rating (exclude 0 ratings)
    ratings = [p.rating for p in products if p.rating > 0]
    rating_avg = sum(ratings) / len(ratings) if ratings else None
    rating_sample_size = len(ratings)

    # Sum total sold count
    count_sold_total = sum(p.sold_count for p in products)

    # Find most common location
    locations = [p.seller_location for p in products if p.seller_location]
    seller_location = None
    if locations:
        from collections import Counter

        location_counts = Counter(locations)
        seller_location = location_counts.most_common(1)[0][0]

    # Determine best seller tier (official > power > regular)
    tier_priority = {"official_store": 3, "power_merchant": 2, "regular": 1}
    tiers = [p.seller_tier for p in products if p.seller_tier]
    seller_tier = None
    if tiers:
        seller_tier = max(tiers, key=lambda t: tier_priority.get(t, 0))

    return {
        "rating_avg": round(rating_avg, 2) if rating_avg else None,
        "rating_sample_size": rating_sample_size,
        "count_sold_total": count_sold_total,
        "seller_location": seller_location,
        "seller_tier": seller_tier,
    }


# =============================================================================
# Tokopedia Scraping Functions
# =============================================================================


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
    Scrape material prices from Tokopedia using three-tier caching strategy.

    Caching tiers:
    1. In-memory TTLCache (60s) - instant, free
    2. Supabase materials table (7 days) - fast DB lookup, free
    3. Live Apify scrape - slow, costs $0.0015/result

    Uses fatihtahta/tokopedia-scraper actor ($1.50/1k results) for cost efficiency.

    Args:
        material_name: Material to search for
        max_results: Maximum number of results to return from live scrape (Tier 3 only)

    Returns:
        list[dict]: Product listings with prices

        IMPORTANT: Return shape differs by cache tier:

        - Tier 1 (in-memory): Returns whatever was previously cached
        - Tier 2 (Supabase): Returns SINGLE aggregated item with price statistics
            [{
                "name": "Material name",
                "price_idr": 150000,  # Average price
                "url": "",
                "seller": "Cached Price",
                "rating": 0.0,
                "sold_count": 0,
                "_cached": True,
                "_price_range": {
                    "min": 100000,
                    "max": 200000,
                    "median": 145000
                }
            }]

        - Tier 3 (live scrape): Returns up to max_results individual products
            [{
                "name": "Product name",
                "price_idr": 150000,
                "url": "https://tokopedia.com/...",
                "seller": "Seller name",
                "rating": 4.8,
                "sold_count": 150
            }, ...]

    Raises:
        Exception: If scraping fails after retries
    """
    from app.utils.cache import price_scrape_cache
    from app.integrations.supabase import (
        get_cached_material_price,
        save_material_price_cache,
    )

    # Build cache key for in-memory cache
    cache_key = f"tokopedia:{material_name.lower()}:{max_results}"

    # =========================================================================
    # TIER 1: In-memory TTLCache (60s TTL, instant, FREE)
    # =========================================================================
    cached_result = await price_scrape_cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    # =========================================================================
    # TIER 2: Supabase materials table (7-day TTL, ~50ms, FREE)
    # =========================================================================
    try:
        db_cache = await get_cached_material_price(material_name)
        if db_cache and db_cache.get("is_fresh") and db_cache.get("price_avg"):
            # NOTE: Cached response returns SINGLE aggregated item with price statistics
            # This differs from Tier 3 (live scrape) which returns up to max_results items
            # The aggregated item contains avg/min/max/median from previous scrape results
            cached_products = [
                {
                    "name": db_cache.get("name_id", material_name),
                    "price_idr": int(db_cache.get("price_avg", 0)),  # Average price
                    "url": db_cache.get(
                        "tokopedia_affiliate_url", ""
                    ),  # Product URL from cache
                    "seller": "Cached Price",
                    "rating": 0.0,
                    "sold_count": 0,
                    "_cached": True,  # Flag indicating this is cached data
                    "_price_range": {  # Additional statistics not available in live results
                        "min": db_cache.get("price_min"),
                        "max": db_cache.get("price_max"),
                        "median": db_cache.get("price_median"),
                    },
                }
            ]
            # Warm up in-memory cache (60s TTL as documented)
            # This preserves the single aggregated item for subsequent requests
            await price_scrape_cache.set(cache_key, cached_products, ttl=60)
            return cached_products
    except Exception:
        # Supabase lookup failed, continue to live scrape
        pass

    # =========================================================================
    # TIER 3: Live Apify scrape (10-30s, $0.0015/result)
    # =========================================================================
    client = get_apify_client()

    # Configure scraping task for fatihtahta/tokopedia-scraper
    # Use queries parameter (native search) instead of startUrls for efficiency
    # Strict limit: 10 results to control costs ($0.0015/result)
    run_input = {
        "queries": [material_name.strip()],
        "limit": 10,
        "includeDetails": False,  # Disable deep scrape for cost control
        "includeReviews": False,  # Disable review scraping for cost control
    }

    try:
        # Run Tokopedia scraper actor (pay-per-result: $1.50/1k = $0.0015/result)
        # Switched from 123webdata ($5/1k) for 70% cost reduction
        run = client.actor("fatihtahta/tokopedia-scraper").call(run_input=run_input)

        # Fetch results from dataset
        results = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            # Extract price - supports multiple Tokopedia actor formats
            price_idr = _extract_price(item)

            # Extract rating - supports both string and float formats
            rating = _extract_rating(item)

            # Extract sold count - supports multiple formats
            sold_count = _extract_sold_count(item)

            # Extract seller name - handle both dict and string formats
            # Some actors return {"shop": {"name": "..."}} others return {"shop": "..."} or {"seller": "..."}
            shop = item.get("shop")
            if isinstance(shop, dict):
                seller = shop.get("name", "")
            elif isinstance(shop, str):
                seller = shop
            else:
                seller = item.get("seller", "")

            results.append(
                {
                    "name": item.get("name", item.get("title", "")),
                    "price_idr": price_idr,
                    "url": item.get("url", item.get("link", "")),
                    "seller": seller,
                    "rating": rating,
                    "sold_count": sold_count,
                }
            )

            # Limit results (actor may return more)
            if len(results) >= max_results:
                break

        # =====================================================================
        # Update BOTH cache tiers with fresh results
        # =====================================================================

        # Tier 1: In-memory cache (60s TTL as documented)
        await price_scrape_cache.set(cache_key, results, ttl=60)

        # Tier 2: Supabase cache (persistent, 7-day freshness)
        try:
            # Generate search URL for cache reference
            tokopedia_search_url = _build_tokopedia_search_url(material_name)
            await save_material_price_cache(
                material_name=material_name,
                prices=results,
                tokopedia_search=tokopedia_search_url,
            )
        except Exception:
            # Supabase save failed, but we have results - continue
            pass

        return results

    except Exception as e:
        raise Exception(f"Tokopedia scraping failed for '{material_name}': {e}")


async def get_best_material_price(
    material_name: str,
    max_scrape_results: int = 20,
    top_n: int = 5,
) -> dict:
    """
    Get the best priced material using Best Seller scoring algorithm.

    This function implements a smart material retrieval flow:
    1. Check Supabase cache (7-day freshness)
    2. If stale/missing, trigger live Tokopedia scrape
    3. Apply weighted ranking algorithm
    4. Cache top 5 results and return #1 winner

    Weighted Ranking Formula:
        Score = (Rating * 0.4) + (Sales * 0.4) + (Price * 0.2)

    Args:
        material_name: Material to search for
        max_scrape_results: Max results to fetch from scraper (more = better ranking)
        top_n: Number of top products to cache (default 5)

    Returns:
        dict: Best seller product with scoring metadata
            {
                "name": "Product name",
                "price_idr": 85000,
                "url": "https://tokopedia.com/...",
                "seller": "Seller name",
                "seller_location": "Jakarta",
                "rating": 4.8,
                "sold_count": 500,
                "best_seller_score": 0.85,
                "_cached": False,
                "_ranking": 1,
                "_score_breakdown": {
                    "rating": 0.38,
                    "sales": 0.32,
                    "price": 0.15
                }
            }
    """
    from app.utils.cache import price_scrape_cache
    from app.integrations.supabase import get_cached_material_price

    # Build cache key for best seller results
    cache_key = f"best_seller:{material_name.lower()}"

    # =========================================================================
    # TIER 1: In-memory cache for best seller (60s TTL)
    # =========================================================================
    cached_best = await price_scrape_cache.get(cache_key)
    if cached_best is not None:
        print(
            f"  💾 CACHE HIT [Tier 1 Memory]: {material_name} → Rp {cached_best.get('price_idr', 0):,}"
        )
        return cached_best

    # =========================================================================
    # TIER 2: Check Supabase for fresh cached data
    # =========================================================================
    try:
        db_cache = await get_cached_material_price(material_name)
        if db_cache and db_cache.get("is_fresh") and db_cache.get("price_avg"):
            print(
                f"  💾 CACHE HIT [Tier 2 Database]: {material_name} → Rp {db_cache.get('price_avg', 0):,}"
            )
            # Return cached best seller data
            cached_result = {
                "name": db_cache.get("name_id", material_name),
                "price_idr": int(db_cache.get("price_avg", 0)),
                "url": "",
                "seller": "Cached Best Seller",
                "seller_location": db_cache.get("seller_location", ""),
                "rating": db_cache.get("rating_avg", 0) or 0,
                "sold_count": db_cache.get("count_sold_total", 0) or 0,
                "best_seller_score": 0.0,  # Not scored, from cache
                "_cached": True,
                "_ranking": 1,
                "_price_range": {
                    "min": db_cache.get("price_min"),
                    "max": db_cache.get("price_max"),
                    "median": db_cache.get("price_median"),
                },
            }
            await price_scrape_cache.set(cache_key, cached_result, ttl=60)
            return cached_result
    except Exception:
        pass

    # =========================================================================
    # TIER 3: Live scrape with Best Seller scoring
    # =========================================================================
    print(f"  🔍 CACHE MISS: {material_name} → Scraping Tokopedia via Apify...")
    # Scrape more results than needed for better ranking quality
    raw_results = await scrape_tokopedia_prices(
        material_name=material_name,
        max_results=max_scrape_results,
    )

    if not raw_results:
        return {
            "name": material_name,
            "price_idr": 0,
            "url": "",
            "seller": "",
            "seller_location": "",
            "rating": 0,
            "sold_count": 0,
            "best_seller_score": 0,
            "_cached": False,
            "_ranking": 0,
            "_error": "No results found",
        }

    # Add seller_location from mapped products for display
    for result in raw_results:
        if "seller_location" not in result:
            # Extract location from shop dict if available
            mapped = map_tokopedia_product(result)
            result["seller_location"] = mapped.seller_location

    # Apply weighted ranking (filters out-of-stock/inactive items)
    ranked = rank_best_sellers(raw_results, top_n=top_n)

    if not ranked:
        # Fallback to first result if scoring failed (all filtered out)
        return {
            **raw_results[0],
            "best_seller_score": 0,
            "_cached": False,
            "_ranking": 1,
        }

    # Build response with #1 winner
    winner = ranked[0]
    best_result = {
        **winner.product,
        "best_seller_score": round(winner.total_score, 4),
        "_cached": False,
        "_ranking": 1,
        "_score_breakdown": {
            "rating": round(winner.rating_score * 0.4, 4),
            "sales": round(winner.sales_score * 0.4, 4),
            "price": round(winner.price_score * 0.2, 4),
        },
        "_top_5": [
            {
                "name": s.product.get("name", ""),
                "price_idr": s.product.get("price_idr", 0),
                "score": round(s.total_score, 4),
            }
            for s in ranked
        ],
    }

    # Cache best seller result
    await price_scrape_cache.set(cache_key, best_result, ttl=60)

    return best_result


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


def get_best_price(products: list[dict], required_quantity: float = None) -> dict:
    """
    Get the best price from quality-filtered products.

    Uses quality scoring to filter unreliable sellers, then returns
    median price from remaining trusted products.

    This is the primary function for price lookups - use this instead
    of calculate_median_price for more robust results.

    Args:
        products: Raw product listings from scraper
        required_quantity: Minimum stock needed (from BOM). Products with
            insufficient stock are filtered out before quality scoring.

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

    # Pre-filter by stock availability (including quantity check)
    available_products = [
        p for p in products if _is_product_available(p, required_quantity)
    ]

    # If no products have sufficient stock, fall back to all products
    # (user will see "No link available" but we can still estimate price)
    products_to_score = available_products if available_products else products

    # Filter to quality products
    quality_products = filter_quality_products(
        products_to_score, min_score=0.3, top_n=5
    )

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
