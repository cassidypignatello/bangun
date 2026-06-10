"""
Tests for BOQ Batch Pricing Pipeline

Tests the normalize_material_name, _build_match_from_scrape,
batch_price_materials, and persist_price_results functions.
Uses mocks exclusively - no real API calls or Supabase writes.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest

from app.integrations.apify import BestSellerScore
from app.integrations.marketplace import (
    MarketplaceSource,
    MaterialPriceMatch,
)
from app.services.boq_pricer import (
    normalize_material_name,
    batch_price_materials,
    persist_price_results,
    _build_match_from_scrape,
)


# =============================================================================
# normalize_material_name Tests
# =============================================================================


class TestNormalizeMaterialName:
    """Tests for normalize_material_name."""

    def test_strips_pas_dot_prefix(self):
        """Should remove 'pas.' prefix from descriptions."""
        result = normalize_material_name("Pas. Granit Dinding Premium")
        assert result == "granit dinding premium"

    def test_strips_pas_space_prefix(self):
        """Should remove 'pas ' prefix from descriptions."""
        assert "keramik dinding 25x40" == normalize_material_name("Pas Keramik Dinding 25x40")

    def test_strips_instalasi_prefix(self):
        """Should remove 'instalasi' prefix from descriptions."""
        assert "pipa pvc 4 inch" == normalize_material_name("Instalasi Pipa PVC 4 Inch")

    def test_strips_pek_dot_prefix(self):
        """Should remove 'pek.' prefix from descriptions."""
        assert "plester dinding" == normalize_material_name("Pek. Plester Dinding")

    def test_strips_pek_space_prefix(self):
        """Should remove 'pek ' prefix from descriptions."""
        assert "plester dinding" == normalize_material_name("Pek Plester Dinding")

    def test_removes_owner_supply_note_suply(self):
        """Should remove '(Suply By Owner)' notes."""
        result = normalize_material_name("Granit Lantai (Suply By Owner) 60x60")
        assert "suply" not in result.lower()
        assert "owner" not in result.lower()

    def test_removes_owner_supply_note_supply(self):
        """Should remove '(Supply By Owner)' notes."""
        result = normalize_material_name("Granit Lantai (Supply By Owner) 60x60")
        assert "supply" not in result.lower()
        assert "owner" not in result.lower()

    def test_removes_use_existing(self):
        """Should remove '(use existing)' notes."""
        result = normalize_material_name("Pintu (use existing) Kayu")
        assert "existing" not in result.lower()

    def test_removes_existing_parenthesized(self):
        """Should remove '(existing)' notes."""
        result = normalize_material_name("Kusen (existing) Aluminium")
        assert "existing" not in result.lower()

    def test_removes_master_bed_room(self):
        """Should remove 'master bed room' location specifier."""
        result = normalize_material_name("Granit Lantai Master Bed Room 60x60")
        assert "master" not in result.lower()
        assert "bed" not in result.lower()
        assert "room" not in result.lower()

    def test_removes_master_bathroom(self):
        """Should remove 'master bathroom' location specifier."""
        result = normalize_material_name("Keramik Master Bathroom 25x40")
        assert "master" not in result.lower()
        assert "bathroom" not in result.lower()

    def test_removes_living_dining_kitchen(self):
        """Should remove 'living dining kitchen' location specifier."""
        result = normalize_material_name("Granit Living Dining Kitchen 60x60")
        assert "living" not in result.lower()
        assert "dining" not in result.lower()
        assert "kitchen" not in result.lower()

    def test_removes_lantai_floor_number(self):
        """Should remove 'lantai N' floor number specifier."""
        result = normalize_material_name("Granit Lantai 2 Premium")
        # 'lantai 2' should be removed
        assert "lantai 2" not in result.lower()

    def test_removes_area_specifier(self):
        """Should remove 'area <word>' specifier."""
        result = normalize_material_name("Cat Tembok Area Kamar")
        assert "area" not in result.lower()
        assert "kamar" not in result.lower()

    def test_collapses_whitespace(self):
        """Should collapse multiple spaces to single space."""
        result = normalize_material_name("Pas.  Granit   Lantai    60x60")
        assert "  " not in result

    def test_strips_leading_trailing_whitespace(self):
        """Should strip leading and trailing whitespace."""
        result = normalize_material_name("  Granit Dinding Premium  ")
        assert result == "granit dinding premium"

    def test_combined_normalization(self):
        """Should handle multiple normalization rules in one description."""
        result = normalize_material_name(
            "Pas. Granit Lantai (Suply By Owner) Master Bed Room 60x60"
        )
        # Should be left with essentially "granit 60x60" (lantai is kept unless part of floor specifier)
        assert "pas" not in result
        assert "suply" not in result
        assert "owner" not in result
        assert "master" not in result
        assert "bed" not in result
        assert "room" not in result

    def test_lowercases_result(self):
        """Should return lowercase result."""
        result = normalize_material_name("GRANIT LANTAI PREMIUM")
        assert result == "granit lantai premium"


class TestNormalizeShortQuerySkipped:
    """Tests that short queries (< 3 chars) are skipped in batch processing."""

    def test_normalize_returns_short_string(self):
        """When normalization produces < 3 chars, batch_price_materials skips the item."""
        # An item whose description normalizes to something < 3 chars
        short_item = {"id": "1", "description": "AB", "item_type": "material"}
        mock_provider = MagicMock()
        mock_provider.batch_search_sync.return_value = {}
        mock_provider.rank_results.return_value = []

        result = batch_price_materials(
            items=[short_item],
            provider=mock_provider,
            supabase_client=MagicMock(),
            max_lookups=20,
        )

        # Should return empty list since the only item was skipped
        assert result == []
        # Provider should not have been called
        mock_provider.batch_search_sync.assert_not_called()

    def test_empty_description_skipped(self):
        """Items with empty descriptions are skipped."""
        empty_item = {"id": "2", "description": "", "item_type": "material"}
        mock_provider = MagicMock()
        mock_provider.batch_search_sync.return_value = {}

        result = batch_price_materials(
            items=[empty_item],
            provider=mock_provider,
            supabase_client=MagicMock(),
            max_lookups=20,
        )

        assert result == []
        mock_provider.batch_search_sync.assert_not_called()


# =============================================================================
# _build_match_from_scrape Tests
# =============================================================================


def _make_best_seller_score(
    name: str = "Granit Lantai 60x60",
    price_idr: int = 150000,
    url: str = "https://tokopedia.com/product/123",
    seller: str = "Toko Bangunan",
    location: str = "Jakarta",
    rating: float = 4.5,
    sold_count: int = 200,
    total_score: float = 0.85,
) -> BestSellerScore:
    """Helper to create a BestSellerScore for testing."""
    return BestSellerScore(
        product={
            "name": name,
            "price_idr": price_idr,
            "url": url,
            "shop": seller,
            "location": location,
            "rating": rating,
            "sold_count": sold_count,
        },
        total_score=total_score,
        rating_score=0.4,
        sales_score=0.3,
        price_score=0.15,
    )


class TestBuildMatchFromScrapeWithResult:
    """Tests for _build_match_from_scrape when a BestSellerScore is provided."""

    def test_market_unit_price_from_product_price_idr(self):
        """Should set market_unit_price from product['price_idr']."""
        item = {"description": "Granit Lantai 60x60", "contractor_unit_price": 200000, "quantity": 10}
        best = _make_best_seller_score(price_idr=150000)

        match = _build_match_from_scrape(item, "granit lantai 60x60", best)

        assert match.market_unit_price == Decimal("150000")

    def test_market_total_calculation(self):
        """Should compute market_total = market_unit_price * quantity."""
        item = {"description": "Granit Lantai 60x60", "contractor_unit_price": 200000, "quantity": 10}
        best = _make_best_seller_score(price_idr=150000)

        match = _build_match_from_scrape(item, "granit lantai 60x60", best)

        assert match.market_total == Decimal("1500000")

    def test_price_difference_calculation(self):
        """Should compute price_difference = contractor_unit_price - market_unit_price."""
        item = {"description": "Granit Lantai 60x60", "contractor_unit_price": 200000, "quantity": 10}
        best = _make_best_seller_score(price_idr=150000)

        match = _build_match_from_scrape(item, "granit lantai 60x60", best)

        assert match.price_difference == Decimal("50000")

    def test_price_difference_pct_calculation(self):
        """Should compute price_difference_pct = (diff / contractor_price) * 100."""
        item = {"description": "Granit Lantai 60x60", "contractor_unit_price": 200000, "quantity": 10}
        best = _make_best_seller_score(price_idr=150000)

        match = _build_match_from_scrape(item, "granit lantai 60x60", best)

        # (200000 - 150000) / 200000 * 100 = 25.0
        assert match.price_difference_pct == 25.0

    def test_match_confidence_word_overlap(self):
        """Should compute match_confidence from word overlap between query and product name."""
        item = {"description": "Granit Lantai 60x60", "contractor_unit_price": 200000, "quantity": 10}
        # Product name has 2 of 3 query words ("granit", "lantai")
        best = _make_best_seller_score(name="Granit Lantai Premium Hitam")

        match = _build_match_from_scrape(item, "granit lantai 60x60", best)

        # query words: {"granit", "lantai", "60x60"} (3 words)
        # product words: {"granit", "lantai", "premium", "hitam"} (4 words)
        # overlap: {"granit", "lantai"} = 2
        # confidence: 2/3 = 0.666...
        assert abs(match.match_confidence - (2 / 3)) < 0.01

    def test_result_has_marketplace_result(self):
        """Should populate the MarketplaceResult fields correctly."""
        item = {"description": "Granit Lantai 60x60", "contractor_unit_price": 200000, "quantity": 10}
        best = _make_best_seller_score(
            name="Granit Lantai 60x60 Premium",
            price_idr=150000,
            url="https://tokopedia.com/product/123",
            seller="Toko Bangunan",
            location="Jakarta",
            rating=4.5,
            sold_count=200,
            total_score=0.85,
        )

        match = _build_match_from_scrape(item, "granit lantai 60x60", best)

        assert match.result is not None
        assert match.result.product_name == "Granit Lantai 60x60 Premium"
        assert match.result.price_idr == 150000
        assert match.result.url == "https://tokopedia.com/product/123"
        assert match.result.seller == "Toko Bangunan"
        assert match.result.seller_location == "Jakarta"
        assert match.result.rating == 4.5
        assert match.result.sold_count == 200
        assert match.result.best_seller_score == 0.85
        assert match.result.source == MarketplaceSource.TOKOPEDIA

    def test_from_cache_is_false(self):
        """Should set from_cache=False for scrape results."""
        item = {"description": "Granit", "contractor_unit_price": 100000, "quantity": 1}
        best = _make_best_seller_score()

        match = _build_match_from_scrape(item, "granit", best)

        assert match.from_cache is False


class TestBuildMatchFromScrapeNoResult:
    """Tests for _build_match_from_scrape when best=None."""

    def test_result_is_none(self):
        """Should set result=None when no marketplace result found."""
        item = {"description": "Unknown Material", "contractor_unit_price": 100000, "quantity": 5}

        match = _build_match_from_scrape(item, "unknown material", None)

        assert match.result is None

    def test_pricing_fields_are_none(self):
        """Should set all pricing fields to None."""
        item = {"description": "Unknown Material", "contractor_unit_price": 100000, "quantity": 5}

        match = _build_match_from_scrape(item, "unknown material", None)

        assert match.market_unit_price is None
        assert match.market_total is None
        assert match.price_difference is None
        assert match.price_difference_pct is None

    def test_match_confidence_is_zero(self):
        """Should set match_confidence to 0.0 when no result."""
        item = {"description": "Unknown Material", "contractor_unit_price": 100000, "quantity": 5}

        match = _build_match_from_scrape(item, "unknown material", None)

        assert match.match_confidence == 0.0

    def test_search_query_preserved(self):
        """Should preserve the search query even with no result."""
        item = {"description": "Unknown Material", "contractor_unit_price": 100000, "quantity": 5}

        match = _build_match_from_scrape(item, "unknown material", None)

        assert match.search_query == "unknown material"

    def test_from_cache_is_false(self):
        """Should set from_cache=False."""
        item = {"description": "Unknown Material", "contractor_unit_price": 100000, "quantity": 5}

        match = _build_match_from_scrape(item, "unknown material", None)

        assert match.from_cache is False


class TestBuildMatchZeroContractorPrice:
    """Tests for _build_match_from_scrape when contractor_unit_price is 0."""

    def test_price_difference_pct_is_zero(self):
        """When contractor_unit_price is 0, price_difference_pct should be 0."""
        item = {"description": "Granit Lantai 60x60", "contractor_unit_price": 0, "quantity": 10}
        best = _make_best_seller_score(price_idr=150000)

        match = _build_match_from_scrape(item, "granit lantai 60x60", best)

        assert match.price_difference_pct == 0.0

    def test_price_difference_is_zero(self):
        """When contractor_unit_price is 0, price_difference should be 0."""
        item = {"description": "Granit Lantai 60x60", "contractor_unit_price": 0, "quantity": 10}
        best = _make_best_seller_score(price_idr=150000)

        match = _build_match_from_scrape(item, "granit lantai 60x60", best)

        assert match.price_difference == Decimal("0")

    def test_none_contractor_price_treated_as_zero(self):
        """When contractor_unit_price is None, should be treated as 0."""
        item = {"description": "Granit Lantai 60x60", "contractor_unit_price": None, "quantity": 10}
        best = _make_best_seller_score(price_idr=150000)

        match = _build_match_from_scrape(item, "granit lantai 60x60", best)

        assert match.price_difference_pct == 0.0


# =============================================================================
# batch_price_materials Tests
# =============================================================================


class TestBatchPriceMaterialsCallsProvider:
    """Tests that batch_price_materials calls the provider correctly."""

    def test_calls_batch_search_sync_with_normalized_queries(self):
        """Should call provider.batch_search_sync with normalized material names."""
        items = [
            {"id": "1", "description": "Pas. Granit Dinding Premium", "contractor_unit_price": 200000, "quantity": 10},
            {"id": "2", "description": "Instalasi Pipa PVC 4 Inch", "contractor_unit_price": 50000, "quantity": 20},
        ]

        mock_provider = MagicMock()
        mock_provider.batch_search_sync.return_value = {
            "granit dinding premium": [{"name": "Granit Dinding Premium", "price_idr": 150000}],
            "pipa pvc 4 inch": [{"name": "Pipa PVC 4 inch", "price_idr": 30000}],
        }
        mock_provider.rank_results.return_value = [
            _make_best_seller_score(name="Granit Dinding Premium", price_idr=150000),
        ]

        batch_price_materials(
            items=items,
            provider=mock_provider,
            supabase_client=MagicMock(),
            max_lookups=20,
        )

        mock_provider.batch_search_sync.assert_called_once()
        call_args = mock_provider.batch_search_sync.call_args
        queries = call_args[0][0]  # first positional arg
        assert "granit dinding premium" in queries
        assert "pipa pvc 4 inch" in queries

    def test_calls_rank_results_for_each_nonempty_result(self):
        """Should call provider.rank_results for items with candidates."""
        items = [
            {"id": "1", "description": "Granit Dinding Premium", "contractor_unit_price": 200000, "quantity": 10},
            {"id": "2", "description": "Unknown Material XYZ", "contractor_unit_price": 50000, "quantity": 5},
        ]

        mock_provider = MagicMock()
        mock_provider.batch_search_sync.return_value = {
            "granit dinding premium": [{"name": "Granit", "price_idr": 150000}],
            "unknown material xyz": [],  # No results
        }
        mock_provider.rank_results.return_value = [
            _make_best_seller_score(name="Granit", price_idr=150000),
        ]

        batch_price_materials(
            items=items,
            provider=mock_provider,
            supabase_client=MagicMock(),
            max_lookups=20,
        )

        # rank_results called once (for granit), not for empty results
        assert mock_provider.rank_results.call_count == 1

    def test_returns_item_match_pairs(self):
        """Should return (item, MaterialPriceMatch) pairs keyed to the source items."""
        items = [
            {"id": "1", "description": "Granit Dinding Premium", "contractor_unit_price": 200000, "quantity": 10},
        ]

        mock_provider = MagicMock()
        mock_provider.batch_search_sync.return_value = {
            "granit dinding premium": [{"name": "Granit Dinding Premium", "price_idr": 150000}],
        }
        mock_provider.rank_results.return_value = [
            _make_best_seller_score(name="Granit Dinding Premium", price_idr=150000),
        ]

        result = batch_price_materials(
            items=items,
            provider=mock_provider,
            supabase_client=MagicMock(),
            max_lookups=20,
        )

        assert len(result) == 1
        item, match = result[0]
        assert item["id"] == "1"
        assert isinstance(match, MaterialPriceMatch)


class TestBatchPriceMaterialsRespectsMaxLookups:
    """Tests that batch_price_materials respects the max_lookups parameter."""

    def test_only_processes_max_lookups_items(self):
        """With max_lookups=2 and 5 items, only 2 are sent to provider."""
        items = [
            {"id": str(i), "description": f"Material {i} Long Name", "contractor_unit_price": 100000, "quantity": 1}
            for i in range(5)
        ]

        mock_provider = MagicMock()
        mock_provider.batch_search_sync.return_value = {}
        mock_provider.rank_results.return_value = []

        result = batch_price_materials(
            items=items,
            provider=mock_provider,
            supabase_client=MagicMock(),
            max_lookups=2,
        )

        # batch_search_sync should have been called with exactly 2 queries
        call_args = mock_provider.batch_search_sync.call_args
        queries = call_args[0][0]
        assert len(queries) == 2

    def test_returns_matches_only_for_processed_items(self):
        """Should return matches only for items that were processed."""
        items = [
            {"id": str(i), "description": f"Material {i} Long Name", "contractor_unit_price": 100000, "quantity": 1}
            for i in range(5)
        ]

        mock_provider = MagicMock()
        mock_provider.batch_search_sync.return_value = {
            f"material {i} long name": [] for i in range(5)
        }
        mock_provider.rank_results.return_value = []

        result = batch_price_materials(
            items=items,
            provider=mock_provider,
            supabase_client=MagicMock(),
            max_lookups=2,
        )

        assert len(result) == 2


class TestBatchPriceMaterialsPrioritizesOwnerSupply:
    """Tests that batch_price_materials prioritizes owner_supply items."""

    def test_owner_supply_items_processed_first(self):
        """Owner supply items should come first in the lookup queue."""
        items = [
            {"id": "1", "description": "Regular Material ABC", "contractor_unit_price": 100000, "quantity": 1, "is_owner_supply": False},
            {"id": "2", "description": "Owner Supply Material DEF", "contractor_unit_price": 200000, "quantity": 1, "is_owner_supply": True},
            {"id": "3", "description": "Another Regular GHI", "contractor_unit_price": 150000, "quantity": 1, "is_owner_supply": False},
            {"id": "4", "description": "Another Owner Supply JKL", "contractor_unit_price": 250000, "quantity": 1, "is_owner_supply": True},
        ]

        mock_provider = MagicMock()
        mock_provider.batch_search_sync.return_value = {}
        mock_provider.rank_results.return_value = []

        batch_price_materials(
            items=items,
            provider=mock_provider,
            supabase_client=MagicMock(),
            max_lookups=2,
        )

        # With max_lookups=2, only the 2 owner_supply items should be processed
        call_args = mock_provider.batch_search_sync.call_args
        queries = call_args[0][0]
        assert len(queries) == 2
        # Both queries should be from owner_supply items
        assert "owner supply material def" in queries
        assert "another owner supply jkl" in queries

    def test_non_owner_supply_after_owner_supply(self):
        """When max_lookups allows, non-owner_supply items come after owner_supply."""
        items = [
            {"id": "1", "description": "Regular Material ABC", "contractor_unit_price": 100000, "quantity": 1, "is_owner_supply": False},
            {"id": "2", "description": "Owner Supply Material DEF", "contractor_unit_price": 200000, "quantity": 1, "is_owner_supply": True},
        ]

        mock_provider = MagicMock()
        mock_provider.batch_search_sync.return_value = {}
        mock_provider.rank_results.return_value = []

        batch_price_materials(
            items=items,
            provider=mock_provider,
            supabase_client=MagicMock(),
            max_lookups=10,
        )

        call_args = mock_provider.batch_search_sync.call_args
        queries = call_args[0][0]
        assert len(queries) == 2
        # Owner supply should be first
        assert queries[0] == "owner supply material def"
        assert queries[1] == "regular material abc"


# =============================================================================
# persist_price_results Tests
# =============================================================================


class TestPersistPriceResults:
    """Tests for persist_price_results."""

    def test_calls_update_for_each_item_with_result(self):
        """Should call supabase.table('boq_items').update(...) for each match."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()

        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq
        mock_eq.execute.return_value = MagicMock()

        items = [
            {"id": "item-1", "description": "Granit Lantai 60x60"},
            {"id": "item-2", "description": "Pipa PVC 4 inch"},
        ]

        match1 = MaterialPriceMatch(
            search_query="granit lantai 60x60",
            result=MagicMock(
                product_name="Granit Lantai Premium",
                price_idr=150000,
                url="https://tokopedia.com/p1",
                seller="Toko A",
                seller_location="Jakarta",
                rating=4.5,
                sold_count=200,
            ),
            match_confidence=0.8,
            market_unit_price=Decimal("150000"),
            market_total=Decimal("1500000"),
            price_difference=Decimal("50000"),
            price_difference_pct=25.0,
            from_cache=False,
        )

        match2 = MaterialPriceMatch(
            search_query="pipa pvc 4 inch",
            result=None,
            match_confidence=0.0,
            market_unit_price=None,
            market_total=None,
            price_difference=None,
            price_difference_pct=None,
            from_cache=False,
        )

        persist_price_results(
            supabase_client=mock_supabase,
            job_id="job-123",
            pairs=list(zip(items, [match1, match2])),
        )

        # Should have called table("boq_items") twice
        assert mock_supabase.table.call_count == 2
        mock_supabase.table.assert_called_with("boq_items")

    def test_update_includes_correct_fields_for_matched_result(self):
        """Should include all pricing fields when a marketplace result exists."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()

        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq
        mock_eq.execute.return_value = MagicMock()

        items = [{"id": "item-1", "description": "Granit Lantai 60x60"}]

        match = MaterialPriceMatch(
            search_query="granit lantai 60x60",
            result=MagicMock(
                product_name="Granit Lantai Premium",
                price_idr=150000,
                url="https://tokopedia.com/p1",
                seller="Toko A",
                seller_location="Jakarta",
                rating=4.5,
                sold_count=200,
            ),
            match_confidence=0.8,
            market_unit_price=Decimal("150000"),
            market_total=Decimal("1500000"),
            price_difference=Decimal("50000"),
            price_difference_pct=25.0,
            from_cache=False,
        )

        persist_price_results(
            supabase_client=mock_supabase,
            job_id="job-123",
            pairs=list(zip(items, [match])),
        )

        # Get the update data passed to .update()
        update_call = mock_table.update.call_args
        update_data = update_call[0][0]

        assert update_data["search_query"] == "granit lantai 60x60"
        assert update_data["tokopedia_product_name"] == "Granit Lantai Premium"
        assert update_data["tokopedia_price"] == 150000
        assert update_data["tokopedia_url"] == "https://tokopedia.com/p1"
        assert update_data["tokopedia_seller"] == "Toko A"
        assert update_data["tokopedia_seller_location"] == "Jakarta"
        assert update_data["tokopedia_rating"] == 4.5
        assert update_data["tokopedia_sold_count"] == 200
        assert update_data["match_confidence"] == 0.8
        assert update_data["market_unit_price"] == 150000.0
        assert update_data["market_total"] == 1500000.0
        assert update_data["price_difference"] == 50000.0
        assert update_data["price_difference_percent"] == 25.0

        # Should filter by item ID
        mock_update.eq.assert_called_with("id", "item-1")

    def test_update_for_no_result_only_has_search_query(self):
        """When no marketplace result, should only set search_query."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_update = MagicMock()
        mock_eq = MagicMock()

        mock_supabase.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq
        mock_eq.execute.return_value = MagicMock()

        items = [{"id": "item-1", "description": "Unknown Material"}]

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

        persist_price_results(
            supabase_client=mock_supabase,
            job_id="job-123",
            pairs=list(zip(items, [match])),
        )

        update_call = mock_table.update.call_args
        update_data = update_call[0][0]

        assert update_data == {"search_query": "unknown material"}

    def test_skips_items_without_id(self):
        """Should skip items that have no 'id' field."""
        mock_supabase = MagicMock()

        items = [{"description": "No ID Material"}]  # No 'id' key

        match = MaterialPriceMatch(
            search_query="no id material",
            result=None,
            match_confidence=0.0,
            market_unit_price=None,
            market_total=None,
            price_difference=None,
            price_difference_pct=None,
            from_cache=False,
        )

        persist_price_results(
            supabase_client=mock_supabase,
            job_id="job-123",
            pairs=list(zip(items, [match])),
        )

        # Should not have called table() at all
        mock_supabase.table.assert_not_called()


# =============================================================================
# TestMatchQualityGate Tests
# =============================================================================


class TestMatchQualityGate:
    """Matches failing confidence or price-sanity checks become no-result matches."""

    def _run(self, items, products_by_query, **kwargs):
        provider = MagicMock()
        provider.batch_search_sync.return_value = products_by_query

        def mock_rank(results):
            scored = []
            for r in results:
                s = MagicMock()
                s.product = r
                s.total_score = 0.8
                scored.append(s)
            return scored

        provider.rank_results.side_effect = mock_rank
        return batch_price_materials(
            items=items, provider=provider, supabase_client=MagicMock(), **kwargs
        )

    def test_rejects_low_confidence_match(self):
        """Zero word overlap between query and product name -> gated out."""
        items = [{"id": "1", "description": "Vacum Cover Kolam", "quantity": 1,
                  "contractor_unit_price": 120000}]
        products = {"vacum cover kolam": [
            {"name": "Plastik Penyimpanan Baju", "price_idr": 5500},
        ]}
        pairs = self._run(items, products)
        item, match = pairs[0]
        assert match.result is None
        assert match.match_confidence == 0.0
        assert match.market_unit_price is None

    def test_rejects_price_outside_sanity_band(self):
        """Market price >5x contractor price -> gated even with name overlap."""
        items = [{"id": "1", "description": "Batako Anak Tangga", "quantity": 1,
                  "contractor_unit_price": 105000}]
        products = {"batako anak tangga": [
            {"name": "Batako anak tangga premium", "price_idr": 4320000},
        ]}
        pairs = self._run(items, products)
        _, match = pairs[0]
        assert match.result is None

    def test_accepts_reasonable_match(self):
        # "Granit 60x60" normalizes to "granit 60x60" (no lantai/floor-number stripping)
        items = [{"id": "1", "description": "Granit 60x60", "quantity": 2,
                  "contractor_unit_price": 200000}]
        products = {"granit 60x60": [
            {"name": "Granit 60x60 Glossy", "price_idr": 150000},
        ]}
        pairs = self._run(items, products)
        _, match = pairs[0]
        assert match.result is not None
        assert match.market_unit_price == Decimal("150000")

    def test_no_price_band_check_when_contractor_price_missing(self):
        """Without a contractor price there is no band; confidence alone decides."""
        # "Granit 60x60" normalizes to "granit 60x60" (no lantai/floor-number stripping)
        items = [{"id": "1", "description": "Granit 60x60", "quantity": 1,
                  "contractor_unit_price": 0}]
        products = {"granit 60x60": [
            {"name": "Granit 60x60 Glossy", "price_idr": 150000},
        ]}
        pairs = self._run(items, products)
        _, match = pairs[0]
        assert match.result is not None
