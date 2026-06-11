"""
Marketplace abstraction layer for price comparison across Indonesian e-commerce platforms.

Provides a unified interface for querying product prices from Tokopedia, Shopee,
and other marketplaces. Designed for batch Bill of Quantities (BoQ) price lookups
with provider-swappable architecture.

Current providers:
- TokopediaProvider: Uses Apify's fatihtahta/tokopedia-scraper actor

Future providers:
- ShopeeProvider: Planned for Shopee marketplace integration
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from itertools import islice
from typing import Iterator

import structlog
from apify_client import ApifyClient

from app.integrations.apify import get_run_dataset_id, map_actor_item, rank_best_sellers

logger = structlog.get_logger()


# =============================================================================
# Batching Utility (Python 3.11 compatibility)
# =============================================================================


def _batched(iterable: Iterator, n: int) -> Iterator[tuple]:
    """
    Batch an iterable into tuples of length n (last batch may be shorter).

    Equivalent to itertools.batched (Python 3.12+), provided here for
    Python 3.11 compatibility.

    Args:
        iterable: Items to batch.
        n: Maximum batch size. Must be >= 1.

    Yields:
        Tuples of up to n items.
    """
    if n < 1:
        raise ValueError("n must be at least one")
    it = iter(iterable)
    while batch := tuple(islice(it, n)):
        yield batch


# =============================================================================
# Enums
# =============================================================================


class MarketplaceSource(str, Enum):
    """Marketplace origin for a price result."""

    TOKOPEDIA = "tokopedia"
    SHOPEE = "shopee"
    CACHED = "cached"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class MarketplaceResult:
    """
    Normalized product result from any marketplace provider.

    Fields are provider-agnostic so callers never depend on
    Tokopedia-specific or Shopee-specific shapes.
    """

    product_name: str
    price_idr: int
    url: str
    seller: str
    seller_location: str
    rating: float | None
    sold_count: int | None
    best_seller_score: float
    source: MarketplaceSource


@dataclass
class MaterialPriceMatch:
    """
    Result of matching a BoQ line item to a marketplace product.

    Captures both the raw marketplace result and derived comparison
    metrics (unit price, total, difference from BoQ estimate).
    """

    search_query: str
    result: MarketplaceResult | None
    match_confidence: float  # 0.0 - 1.0
    market_unit_price: Decimal | None
    market_total: Decimal | None
    price_difference: Decimal | None
    price_difference_pct: float | None
    from_cache: bool


# =============================================================================
# Abstract Provider
# =============================================================================


class MarketplaceProvider(ABC):
    """
    Abstract base class for marketplace price providers.

    Subclasses must implement search_sync and rank_results.
    batch_search_sync has a default sequential fallback but
    providers should override it for efficient batching.
    """

    @abstractmethod
    def search_sync(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search for products matching a single query.

        Args:
            query: Search term (e.g. "granit lantai 60x60").
            limit: Maximum results to return.

        Returns:
            Raw product dicts from the marketplace.
        """
        ...

    @abstractmethod
    def rank_results(self, results: list[dict]) -> list:
        """
        Rank/score a list of raw product dicts.

        Args:
            results: Raw product dicts from search_sync.

        Returns:
            Ranked results (type depends on provider).
        """
        ...

    def batch_search_sync(
        self, queries: list[str], limit_per_query: int = 10
    ) -> dict[str, list[dict]]:
        """
        Search for multiple queries. Default: sequential single searches.

        Providers should override this for more efficient batching
        (e.g. one actor call per batch of queries).

        Args:
            queries: List of search terms.
            limit_per_query: Max results per query.

        Returns:
            Dict mapping each query to its raw product list.
        """
        output: dict[str, list[dict]] = {}
        for query in queries:
            output[query] = self.search_sync(query, limit=limit_per_query)
        return output


# =============================================================================
# Tokopedia Provider
# =============================================================================


class TokopediaProvider(MarketplaceProvider):
    """
    Marketplace provider backed by Apify's fatihtahta/tokopedia-scraper actor.

    Supports efficient batch searching by grouping queries into chunks of 5
    and running one actor call per chunk.
    """

    ACTOR_ID = "fatihtahta/tokopedia-scraper"
    BATCH_SIZE = 5

    def __init__(self, apify_token: str) -> None:
        self._client = ApifyClient(apify_token)

    # --------------------------------------------------------------------- #
    # Public interface
    # --------------------------------------------------------------------- #

    def search_sync(self, query: str, limit: int = 10) -> list[dict]:
        """
        Run a single Tokopedia search via the Apify actor.

        Args:
            query: Search term.
            limit: Max results.

        Returns:
            Raw product dicts from the actor dataset.
        """
        run_input = {
            "queries": [query],
            "limit": limit,
            "includeDetails": False,
            "includeReviews": False,
        }

        run = self._client.actor(self.ACTOR_ID).call(run_input=run_input)
        dataset_id = get_run_dataset_id(run)
        if not dataset_id:
            logger.warning("marketplace_run_no_dataset", query=query)
            return []
        return [
            map_actor_item(item)
            for item in self._client.dataset(dataset_id).iterate_items()
        ]

    def rank_results(self, results: list[dict]) -> list:
        """
        Rank products using the existing Best Seller scoring algorithm.

        Delegates to ``app.integrations.apify.rank_best_sellers``.

        Args:
            results: Raw product dicts.

        Returns:
            List of BestSellerScore objects sorted by score descending.
        """
        return rank_best_sellers(results)

    def batch_search_sync(
        self, queries: list[str], limit_per_query: int = 10
    ) -> dict[str, list[dict]]:
        """
        Batch multiple queries into groups of 5, one actor run per group.

        After each run, flat results are routed back to the originating
        query using word-overlap matching on product titles.

        Args:
            queries: Search terms.
            limit_per_query: Max results per individual query.

        Returns:
            Dict mapping each query to its matched product list.
        """
        if not queries:
            return {}

        output: dict[str, list[dict]] = {q: [] for q in queries}

        for batch in _batched(queries, self.BATCH_SIZE):
            batch_list = list(batch)

            run_input = {
                "queries": batch_list,
                "limit": limit_per_query,
                "includeDetails": False,
                "includeReviews": False,
            }

            run = self._client.actor(self.ACTOR_ID).call(run_input=run_input)
            dataset_id = get_run_dataset_id(run)
            if not dataset_id:
                logger.warning("marketplace_run_no_dataset", queries=batch_list)
                continue
            items = [
                map_actor_item(item)
                for item in self._client.dataset(dataset_id).iterate_items()
            ]

            self._assign_results_to_queries(batch_list, items, output)

        return output

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _assign_results_to_queries(
        self,
        queries: list[str],
        items: list[dict],
        output: dict[str, list[dict]],
    ) -> None:
        """
        Route flat actor results back to the originating query.

        Items mapped from the current actor schema carry the exact
        search_query that produced them — use it when it matches one of
        ours. Otherwise fall back to word-overlap between the product
        title and each query (ties broken by position; first query wins).

        Args:
            queries: The queries that were sent in this batch.
            items: Flat product dicts (already passed through map_actor_item).
            output: Mutable dict to append matched items into.
        """
        # Pre-tokenise queries once
        query_tokens = {q: set(q.lower().split()) for q in queries}

        for item in items:
            actor_query = (item.get("search_query") or "").lower().strip()
            if actor_query in output:
                output[actor_query].append(item)
                continue

            title = (item.get("name") or item.get("title") or "").lower()
            title_words = set(title.split())

            best_query = queries[0]  # fallback
            best_overlap = 0

            for q in queries:
                overlap = len(query_tokens[q] & title_words)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_query = q

            output[best_query].append(item)


# =============================================================================
# Mock Provider (dev/testing)
# =============================================================================


class MockMarketplaceProvider(MarketplaceProvider):
    """
    Deterministic fake provider for cost-free pipeline testing.

    Selected by boq_processor when settings.debug and settings.use_mock_prices
    are both true. Prices are derived from the query text so repeated runs
    produce identical results.
    """

    def search_sync(self, query: str, limit: int = 10) -> list[dict]:
        """
        Return a single fake product for the query.

        Args:
            query: Search term.
            limit: Ignored (one deterministic result per query).

        Returns:
            One-element list with a product dict shaped like actor output.
        """
        return [self._mock_product(query)]

    def rank_results(self, results: list[dict]) -> list:
        """
        Rank fake products with the real Best Seller scorer.

        Args:
            results: Product dicts from search_sync.

        Returns:
            List of BestSellerScore objects.
        """
        return rank_best_sellers(results)

    def batch_search_sync(
        self, queries: list[str], limit_per_query: int = 10
    ) -> dict[str, list[dict]]:
        """
        Return one fake product per query without any network calls.

        Args:
            queries: Search terms.
            limit_per_query: Ignored.

        Returns:
            Dict mapping each query to its single fake product.
        """
        return {q: [self._mock_product(q)] for q in queries}

    @staticmethod
    def _mock_product(query: str) -> dict:
        """
        Build a stable fake product for a query.

        Price is 50,000-149,000 IDR derived from the query's character sum,
        so the same query always yields the same price.
        """
        price = 50_000 + (sum(ord(c) for c in query) % 100) * 1_000
        return {
            "name": f"Mock {query.title()}",
            "price_idr": price,
            "url": f"https://tokopedia.com/mock/{query.replace(' ', '-')}",
            "shop": "Mock Store",
            "location": "Denpasar",
            "rating": 4.5,
            "sold_count": 100,
            "stock": 1000,
            "status": "active",
        }
