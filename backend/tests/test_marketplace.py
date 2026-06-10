"""
Tests for Marketplace Abstraction Layer

Tests the marketplace provider pattern that abstracts over Tokopedia, Shopee, etc.
Uses mocks exclusively - no real Apify API calls.
"""

from __future__ import annotations

import pytest
from abc import ABC
from decimal import Decimal
from unittest.mock import MagicMock, patch


# =============================================================================
# MarketplaceSource Enum Tests
# =============================================================================


class TestMarketplaceSource:
    """Tests for MarketplaceSource enum values"""

    def test_has_tokopedia_value(self):
        """Should have a 'tokopedia' member"""
        from app.integrations.marketplace import MarketplaceSource

        assert MarketplaceSource.TOKOPEDIA.value == "tokopedia"

    def test_has_shopee_value(self):
        """Should have a 'shopee' member"""
        from app.integrations.marketplace import MarketplaceSource

        assert MarketplaceSource.SHOPEE.value == "shopee"

    def test_has_cached_value(self):
        """Should have a 'cached' member"""
        from app.integrations.marketplace import MarketplaceSource

        assert MarketplaceSource.CACHED.value == "cached"

    def test_is_string_enum(self):
        """Should be usable as a string"""
        from app.integrations.marketplace import MarketplaceSource

        assert str(MarketplaceSource.TOKOPEDIA) == "MarketplaceSource.TOKOPEDIA"
        assert MarketplaceSource.TOKOPEDIA == "tokopedia"


# =============================================================================
# MarketplaceResult Dataclass Tests
# =============================================================================


class TestMarketplaceResult:
    """Tests for MarketplaceResult dataclass"""

    def test_can_instantiate_with_all_fields(self):
        """Should create instance with all required fields"""
        from app.integrations.marketplace import MarketplaceResult, MarketplaceSource

        result = MarketplaceResult(
            product_name="Semen Tiga Roda 40kg",
            price_idr=85000,
            url="https://tokopedia.com/product/123",
            seller="Toko Bangunan Jaya",
            seller_location="Jakarta Selatan",
            rating=4.8,
            sold_count=500,
            best_seller_score=0.85,
            source=MarketplaceSource.TOKOPEDIA,
        )

        assert result.product_name == "Semen Tiga Roda 40kg"
        assert result.price_idr == 85000
        assert result.url == "https://tokopedia.com/product/123"
        assert result.seller == "Toko Bangunan Jaya"
        assert result.seller_location == "Jakarta Selatan"
        assert result.rating == 4.8
        assert result.sold_count == 500
        assert result.best_seller_score == 0.85
        assert result.source == MarketplaceSource.TOKOPEDIA

    def test_handles_none_optional_fields(self):
        """Should accept None for rating and sold_count"""
        from app.integrations.marketplace import MarketplaceResult, MarketplaceSource

        result = MarketplaceResult(
            product_name="Test Product",
            price_idr=50000,
            url="",
            seller="",
            seller_location="",
            rating=None,
            sold_count=None,
            best_seller_score=0.0,
            source=MarketplaceSource.CACHED,
        )

        assert result.rating is None
        assert result.sold_count is None


# =============================================================================
# MaterialPriceMatch Dataclass Tests
# =============================================================================


class TestMaterialPriceMatch:
    """Tests for MaterialPriceMatch dataclass"""

    def test_can_instantiate_with_result(self):
        """Should create instance with a marketplace result"""
        from app.integrations.marketplace import (
            MaterialPriceMatch,
            MarketplaceResult,
            MarketplaceSource,
        )

        result = MarketplaceResult(
            product_name="Granit Lantai 60x60",
            price_idr=150000,
            url="https://tokopedia.com/product/456",
            seller="Toko Keramik",
            seller_location="Surabaya",
            rating=4.5,
            sold_count=200,
            best_seller_score=0.72,
            source=MarketplaceSource.TOKOPEDIA,
        )

        match = MaterialPriceMatch(
            search_query="granit lantai 60x60",
            result=result,
            match_confidence=0.9,
            market_unit_price=Decimal("150000"),
            market_total=Decimal("1500000"),
            price_difference=Decimal("-50000"),
            price_difference_pct=-3.33,
            from_cache=False,
        )

        assert match.search_query == "granit lantai 60x60"
        assert match.result is not None
        assert match.result.price_idr == 150000
        assert match.match_confidence == 0.9
        assert match.market_unit_price == Decimal("150000")
        assert match.from_cache is False

    def test_handles_none_result(self):
        """Should accept None result for failed lookups"""
        from app.integrations.marketplace import MaterialPriceMatch

        match = MaterialPriceMatch(
            search_query="unknown material",
            result=None,
            match_confidence=0.0,
            market_unit_price=None,
            market_total=None,
            price_difference=None,
            price_difference_pct=None,
            from_cache=False,
        )

        assert match.result is None
        assert match.market_unit_price is None
        assert match.price_difference is None
        assert match.price_difference_pct is None


# =============================================================================
# MarketplaceProvider ABC Tests
# =============================================================================


class TestMarketplaceProviderABC:
    """Tests for MarketplaceProvider abstract base class"""

    def test_cannot_instantiate_directly(self):
        """Should raise TypeError when trying to instantiate ABC directly"""
        from app.integrations.marketplace import MarketplaceProvider

        with pytest.raises(TypeError):
            MarketplaceProvider()

    def test_subclass_must_implement_search_sync(self):
        """Should require search_sync implementation"""
        from app.integrations.marketplace import MarketplaceProvider

        class IncompleteProvider(MarketplaceProvider):
            def rank_results(self, results):
                return results

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_subclass_must_implement_rank_results(self):
        """Should require rank_results implementation"""
        from app.integrations.marketplace import MarketplaceProvider

        class IncompleteProvider(MarketplaceProvider):
            def search_sync(self, query, limit=10):
                return []

        with pytest.raises(TypeError):
            IncompleteProvider()


# =============================================================================
# TokopediaProvider Tests
# =============================================================================


class TestTokopediaProviderAssignResults:
    """Tests for TokopediaProvider._assign_results_to_queries"""

    def test_assigns_products_to_correct_queries(self):
        """Should route products to queries based on word overlap in titles"""
        from app.integrations.marketplace import TokopediaProvider

        provider = TokopediaProvider(apify_token="test_token")

        queries = ["granit lantai", "pipa pvc"]
        items = [
            {"name": "Granit Lantai 60x60 Hitam Premium"},
            {"name": "Granit Lantai 40x40 Cream"},
            {"name": "Pipa PVC Rucika 4 inch"},
            {"name": "Pipa PVC Wavin 3 inch"},
        ]
        output: dict[str, list[dict]] = {q: [] for q in queries}

        provider._assign_results_to_queries(queries, items, output)

        assert len(output["granit lantai"]) == 2
        assert len(output["pipa pvc"]) == 2
        # Verify correct assignment
        assert output["granit lantai"][0]["name"] == "Granit Lantai 60x60 Hitam Premium"
        assert output["granit lantai"][1]["name"] == "Granit Lantai 40x40 Cream"
        assert output["pipa pvc"][0]["name"] == "Pipa PVC Rucika 4 inch"
        assert output["pipa pvc"][1]["name"] == "Pipa PVC Wavin 3 inch"

    def test_handles_title_field_fallback(self):
        """Should fall back to 'title' field when 'name' is missing"""
        from app.integrations.marketplace import TokopediaProvider

        provider = TokopediaProvider(apify_token="test_token")

        queries = ["semen tiga roda"]
        items = [
            {"title": "Semen Tiga Roda 40kg Portland"},
        ]
        output: dict[str, list[dict]] = {q: [] for q in queries}

        provider._assign_results_to_queries(queries, items, output)

        assert len(output["semen tiga roda"]) == 1

    def test_handles_empty_results(self):
        """Should leave output dict values empty when no items"""
        from app.integrations.marketplace import TokopediaProvider

        provider = TokopediaProvider(apify_token="test_token")

        queries = ["granit lantai", "pipa pvc"]
        items = []
        output: dict[str, list[dict]] = {q: [] for q in queries}

        provider._assign_results_to_queries(queries, items, output)

        assert output["granit lantai"] == []
        assert output["pipa pvc"] == []

    def test_handles_no_matching_title(self):
        """Should assign to first query when no word overlap found"""
        from app.integrations.marketplace import TokopediaProvider

        provider = TokopediaProvider(apify_token="test_token")

        queries = ["granit lantai", "pipa pvc"]
        items = [
            {"name": ""},  # Empty name - no overlap with any query
        ]
        output: dict[str, list[dict]] = {q: [] for q in queries}

        provider._assign_results_to_queries(queries, items, output)

        # Should be assigned to first query (fallback when all overlap is 0)
        total_assigned = sum(len(v) for v in output.values())
        assert total_assigned == 1

    def test_case_insensitive_matching(self):
        """Should match words case-insensitively"""
        from app.integrations.marketplace import TokopediaProvider

        provider = TokopediaProvider(apify_token="test_token")

        queries = ["granit lantai"]
        items = [
            {"name": "GRANIT LANTAI Premium 60x60"},
        ]
        output: dict[str, list[dict]] = {q: [] for q in queries}

        provider._assign_results_to_queries(queries, items, output)

        assert len(output["granit lantai"]) == 1


class TestTokopediaProviderSearchSync:
    """Tests for TokopediaProvider.search_sync"""

    def test_search_sync_calls_actor(self):
        """Should call the fatihtahta/tokopedia-scraper actor"""
        from app.integrations.marketplace import TokopediaProvider

        # Set up mock ApifyClient
        mock_dataset = MagicMock()
        mock_dataset.iterate_items.return_value = [
            {"name": "Semen Tiga Roda 40kg", "price": 85000, "rating": 4.8},
        ]

        mock_actor = MagicMock()
        mock_actor.call.return_value = {"defaultDatasetId": "ds-123"}

        mock_client = MagicMock()
        mock_client.actor.return_value = mock_actor
        mock_client.dataset.return_value = mock_dataset

        with patch(
            "app.integrations.marketplace.ApifyClient", return_value=mock_client
        ):
            provider = TokopediaProvider(apify_token="test_token")
            results = provider.search_sync("semen tiga roda", limit=10)

        mock_client.actor.assert_called_with("fatihtahta/tokopedia-scraper")
        mock_actor.call.assert_called_once()
        call_args = mock_actor.call.call_args
        run_input = call_args[1]["run_input"]
        assert run_input["queries"] == ["semen tiga roda"]
        assert run_input["limit"] == 10
        assert run_input["includeDetails"] is False
        assert run_input["includeReviews"] is False
        assert len(results) == 1

    def test_search_sync_returns_raw_items(self):
        """Should return raw items from the dataset"""
        from app.integrations.marketplace import TokopediaProvider

        mock_dataset = MagicMock()
        mock_dataset.iterate_items.return_value = [
            {"name": "Product A", "price": 80000},
            {"name": "Product B", "price": 90000},
        ]

        mock_actor = MagicMock()
        mock_actor.call.return_value = {"defaultDatasetId": "ds-123"}

        mock_client = MagicMock()
        mock_client.actor.return_value = mock_actor
        mock_client.dataset.return_value = mock_dataset

        with patch(
            "app.integrations.marketplace.ApifyClient", return_value=mock_client
        ):
            provider = TokopediaProvider(apify_token="test_token")
            results = provider.search_sync("test", limit=10)

        assert len(results) == 2
        assert results[0]["name"] == "Product A"
        assert results[1]["name"] == "Product B"


class TestTokopediaProviderBatchSearchSync:
    """Tests for TokopediaProvider.batch_search_sync"""

    def test_batch_search_groups_queries(self):
        """Should batch queries into groups of 5 with one actor call per batch"""
        from app.integrations.marketplace import TokopediaProvider

        # 7 queries should produce 2 batches: [5] + [2]
        queries = [
            "granit lantai",
            "pipa pvc",
            "semen tiga roda",
            "cat tembok",
            "keramik dinding",
            "besi beton",
            "kabel listrik",
        ]

        mock_dataset = MagicMock()
        # Return items that match various queries
        mock_dataset.iterate_items.return_value = [
            {"name": "Granit Lantai 60x60"},
            {"name": "Pipa PVC 4 inch"},
            {"name": "Semen Tiga Roda 40kg"},
            {"name": "Cat Tembok Dulux"},
            {"name": "Keramik Dinding 25x40"},
            {"name": "Besi Beton 12mm"},
            {"name": "Kabel Listrik NYM"},
        ]

        mock_actor = MagicMock()
        mock_actor.call.return_value = {"defaultDatasetId": "ds-123"}

        mock_client = MagicMock()
        mock_client.actor.return_value = mock_actor
        mock_client.dataset.return_value = mock_dataset

        with patch(
            "app.integrations.marketplace.ApifyClient", return_value=mock_client
        ):
            provider = TokopediaProvider(apify_token="test_token")
            results = provider.batch_search_sync(queries, limit_per_query=10)

        # Should have called actor twice (batch of 5 + batch of 2)
        assert mock_actor.call.call_count == 2

        # Should have results for all 7 queries
        assert len(results) == 7
        for query in queries:
            assert query in results

    def test_batch_search_returns_dict_keyed_by_query(self):
        """Should return results keyed by query string"""
        from app.integrations.marketplace import TokopediaProvider

        queries = ["granit lantai", "pipa pvc"]

        mock_dataset = MagicMock()
        mock_dataset.iterate_items.return_value = [
            {"name": "Granit Lantai 60x60"},
            {"name": "Pipa PVC Rucika"},
        ]

        mock_actor = MagicMock()
        mock_actor.call.return_value = {"defaultDatasetId": "ds-123"}

        mock_client = MagicMock()
        mock_client.actor.return_value = mock_actor
        mock_client.dataset.return_value = mock_dataset

        with patch(
            "app.integrations.marketplace.ApifyClient", return_value=mock_client
        ):
            provider = TokopediaProvider(apify_token="test_token")
            results = provider.batch_search_sync(queries, limit_per_query=10)

        assert isinstance(results, dict)
        assert "granit lantai" in results
        assert "pipa pvc" in results
        assert isinstance(results["granit lantai"], list)
        assert isinstance(results["pipa pvc"], list)

    def test_batch_search_empty_queries(self):
        """Should handle empty query list"""
        from app.integrations.marketplace import TokopediaProvider

        mock_client = MagicMock()

        with patch(
            "app.integrations.marketplace.ApifyClient", return_value=mock_client
        ):
            provider = TokopediaProvider(apify_token="test_token")
            results = provider.batch_search_sync([], limit_per_query=10)

        assert results == {}


class TestTokopediaProviderRankResults:
    """Tests for TokopediaProvider.rank_results"""

    def test_delegates_to_rank_best_sellers(self):
        """Should delegate ranking to apify.rank_best_sellers"""
        from app.integrations.marketplace import TokopediaProvider

        mock_client = MagicMock()

        with patch(
            "app.integrations.marketplace.ApifyClient", return_value=mock_client
        ):
            provider = TokopediaProvider(apify_token="test_token")

        products = [
            {"price_idr": 80000, "rating": 4.5, "sold_count": 500},
            {"price_idr": 100000, "rating": 4.0, "sold_count": 100},
        ]

        with patch(
            "app.integrations.marketplace.rank_best_sellers"
        ) as mock_rank:
            mock_rank.return_value = ["ranked_result_1", "ranked_result_2"]
            ranked = provider.rank_results(products)

        mock_rank.assert_called_once_with(products)
        assert ranked == ["ranked_result_1", "ranked_result_2"]


class TestMockMarketplaceProvider:
    """Tests for MockMarketplaceProvider (use_mock_prices dev path)"""

    def test_returns_deterministic_results(self):
        """Same query should always produce the same product and price"""
        from app.integrations.marketplace import MockMarketplaceProvider

        provider = MockMarketplaceProvider()

        first = provider.search_sync("granit 60x60")
        second = provider.search_sync("granit 60x60")

        assert first == second
        assert first[0]["price_idr"] == second[0]["price_idr"]

    def test_different_queries_can_differ(self):
        """Price is derived from the query text"""
        from app.integrations.marketplace import MockMarketplaceProvider

        provider = MockMarketplaceProvider()

        a = provider.search_sync("semen portland 50kg")[0]["price_idr"]
        b = provider.search_sync("pipa pvc 4 inch")[0]["price_idr"]

        assert a != b

    def test_product_shape_works_with_ranker(self):
        """Mock products must survive rank_best_sellers filtering and scoring"""
        from app.integrations.marketplace import MockMarketplaceProvider

        provider = MockMarketplaceProvider()
        products = provider.search_sync("granit 60x60")

        ranked = provider.rank_results(products)

        assert len(ranked) == 1
        assert ranked[0].product["price_idr"] == products[0]["price_idr"]
        assert ranked[0].total_score > 0

    def test_batch_search_returns_all_queries(self):
        """Every query gets exactly one product, no network calls"""
        from app.integrations.marketplace import MockMarketplaceProvider

        provider = MockMarketplaceProvider()
        queries = ["granit 60x60", "semen portland", "pipa pvc"]

        results = provider.batch_search_sync(queries)

        assert set(results.keys()) == set(queries)
        assert all(len(v) == 1 for v in results.values())
