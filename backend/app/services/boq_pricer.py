"""
Batch BOQ material pricing pipeline.

Takes extracted BOQ items (materials), searches marketplace providers for
real-time pricing, ranks results, and persists price comparisons back to
the database.

Design decisions:
- Fully synchronous: designed to run inside ProcessPoolExecutor (same as
  boq_processor.py) to avoid event-loop conflicts.
- Two-tier pricing: Supabase `materials` cache (7-day TTL) → live Apify scrape.
- Decimal arithmetic for all money calculations to avoid float rounding.
- normalize_material_name is duplicated from boq_processor.py to avoid
  circular imports and give this module ownership of the function.
"""

from __future__ import annotations

import hashlib
import re
import structlog
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Callable, Optional

from app.integrations.marketplace import (
    MarketplaceProvider,
    MarketplaceResult,
    MarketplaceSource,
    MaterialPriceMatch,
)

logger = structlog.get_logger()

CACHE_TTL_DAYS = 7


# =============================================================================
# Material Name Normalization
# =============================================================================


def normalize_material_name(description: str) -> str:
    """
    Normalize a material description for marketplace search.

    Strips Indonesian construction prefixes (Pas., Pek., Instalasi),
    owner-supply notes, room/floor location specifiers, and collapses
    whitespace.

    Args:
        description: Raw material description from BOQ.

    Returns:
        Cleaned, lowercased search query string.
    """
    prefixes_to_remove = [
        r"^pas\.\s*",
        r"^pas\s+",
        r"^instalasi\s+",
        r"^pek\.\s*",
        r"^pek\s+",
    ]

    result = description.lower()
    for prefix in prefixes_to_remove:
        result = re.sub(prefix, "", result, flags=re.IGNORECASE)

    # Remove owner supply / existing notes (with or without parentheses)
    result = re.sub(r"\([^)]*suply\s*by\s*owner[^)]*\)", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\([^)]*supply\s*by\s*owner[^)]*\)", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\(?use\s*existing\)?", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\([^)]*existing[^)]*\)", "", result, flags=re.IGNORECASE)

    # Remove location/room specifiers
    result = re.sub(r"master\s*bed\s*room", "", result, flags=re.IGNORECASE)
    result = re.sub(r"master\s*bathroom", "", result, flags=re.IGNORECASE)
    result = re.sub(r"living\s*dining\s*kitchen", "", result, flags=re.IGNORECASE)
    result = re.sub(r"lantai\s*\d+", "", result, flags=re.IGNORECASE)
    result = re.sub(r"area\s+\w+", "", result, flags=re.IGNORECASE)

    # Clean up
    result = re.sub(r"\s+", " ", result).strip()

    return result


def canonicalize_for_cache(normalized_name: str) -> str:
    """
    Canonicalize a normalized material name for cache key lookup.

    The materials table uses `normalized_name` with sorted words so that
    "granit dinding 60x60" and "dinding granit 60x60" map to the same entry.

    Args:
        normalized_name: Output from normalize_material_name().

    Returns:
        Lowercased, alphabetically sorted words joined by space.
    """
    words = normalized_name.lower().split()
    return " ".join(sorted(words))


# =============================================================================
# Cache Layer (Supabase `materials` table)
# =============================================================================


def _lookup_cache(
    supabase_client,
    cache_keys: list[str],
) -> dict[str, dict]:
    """
    Batch-query the materials table for cached price entries.

    Uses a single `.in_()` query for efficiency. Only returns entries
    where `price_updated_at` is within the TTL window and `price_median`
    is set.

    Args:
        supabase_client: Supabase client instance.
        cache_keys: List of canonicalized material names.

    Returns:
        Dict mapping cache_key → materials row dict (only fresh hits).
    """
    if not cache_keys:
        return {}

    try:
        result = (
            supabase_client.table("materials")
            .select("*")
            .in_("normalized_name", cache_keys)
            .execute()
        )
    except Exception:
        logger.warning("boq_cache_lookup_failed", exc_info=True)
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)
    hits: dict[str, dict] = {}

    for row in (result.data or []):
        updated_at = row.get("price_updated_at")
        if not updated_at or not row.get("price_median"):
            continue

        # Parse ISO timestamp
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

        if updated_at >= cutoff:
            key = row.get("normalized_name", "")
            hits[key] = row

    logger.info("boq_cache_lookup", keys_queried=len(cache_keys), hits=len(hits))
    return hits


def _no_result_match(query: str, from_cache: bool) -> MaterialPriceMatch:
    """A match with no marketplace result (nothing found, or gated out)."""
    return MaterialPriceMatch(
        search_query=query,
        result=None,
        match_confidence=0.0,
        market_unit_price=None,
        market_total=None,
        price_difference=None,
        price_difference_pct=None,
        from_cache=from_cache,
    )


def _build_match_from_cache(
    item: dict,
    query: str,
    cache_row: dict,
    max_price_ratio: float = 5.0,
) -> MaterialPriceMatch:
    """
    Build a MaterialPriceMatch from a cached materials table row.

    Uses price_median as the market unit price for comparison.

    Applies a price-sanity band gate: cached confidence is fixed at 0.85
    (pre-verified by prior scrape), so only the band check applies. If the
    cached market price lies outside [contractor/max_price_ratio,
    contractor*max_price_ratio], the match is rejected and returned as a
    no-result match (search_query kept, pricing fields None, from_cache=True).

    Args:
        item: BOQ item dict (must have 'contractor_unit_price', 'quantity').
        query: Normalized search query.
        cache_row: Row from the materials table.
        max_price_ratio: Maximum ratio between market and contractor prices.

    Returns:
        MaterialPriceMatch with from_cache=True.
    """
    market_price = Decimal(str(cache_row.get("price_median", 0) or 0))
    contractor_price = Decimal(str(item.get("contractor_unit_price", 0) or 0))
    quantity = Decimal(str(item.get("quantity", 0) or 0))

    # Price-sanity band gate for cache matches
    if contractor_price > 0 and market_price > 0:
        ratio = float(market_price / contractor_price)
        if ratio > max_price_ratio or ratio < 1.0 / max_price_ratio:
            logger.info(
                "boq_match_rejected",
                query=query,
                reason="price_out_of_band",
                confidence=0.85,
                market_price=int(market_price),
                contractor_price=int(contractor_price),
                source="cache",
            )
            return _no_result_match(query, from_cache=True)

    market_total = market_price * quantity

    if contractor_price > 0:
        diff = contractor_price - market_price
        diff_pct = float(diff / contractor_price * 100)
    else:
        diff = Decimal("0")
        diff_pct = 0.0

    product_name = cache_row.get("name_id") or cache_row.get("name_en") or query

    return MaterialPriceMatch(
        search_query=query,
        result=MarketplaceResult(
            product_name=product_name,
            price_idr=int(market_price),
            url=cache_row.get("tokopedia_affiliate_url") or "",
            seller="",
            seller_location=cache_row.get("seller_location") or "",
            rating=cache_row.get("rating_avg"),
            sold_count=cache_row.get("count_sold_total"),
            best_seller_score=0.0,
            source=MarketplaceSource.CACHED,
        ),
        match_confidence=0.85,  # cache match is pre-verified
        market_unit_price=market_price,
        market_total=market_total,
        price_difference=diff,
        price_difference_pct=round(diff_pct, 2),
        from_cache=True,
    )


def _cache_material_code(cache_key: str) -> str:
    """
    Generate a deterministic material_code (<= 20 chars) for scraped cache rows.

    Args:
        cache_key: Canonicalized cache key (normalized_name).

    Returns:
        Code like 'BOQ' + 16 hex chars, stable for the same cache key.
    """
    digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:16].upper()
    return f"BOQ{digest}"


def _write_cache(
    supabase_client,
    query: str,
    cache_key: str,
    best_product: dict,
    all_candidates: list[dict],
    unit: str | None = None,
) -> None:
    """
    Write scraped pricing data into the materials table for future cache hits.

    Write strategy (materials has NOT NULL columns a blind upsert can't satisfy,
    and a unique index on LOWER(name_id) that an upsert can't arbitrate):
      1. Update the existing cache row matched by normalized_name.
      2. Adopt a seeded row whose name_id matches the query (sets its
         normalized_name so future lookups hit it directly).
      3. Insert a new row with a generated material_code and required fields.

    Args:
        supabase_client: Supabase client instance.
        query: The normalized search query.
        cache_key: Canonicalized cache key (normalized_name).
        best_product: Best-ranked product dict from the scrape.
        all_candidates: All candidate product dicts for price statistics.
        unit: BOQ item unit, used only when inserting a new row.
    """
    if not best_product or not all_candidates:
        return

    prices = [c.get("price_idr", 0) for c in all_candidates if c.get("price_idr")]
    if not prices:
        return

    prices_sorted = sorted(prices)
    n = len(prices_sorted)
    price_median = prices_sorted[n // 2] if n % 2 == 1 else (prices_sorted[n // 2 - 1] + prices_sorted[n // 2]) / 2

    ratings = [c.get("rating") for c in all_candidates if c.get("rating") is not None]
    sold_counts = [c.get("sold_count", 0) or c.get("sold", 0) or 0 for c in all_candidates]

    price_fields = {
        "tokopedia_search": query,
        "price_min": min(prices),
        "price_max": max(prices),
        "price_avg": sum(prices) / n,
        "price_median": price_median,
        "price_sample_size": n,
        "price_updated_at": datetime.now(timezone.utc).isoformat(),
        "seller_location": best_product.get("location") or best_product.get("seller_location") or "",
        "rating_avg": sum(ratings) / len(ratings) if ratings else None,
        "rating_sample_size": len(ratings),
        "count_sold_total": sum(sold_counts),
        "tokopedia_affiliate_url": best_product.get("url") or best_product.get("link") or "",
    }

    try:
        # 1. Existing cache row for this normalized name
        result = (
            supabase_client.table("materials")
            .update(price_fields)
            .eq("normalized_name", cache_key)
            .execute()
        )
        if result.data:
            return

        # 2. Seeded row matching the query by name — adopt it into the cache
        result = (
            supabase_client.table("materials")
            .update({**price_fields, "normalized_name": cache_key})
            .ilike("name_id", query)
            .is_("normalized_name", "null")
            .execute()
        )
        if result.data:
            return

        # 3. New cache row (materials requires code/name/category/unit)
        supabase_client.table("materials").insert({
            **price_fields,
            "normalized_name": cache_key,
            "material_code": _cache_material_code(cache_key),
            "name_id": query[:200],
            "name_en": query[:200],
            "category": "boq_scraped",
            "unit": (unit or "unit")[:50],
        }).execute()
    except Exception:
        # Cache write failure is non-critical — log and continue
        logger.warning("boq_cache_write_failed", cache_key=cache_key, exc_info=True)


# =============================================================================
# Batch Pricing Pipeline
# =============================================================================


def batch_price_materials(
    items: list[dict],
    provider: MarketplaceProvider,
    supabase_client,
    max_lookups: int = 20,
    progress_callback: Optional[Callable[[int], None]] = None,
    min_confidence: float = 0.3,
    max_price_ratio: float = 5.0,
) -> list[tuple[dict, MaterialPriceMatch]]:
    """
    Main pipeline entry point. Runs fully synchronously.

    Steps:
      1. Normalize material names into search queries.
      2. Skip items whose normalized query is < 3 characters.
      3. Prioritize owner_supply items first, then others.
      4. Cap at max_lookups.
      5. Check Supabase materials cache for fresh prices.
      6. Scrape marketplace only for cache misses.
      7. Write scrape results back to cache.
      8. For each result: rank candidates, pick best, calculate delta.
      9. Apply quality gate: reject matches below min_confidence or outside
         the price-sanity band [contractor/max_price_ratio, contractor*max_price_ratio].

    Args:
        items: BOQ item rows (dicts with at minimum 'description').
        provider: Marketplace provider instance.
        supabase_client: Supabase client for cache lookups/writes.
        max_lookups: Maximum number of items to price in one run.
        progress_callback: Optional callback receiving progress percentage (40-85 range).
        min_confidence: Minimum word-overlap confidence to accept a scrape match.
        max_price_ratio: Maximum ratio between market and contractor unit prices.

    Returns:
        List of (item, MaterialPriceMatch) pairs, one per processed item,
        so callers never have to reconstruct which match belongs to which item.
    """
    # --- Prepare priceable items ---
    priceable: list[dict] = []
    for item in items:
        query = normalize_material_name(item.get("description", ""))
        if len(query) < 3:
            continue
        cache_key = canonicalize_for_cache(query)
        priceable.append({**item, "_search_query": query, "_cache_key": cache_key})

    # --- Prioritize owner_supply items ---
    priceable.sort(key=lambda x: (not x.get("is_owner_supply", False)))

    # --- Cap at max_lookups ---
    priceable = priceable[:max_lookups]

    total = len(priceable)
    if total == 0:
        return []

    # --- Check cache ---
    cache_keys = [item["_cache_key"] for item in priceable]
    cache_hits = _lookup_cache(supabase_client, cache_keys)

    # Split into cached and uncached
    cached_items: list[tuple[int, dict]] = []  # (index, item)
    uncached_items: list[tuple[int, dict]] = []  # (index, item)

    for i, item in enumerate(priceable):
        if item["_cache_key"] in cache_hits:
            cached_items.append((i, item))
        else:
            uncached_items.append((i, item))

    logger.info(
        "boq_pricing_batch_start",
        total_items=total,
        cache_hits=len(cached_items),
        cache_misses=len(uncached_items),
    )

    # --- Build matches array (will be filled in order) ---
    matches: list[MaterialPriceMatch | None] = [None] * total

    # --- Process cache hits (instant, 40% → 55%) ---
    for idx, (i, item) in enumerate(cached_items):
        cache_row = cache_hits[item["_cache_key"]]
        matches[i] = _build_match_from_cache(item, item["_search_query"], cache_row, max_price_ratio=max_price_ratio)

        if progress_callback and total > 0:
            # Cache hits use the 40-55% range
            pct = 40 + int(15 * (idx + 1) / max(len(cached_items), 1))
            progress_callback(pct)

    # --- Scrape marketplace for cache misses (55% → 85%) ---
    if uncached_items:
        uncached_queries = [item["_search_query"] for _, item in uncached_items]
        raw_results = provider.batch_search_sync(uncached_queries, limit_per_query=10)

        for idx, (i, item) in enumerate(uncached_items):
            query = item["_search_query"]
            candidates = raw_results.get(query, [])

            if candidates:
                ranked = provider.rank_results(candidates)
                best = ranked[0] if ranked else None
            else:
                best = None

            matches[i] = _build_match_from_scrape(item, query, best, min_confidence=min_confidence, max_price_ratio=max_price_ratio)

            # Write to cache for next time
            if best is not None:
                _write_cache(
                    supabase_client,
                    query,
                    item["_cache_key"],
                    best.product,
                    candidates,
                    unit=item.get("unit"),
                )

            if progress_callback and total > 0:
                # Scrapes use the 55-85% range
                pct = 55 + int(30 * (idx + 1) / max(len(uncached_items), 1))
                progress_callback(pct)
    else:
        # All from cache — jump to 85%
        if progress_callback:
            progress_callback(85)

    # Pair each item with its match; drop None entries (shouldn't happen, but safety)
    pairs = [
        (item, match)
        for item, match in zip(priceable, matches)
        if match is not None
    ]

    logger.info(
        "boq_pricing_batch_complete",
        priced=sum(1 for _, m in pairs if m.result),
        from_cache=sum(1 for _, m in pairs if m.from_cache),
        total=total,
    )
    return pairs


# =============================================================================
# Match Building
# =============================================================================


def _build_match_from_scrape(
    item: dict,
    query: str,
    best,
    min_confidence: float = 0.3,
    max_price_ratio: float = 5.0,
) -> MaterialPriceMatch:
    """
    Build a MaterialPriceMatch from a BOQ item and a ranking result.

    Applies a two-part quality gate before building the match:
      1. Confidence gate: word-overlap between query and product name must be
         >= min_confidence (default 0.3). A pool fitting matching vacuum storage
         bags scores 0.0 and is rejected.
      2. Price-sanity band: when a contractor price is available, the market
         price must lie within [contractor/max_price_ratio, contractor*max_price_ratio].
         Matches outside this band (e.g. -12,100% price differences) are rejected.

    Rejected matches are returned as no-result matches (search_query kept,
    all pricing fields None, match_confidence=0.0) so they are recorded but
    do not contribute to market totals or summary statistics.

    Args:
        item: BOQ item dict (must have 'contractor_unit_price', 'quantity').
        query: Normalized search query used.
        best: A BestSellerScore object (with .product dict and .total_score),
              or None if no results found.
        min_confidence: Minimum word-overlap confidence required to accept match.
        max_price_ratio: Maximum ratio between market and contractor prices.

    Returns:
        MaterialPriceMatch with computed pricing deltas and confidence,
        or a no-result match if the quality gate rejects the candidate.
    """
    if best is None:
        return _no_result_match(query, from_cache=False)

    # Extract from BestSellerScore
    product = best.product
    market_price = Decimal(str(product.get("price_idr", 0)))
    contractor_price = Decimal(str(item.get("contractor_unit_price", 0) or 0))
    quantity = Decimal(str(item.get("quantity", 0) or 0))

    # Match confidence via word overlap (computed before gate check)
    search_words = set(query.lower().split())
    product_name = product.get("name") or product.get("title") or ""
    product_words = set(product_name.lower().split())
    overlap = len(search_words & product_words)
    confidence = overlap / max(len(search_words), 1)

    # Quality gate
    rejection = None
    if confidence < min_confidence:
        rejection = "low_confidence"
    elif contractor_price > 0 and market_price > 0:
        ratio = float(market_price / contractor_price)
        if ratio > max_price_ratio or ratio < 1.0 / max_price_ratio:
            rejection = "price_out_of_band"

    if rejection is not None:
        logger.info(
            "boq_match_rejected",
            query=query,
            reason=rejection,
            confidence=round(confidence, 2),
            market_price=int(market_price),
            contractor_price=int(contractor_price),
        )
        return _no_result_match(query, from_cache=False)

    market_total = market_price * quantity

    if contractor_price > 0:
        diff = contractor_price - market_price
        diff_pct = float(diff / contractor_price * 100)
    else:
        diff = Decimal("0")
        diff_pct = 0.0

    return MaterialPriceMatch(
        search_query=query,
        result=MarketplaceResult(
            product_name=product_name,
            price_idr=product.get("price_idr", 0),
            url=product.get("url") or product.get("link") or "",
            seller=product.get("shop") or product.get("seller") or "",
            seller_location=product.get("location") or product.get("seller_location") or "",
            rating=product.get("rating"),
            sold_count=product.get("sold_count") or product.get("sold"),
            best_seller_score=best.total_score,
            source=MarketplaceSource.TOKOPEDIA,
        ),
        match_confidence=min(confidence, 1.0),
        market_unit_price=market_price,
        market_total=market_total,
        price_difference=diff,
        price_difference_pct=round(diff_pct, 2),
        from_cache=False,
    )


# =============================================================================
# Persistence
# =============================================================================


def persist_price_results(
    supabase_client,
    job_id: str,
    pairs: list[tuple[dict, MaterialPriceMatch]],
) -> None:
    """
    Write pricing results back to boq_items table rows.

    Each match is written to its paired item's row by the item's 'id'.

    Args:
        supabase_client: Supabase client instance.
        job_id: BOQ processing job ID (for logging context).
        pairs: (item, match) pairs from batch_price_materials. Items must
            contain an 'id' field.
    """
    for item, match in pairs:
        item_id = item.get("id")
        if not item_id:
            continue

        update_data: dict = {
            "search_query": match.search_query,
        }

        if match.result:
            update_data.update({
                "tokopedia_product_name": match.result.product_name,
                "tokopedia_price": float(match.result.price_idr),
                "tokopedia_url": match.result.url,
                "tokopedia_seller": match.result.seller,
                "tokopedia_seller_location": match.result.seller_location,
                "tokopedia_rating": match.result.rating,
                "tokopedia_sold_count": match.result.sold_count,
                "match_confidence": match.match_confidence,
                "market_unit_price": float(match.market_unit_price) if match.market_unit_price is not None else None,
                "market_total": float(match.market_total) if match.market_total is not None else None,
                "price_difference": float(match.price_difference) if match.price_difference is not None else None,
                "price_difference_percent": match.price_difference_pct,
            })

        supabase_client.table("boq_items").update(update_data).eq("id", item_id).execute()

    logger.info("boq_pricing_persisted", job_id=job_id, items_updated=len(pairs))
