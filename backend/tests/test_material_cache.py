"""
Tests for Material Price Cache Layer

Tests the three-tier caching strategy for Tokopedia price lookups:
- Tier 1: In-memory TTLCache (tested in test_cache.py)
- Tier 2: Supabase materials table (tested here)
- Tier 3: Apify scraping (tested here with mocks)
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock


class TestGetCachedMaterialPrice:
    """Tests for get_cached_material_price function"""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self):
        """Should return None when material is not found"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            # All queries return empty
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.return_value.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_response
            mock_client.return_value.table.return_value.select.return_value.contains.return_value.limit.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_cached_material_price

            result = await get_cached_material_price("nonexistent material")

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_price_when_fresh(self):
        """Should return cached price data when within 7-day TTL"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            # Material with fresh price data
            fresh_timestamp = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            mock_response = MagicMock()
            mock_response.data = [{
                "id": "mat-123",
                "name_id": "Semen Tiga Roda 40kg",
                "name_en": "Portland Cement 40kg",
                "price_min": 75000,
                "price_max": 95000,
                "price_avg": 85000,
                "price_median": 84000,
                "price_sample_size": 5,
                "price_updated_at": fresh_timestamp,
                "tokopedia_search": "semen tiga roda 40kg",
                "unit": "sak",
            }]
            mock_client.return_value.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_cached_material_price

            result = await get_cached_material_price("Semen Tiga Roda")

            assert result is not None
            assert result["material_id"] == "mat-123"
            assert result["price_avg"] == 85000
            assert result["is_fresh"] is True

    @pytest.mark.asyncio
    async def test_returns_stale_when_older_than_7_days(self):
        """Should mark cache as stale when price_updated_at > 7 days ago"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            # Material with stale price data (10 days old)
            stale_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            mock_response = MagicMock()
            mock_response.data = [{
                "id": "mat-123",
                "name_id": "Semen Tiga Roda 40kg",
                "price_avg": 85000,
                "price_updated_at": stale_timestamp,
            }]
            mock_client.return_value.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_cached_material_price

            result = await get_cached_material_price("Semen Tiga Roda")

            assert result is not None
            assert result["is_fresh"] is False

    @pytest.mark.asyncio
    async def test_returns_none_when_no_price_data(self):
        """Should return None when material exists but has no price data"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [{
                "id": "mat-123",
                "name_id": "Semen Tiga Roda 40kg",
                "price_avg": None,  # No price data
                "price_updated_at": None,
            }]
            mock_client.return_value.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_cached_material_price

            result = await get_cached_material_price("Semen Tiga Roda")

            assert result is None


class TestSaveMaterialPriceCache:
    """Tests for save_material_price_cache function"""

    @pytest.mark.asyncio
    async def test_updates_existing_material_prices(self):
        """Should update price fields for existing material"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            # Material exists
            mock_select = MagicMock()
            mock_select.data = [{"id": "mat-123"}]
            mock_client.return_value.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_select

            # Update succeeds
            mock_update = MagicMock()
            mock_client.return_value.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_update

            from app.integrations.supabase import save_material_price_cache

            prices = [
                {"price_idr": 80000},
                {"price_idr": 85000},
                {"price_idr": 90000},
            ]
            result = await save_material_price_cache("Semen Tiga Roda", prices)

            assert result == "mat-123"
            # Verify update was called with calculated prices
            mock_client.return_value.table.return_value.update.assert_called_once()
            call_args = mock_client.return_value.table.return_value.update.call_args[0][0]
            assert call_args["price_min"] == 80000
            assert call_args["price_max"] == 90000
            assert call_args["price_sample_size"] == 3

    @pytest.mark.asyncio
    async def test_creates_new_material_when_not_found(self):
        """Should create new material entry when not in database"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            # Material doesn't exist in name lookup
            mock_name_select = MagicMock()
            mock_name_select.data = []
            mock_client.return_value.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_name_select

            # Material doesn't exist in alias lookup
            mock_alias_select = MagicMock()
            mock_alias_select.data = []
            mock_client.return_value.table.return_value.select.return_value.contains.return_value.limit.return_value.execute.return_value = mock_alias_select

            # Insert succeeds
            mock_insert = MagicMock()
            mock_insert.data = [{"id": "new-mat-456"}]
            mock_client.return_value.table.return_value.insert.return_value.execute.return_value = mock_insert

            from app.integrations.supabase import save_material_price_cache

            prices = [{"price_idr": 100000}]
            result = await save_material_price_cache("New Material", prices)

            assert result == "new-mat-456"
            # Verify insert was called
            mock_client.return_value.table.return_value.insert.assert_called_once()
            call_args = mock_client.return_value.table.return_value.insert.call_args[0][0]
            assert call_args["name_id"] == "New Material"  # Title case normalized
            assert call_args["category"] == "dynamic"  # Dynamic entries marked
            assert call_args["unit"] == "pcs"  # Default unit for unknown materials

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_prices(self):
        """Should return None when prices list is empty"""
        from app.integrations.supabase import save_material_price_cache

        result = await save_material_price_cache("Test Material", [])

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_prices(self):
        """Should return None when all prices are invalid"""
        from app.integrations.supabase import save_material_price_cache

        prices = [
            {"price_idr": 0},
            {"price_idr": None},
            {"name": "no price field"},
        ]
        result = await save_material_price_cache("Test Material", prices)

        assert result is None


class TestGetMaterialByAlias:
    """Tests for get_material_by_alias function"""

    @pytest.mark.asyncio
    async def test_finds_material_by_alias(self):
        """Should find material when alias matches"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [{
                "id": "mat-123",
                "name_id": "Semen Tiga Roda 40kg",
                "aliases": ["semen", "cement", "tiga roda"],
            }]
            mock_client.return_value.table.return_value.select.return_value.contains.return_value.limit.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_material_by_alias

            result = await get_material_by_alias("cement")

            assert result is not None
            assert result["id"] == "mat-123"

    @pytest.mark.asyncio
    async def test_returns_none_when_alias_not_found(self):
        """Should return None when alias doesn't match any material"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.return_value.table.return_value.select.return_value.contains.return_value.limit.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_material_by_alias

            result = await get_material_by_alias("nonexistent")

            assert result is None


class TestGetStaleMaterials:
    """Tests for get_stale_materials function"""

    @pytest.mark.asyncio
    async def test_returns_stale_materials(self):
        """Should return materials with old or missing price data"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            stale_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            mock_response = MagicMock()
            mock_response.data = [
                {"id": "mat-1", "name_id": "Stale Material", "price_updated_at": stale_timestamp},
                {"id": "mat-2", "name_id": "No Price Material", "price_updated_at": None},
            ]
            mock_client.return_value.table.return_value.select.return_value.or_.return_value.order.return_value.limit.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_stale_materials

            result = await get_stale_materials(max_age_days=7, limit=50)

            assert len(result) == 2
            assert result[0]["id"] == "mat-1"
            assert result[1]["id"] == "mat-2"


class TestInferUnitFromName:
    """Tests for _infer_unit_from_name helper function"""

    def test_infers_weight_units(self):
        """Should infer kg/sak for weight-based materials"""
        from app.integrations.supabase import _infer_unit_from_name

        assert _infer_unit_from_name("Semen Portland 50kg") == "kg"
        assert _infer_unit_from_name("Cat Tembok 5 Kilogram") == "kg"
        assert _infer_unit_from_name("Semen Sak 40kg") == "kg"  # kg takes precedence
        assert _infer_unit_from_name("Mortar Sak") == "sak"

    def test_infers_area_units(self):
        """Should infer m²/m³ for area/volume materials"""
        from app.integrations.supabase import _infer_unit_from_name

        assert _infer_unit_from_name("Keramik 60x60 per m²") == "m²"
        assert _infer_unit_from_name("Lantai Granit M2") == "m²"
        assert _infer_unit_from_name("Ready Mix K300 per m³") == "m³"
        assert _infer_unit_from_name("Beton Kubik") == "m³"

    def test_infers_length_units(self):
        """Should infer meter/batang for linear materials"""
        from app.integrations.supabase import _infer_unit_from_name

        assert _infer_unit_from_name("Kabel NYM 3x2.5mm per meter") == "meter"
        assert _infer_unit_from_name("Besi Beton 12mm 6m") == "meter"
        assert _infer_unit_from_name("Pipa PVC 4 inch") == "batang"
        assert _infer_unit_from_name("Hollow Galvanis 40x40") == "batang"

    def test_infers_sheet_units(self):
        """Should infer lembar for sheet materials"""
        from app.integrations.supabase import _infer_unit_from_name

        assert _infer_unit_from_name("Plywood 18mm") == "lembar"
        assert _infer_unit_from_name("Gypsum Board 9mm") == "lembar"
        assert _infer_unit_from_name("Triplek 12mm") == "lembar"

    def test_infers_piece_units(self):
        """Should infer buah for individual items"""
        from app.integrations.supabase import _infer_unit_from_name

        assert _infer_unit_from_name("Bata Merah Press") == "buah"
        assert _infer_unit_from_name("Keramik 30x30") == "buah"
        assert _infer_unit_from_name("Genteng Beton Flat") == "buah"
        assert _infer_unit_from_name("Kran Air Kuningan") == "buah"

    def test_defaults_to_pcs(self):
        """Should default to pcs for unknown materials"""
        from app.integrations.supabase import _infer_unit_from_name

        assert _infer_unit_from_name("Random Unknown Item") == "pcs"
        assert _infer_unit_from_name("Some Material") == "pcs"


class TestExtractPrice:
    """Tests for _extract_price helper function"""

    def test_extracts_price_int_format(self):
        """Should extract price from priceInt field (123webdata format)"""
        from app.integrations.apify import _extract_price

        item = {"priceInt": 85000}
        assert _extract_price(item) == 85000

    def test_extracts_price_dict_format(self):
        """Should extract price from nested dict (jupri format)"""
        from app.integrations.apify import _extract_price

        item = {"price": {"number": 85000}}
        assert _extract_price(item) == 85000

    def test_extracts_price_string_format(self):
        """Should extract price from string with Rp prefix (fatihtahta format)"""
        from app.integrations.apify import _extract_price

        item = {"price": "Rp85.000"}
        assert _extract_price(item) == 85000

        item2 = {"price": "Rp 1.250.000"}
        assert _extract_price(item2) == 1250000

    def test_extracts_price_direct_int(self):
        """Should extract price from direct int value"""
        from app.integrations.apify import _extract_price

        item = {"price": 85000}
        assert _extract_price(item) == 85000

    def test_returns_zero_for_missing_price(self):
        """Should return 0 when no price field found"""
        from app.integrations.apify import _extract_price

        item = {"name": "Product"}
        assert _extract_price(item) == 0


class TestExtractRating:
    """Tests for _extract_rating helper function"""

    def test_extracts_rating_float(self):
        """Should extract rating from float value"""
        from app.integrations.apify import _extract_rating

        item = {"rating": 4.8}
        assert _extract_rating(item) == 4.8

    def test_extracts_rating_string(self):
        """Should extract rating from string value"""
        from app.integrations.apify import _extract_rating

        item = {"rating": "4.5"}
        assert _extract_rating(item) == 4.5

    def test_extracts_rating_average(self):
        """Should extract from ratingAverage field"""
        from app.integrations.apify import _extract_rating

        item = {"ratingAverage": 4.2}
        assert _extract_rating(item) == 4.2

    def test_returns_zero_for_missing_rating(self):
        """Should return 0.0 when no rating found"""
        from app.integrations.apify import _extract_rating

        item = {"name": "Product"}
        assert _extract_rating(item) == 0.0


class TestExtractSoldCount:
    """Tests for _extract_sold_count helper function"""

    def test_extracts_sold_int(self):
        """Should extract sold count from int value"""
        from app.integrations.apify import _extract_sold_count

        item = {"sold": 150}
        assert _extract_sold_count(item) == 150

    def test_extracts_sold_string(self):
        """Should extract sold count from string (fatihtahta format)"""
        from app.integrations.apify import _extract_sold_count

        item = {"sold": "500+ terjual"}
        assert _extract_sold_count(item) == 500

    def test_extracts_sold_ribu_format(self):
        """Should handle 'rb' (ribu/thousand) format"""
        from app.integrations.apify import _extract_sold_count

        # Simple ribu format
        item = {"sold": "2rb+ terjual"}
        assert _extract_sold_count(item) == 2000

    def test_extracts_sold_ribu_with_indonesian_thousands(self):
        """Should handle Indonesian thousands separator (.) in ribu format"""
        from app.integrations.apify import _extract_sold_count

        # Indonesian format: dot is thousands separator
        # "1.500rb" = 1,500 * 1000 = 1,500,000
        item = {"sold": "1.500rb terjual"}
        assert _extract_sold_count(item) == 1500000

        # "10.000rb" = 10,000 * 1000 = 10,000,000
        item2 = {"sold": "10.000rb"}
        assert _extract_sold_count(item2) == 10000000

    def test_extracts_sold_ribu_with_indonesian_decimal(self):
        """Should handle Indonesian decimal separator (,) in ribu format"""
        from app.integrations.apify import _extract_sold_count

        # Indonesian format: comma is decimal separator
        # "1,5rb" = 1.5 * 1000 = 1,500
        item = {"sold": "1,5rb terjual"}
        assert _extract_sold_count(item) == 1500

        # "2,5rb" = 2.5 * 1000 = 2,500
        item2 = {"sold": "2,5rb"}
        assert _extract_sold_count(item2) == 2500

    def test_extracts_sold_ribu_with_both_separators(self):
        """Should handle Indonesian format with both . and , separators"""
        from app.integrations.apify import _extract_sold_count

        # "1.234,5rb" = 1,234.5 * 1000 = 1,234,500
        item = {"sold": "1.234,5rb terjual"}
        assert _extract_sold_count(item) == 1234500

    def test_extracts_sold_nested(self):
        """Should extract from nested stock.sold (jupri format)"""
        from app.integrations.apify import _extract_sold_count

        item = {"stock": {"sold": 300}}
        assert _extract_sold_count(item) == 300

    def test_returns_zero_for_missing_sold(self):
        """Should return 0 when no sold count found"""
        from app.integrations.apify import _extract_sold_count

        item = {"name": "Product"}
        assert _extract_sold_count(item) == 0


class TestScrapeTokopediaPricesIntegration:
    """Integration tests for scrape_tokopedia_prices with mocked dependencies"""

    @pytest.mark.asyncio
    async def test_returns_from_memory_cache_first(self):
        """Should return from in-memory cache without hitting Supabase or Apify"""
        with patch("app.utils.cache.price_scrape_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=[
                {"name": "Cached Product", "price_idr": 85000}
            ])

            from app.integrations.apify import scrape_tokopedia_prices

            result = await scrape_tokopedia_prices("Semen Tiga Roda")

            assert len(result) == 1
            assert result[0]["name"] == "Cached Product"
            mock_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_from_supabase_when_memory_miss(self):
        """Should return from Supabase cache when in-memory cache misses"""
        with patch("app.utils.cache.price_scrape_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            with patch("app.integrations.supabase.get_cached_material_price") as mock_db_cache:
                mock_db_cache.return_value = {
                    "material_id": "mat-123",
                    "name_id": "Semen Tiga Roda 40kg",
                    "price_avg": 85000,
                    "price_min": 80000,
                    "price_max": 90000,
                    "price_median": 84000,
                    "is_fresh": True,
                }

                from app.integrations.apify import scrape_tokopedia_prices

                result = await scrape_tokopedia_prices("Semen Tiga Roda")

                assert len(result) == 1
                assert result[0]["price_idr"] == 85000
                assert result[0]["_cached"] is True
                # Should warm in-memory cache
                mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrapes_apify_when_all_caches_miss(self):
        """Should call Apify when both caches miss"""
        with patch("app.utils.cache.price_scrape_cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            with patch("app.integrations.supabase.get_cached_material_price") as mock_db_cache:
                mock_db_cache.return_value = None  # DB cache miss

                with patch("app.integrations.supabase.save_material_price_cache") as mock_save:
                    mock_save.return_value = "new-mat-123"

                    with patch("app.integrations.apify.get_apify_client") as mock_apify:
                        # Mock Apify actor run
                        mock_actor = MagicMock()
                        mock_run = {"defaultDatasetId": "dataset-123"}
                        mock_actor.call.return_value = mock_run

                        mock_dataset = MagicMock()
                        mock_dataset.iterate_items.return_value = [
                            {"name": "Semen Tiga Roda", "price": 85000, "rating": 4.8, "sold": 500},
                        ]

                        mock_client = MagicMock()
                        mock_client.actor.return_value = mock_actor
                        mock_client.dataset.return_value = mock_dataset
                        mock_apify.return_value = mock_client

                        from app.integrations.apify import scrape_tokopedia_prices

                        result = await scrape_tokopedia_prices("Semen Tiga Roda")

                        # Verify Apify was called with correct actor
                        mock_client.actor.assert_called_with("fatihtahta/tokopedia-scraper")

                        # Verify result
                        assert len(result) == 1
                        assert result[0]["price_idr"] == 85000

                        # Verify both caches were updated
                        mock_cache.set.assert_called_once()
                        mock_save.assert_called_once()


class TestMapTokopediaProduct:
    """Tests for map_tokopedia_product mapper function"""

    def test_maps_complete_product(self):
        """Should map all fields from complete fatihtahta actor output"""
        from app.integrations.apify import map_tokopedia_product

        raw_item = {
            "name": "Semen Tiga Roda 40kg",
            "price": "Rp85.000",
            "rating": 4.8,
            "sold": "500+ terjual",
            "url": "https://tokopedia.com/product/123",
            "shop": {
                "name": "Toko Bangunan Jaya",
                "location": "Jakarta Selatan",
                "badge": "Power Merchant",
            },
        }

        result = map_tokopedia_product(raw_item)

        assert result.name == "Semen Tiga Roda 40kg"
        assert result.price_idr == 85000
        assert result.rating == 4.8
        assert result.sold_count == 500
        assert result.seller_name == "Toko Bangunan Jaya"
        assert result.seller_location == "Jakarta Selatan"
        assert result.seller_tier == "power_merchant"
        assert result.url == "https://tokopedia.com/product/123"

    def test_maps_official_store(self):
        """Should correctly identify official store seller tier"""
        from app.integrations.apify import map_tokopedia_product

        raw_item = {
            "title": "Cat Dulux Weathershield",
            "price": 250000,
            "rating": 4.9,
            "sold": 1000,
            "link": "https://tokopedia.com/dulux/123",
            "shop": {
                "name": "Dulux Official",
                "location": "Jakarta",
                "isOfficial": True,
            },
        }

        result = map_tokopedia_product(raw_item)

        assert result.name == "Cat Dulux Weathershield"
        assert result.seller_tier == "official_store"

    def test_maps_string_shop(self):
        """Should handle shop as string instead of dict"""
        from app.integrations.apify import map_tokopedia_product

        raw_item = {
            "name": "Keramik 60x60",
            "price": 75000,
            "shop": "Toko Keramik",
            "location": "Surabaya",
        }

        result = map_tokopedia_product(raw_item)

        assert result.seller_name == "Toko Keramik"
        assert result.seller_location == "Surabaya"
        assert result.seller_tier == "regular"

    def test_maps_minimal_product(self):
        """Should handle product with missing fields"""
        from app.integrations.apify import map_tokopedia_product

        raw_item = {"name": "Unknown Product"}

        result = map_tokopedia_product(raw_item)

        assert result.name == "Unknown Product"
        assert result.price_idr == 0
        assert result.rating == 0.0
        assert result.sold_count == 0
        assert result.seller_name == ""
        assert result.seller_location == ""
        assert result.seller_tier == "regular"
        assert result.url == ""


class TestAggregateSellerStats:
    """Tests for aggregate_seller_stats function"""

    def test_aggregates_multiple_products(self):
        """Should correctly aggregate stats from multiple products"""
        from app.integrations.apify import TokopediaProduct, aggregate_seller_stats

        products = [
            TokopediaProduct(
                name="Product A",
                price_idr=80000,
                rating=4.5,
                sold_count=100,
                seller_name="Toko A",
                seller_location="Jakarta",
                seller_tier="regular",
                url="",
            ),
            TokopediaProduct(
                name="Product B",
                price_idr=85000,
                rating=4.8,
                sold_count=200,
                seller_name="Toko B",
                seller_location="Jakarta",
                seller_tier="power_merchant",
                url="",
            ),
            TokopediaProduct(
                name="Product C",
                price_idr=90000,
                rating=4.2,
                sold_count=50,
                seller_name="Toko C",
                seller_location="Bandung",
                seller_tier="official_store",
                url="",
            ),
        ]

        result = aggregate_seller_stats(products)

        # Average of 4.5, 4.8, 4.2 = 4.5
        assert result["rating_avg"] == 4.5
        assert result["rating_sample_size"] == 3
        # Sum of 100 + 200 + 50 = 350
        assert result["count_sold_total"] == 350
        # Jakarta appears twice, most common
        assert result["seller_location"] == "Jakarta"
        # official_store is highest tier
        assert result["seller_tier"] == "official_store"

    def test_handles_zero_ratings(self):
        """Should exclude zero ratings from average"""
        from app.integrations.apify import TokopediaProduct, aggregate_seller_stats

        products = [
            TokopediaProduct(
                name="Product A",
                price_idr=80000,
                rating=4.5,
                sold_count=100,
                seller_name="Toko A",
                seller_location="Jakarta",
                seller_tier="regular",
                url="",
            ),
            TokopediaProduct(
                name="Product B",
                price_idr=85000,
                rating=0.0,  # No rating
                sold_count=200,
                seller_name="Toko B",
                seller_location="Jakarta",
                seller_tier="power_merchant",
                url="",
            ),
        ]

        result = aggregate_seller_stats(products)

        # Only Product A has rating
        assert result["rating_avg"] == 4.5
        assert result["rating_sample_size"] == 1

    def test_handles_empty_list(self):
        """Should return empty dict for empty product list"""
        from app.integrations.apify import aggregate_seller_stats

        result = aggregate_seller_stats([])

        assert result == {}

    def test_handles_no_rated_products(self):
        """Should return None rating_avg when no products have ratings"""
        from app.integrations.apify import TokopediaProduct, aggregate_seller_stats

        products = [
            TokopediaProduct(
                name="Product A",
                price_idr=80000,
                rating=0.0,
                sold_count=100,
                seller_name="Toko A",
                seller_location="Jakarta",
                seller_tier="regular",
                url="",
            ),
        ]

        result = aggregate_seller_stats(products)

        assert result["rating_avg"] is None
        assert result["rating_sample_size"] == 0


class TestBestSellerScoring:
    """Tests for Best Seller scoring algorithm with Bali location bonus"""

    def test_is_bali_location(self):
        """Should correctly identify Bali region locations"""
        from app.integrations.apify import _is_bali_location

        # Bali locations should return True
        assert _is_bali_location("Denpasar") is True
        assert _is_bali_location("Badung") is True
        assert _is_bali_location("Bali") is True
        assert _is_bali_location("Kota Denpasar, Bali") is True
        assert _is_bali_location("Gianyar") is True

        # Non-Bali locations should return False
        assert _is_bali_location("Jakarta") is False
        assert _is_bali_location("Surabaya") is False
        assert _is_bali_location("Bandung") is False
        assert _is_bali_location("") is False
        assert _is_bali_location(None) is False

    def test_score_best_seller_price_weight(self):
        """Should weight price at 0.4 with lower = better"""
        from app.integrations.apify import score_best_seller

        # Lowest price product
        low_price = {"price_idr": 80000, "rating": 0, "sold_count": 0, "seller_location": ""}
        # Highest price product
        high_price = {"price_idr": 120000, "rating": 0, "sold_count": 0, "seller_location": ""}

        low_score = score_best_seller(low_price, min_price=80000, max_price=120000)
        high_score = score_best_seller(high_price, min_price=80000, max_price=120000)

        # Low price should have higher price_score
        assert low_score.price_score == 1.0  # Lowest price = 1.0
        assert high_score.price_score == 0.0  # Highest price = 0.0
        # Price contributes 0.4 weight
        assert low_score.total_score > high_score.total_score

    def test_score_best_seller_rating_weight(self):
        """Should weight rating at 0.3"""
        from app.integrations.apify import score_best_seller

        # High rating product
        high_rating = {"price_idr": 100000, "rating": 5.0, "sold_count": 0, "seller_location": ""}
        # Low rating product
        low_rating = {"price_idr": 100000, "rating": 1.0, "sold_count": 0, "seller_location": ""}

        high_score = score_best_seller(high_rating, min_price=100000, max_price=100000)
        low_score = score_best_seller(low_rating, min_price=100000, max_price=100000)

        assert high_score.rating_score == 1.0
        assert low_score.rating_score == 0.2  # 1/5 = 0.2
        assert high_score.total_score > low_score.total_score

    def test_score_best_seller_sales_weight(self):
        """Should weight sales at 0.2 with logarithmic scale"""
        from app.integrations.apify import score_best_seller

        # High sales product
        high_sales = {"price_idr": 100000, "rating": 0, "sold_count": 10000, "seller_location": ""}
        # Low sales product
        low_sales = {"price_idr": 100000, "rating": 0, "sold_count": 10, "seller_location": ""}
        # No sales product
        no_sales = {"price_idr": 100000, "rating": 0, "sold_count": 0, "seller_location": ""}

        high_score = score_best_seller(high_sales, min_price=100000, max_price=100000)
        low_score = score_best_seller(low_sales, min_price=100000, max_price=100000)
        no_score = score_best_seller(no_sales, min_price=100000, max_price=100000)

        assert high_score.sales_score == 1.0  # 10k+ = max
        assert 0 < low_score.sales_score < 0.5  # 10 sales = low but not zero
        assert no_score.sales_score == 0.0

    def test_score_best_seller_bali_bonus(self):
        """Should give 10% bonus to Bali sellers via location weight"""
        from app.integrations.apify import score_best_seller

        # Bali seller
        bali_seller = {"price_idr": 100000, "rating": 4.0, "sold_count": 100, "seller_location": "Denpasar"}
        # Non-Bali seller (same stats)
        jakarta_seller = {"price_idr": 100000, "rating": 4.0, "sold_count": 100, "seller_location": "Jakarta"}

        bali_score = score_best_seller(bali_seller, min_price=100000, max_price=100000)
        jakarta_score = score_best_seller(jakarta_seller, min_price=100000, max_price=100000)

        # Bali gets full location score (1.0), Jakarta gets half (0.5)
        assert bali_score.location_score == 1.0
        assert jakarta_score.location_score == 0.5
        assert bali_score.is_bali_seller is True
        assert jakarta_score.is_bali_seller is False

        # Bali seller should have higher total score
        # Location weight is 0.1, so difference is 0.05 (0.1 * 0.5)
        score_diff = bali_score.total_score - jakarta_score.total_score
        assert abs(score_diff - 0.05) < 0.001

    def test_rank_best_sellers(self):
        """Should rank products and return top N"""
        from app.integrations.apify import rank_best_sellers

        products = [
            {"price_idr": 120000, "rating": 3.0, "sold_count": 50, "seller_location": "Jakarta"},
            {"price_idr": 80000, "rating": 4.5, "sold_count": 500, "seller_location": "Denpasar"},  # Should win
            {"price_idr": 100000, "rating": 4.0, "sold_count": 100, "seller_location": "Surabaya"},
        ]

        ranked = rank_best_sellers(products, top_n=2)

        assert len(ranked) == 2
        # Denpasar seller should be #1 (low price, high rating, Bali bonus)
        assert ranked[0].product["seller_location"] == "Denpasar"
        assert ranked[0].is_bali_seller is True
        # Scores should be descending
        assert ranked[0].total_score > ranked[1].total_score

    def test_rank_best_sellers_empty(self):
        """Should handle empty product list"""
        from app.integrations.apify import rank_best_sellers

        ranked = rank_best_sellers([])
        assert ranked == []

    def test_rank_best_sellers_no_valid_prices(self):
        """Should handle products with no valid prices"""
        from app.integrations.apify import rank_best_sellers

        products = [
            {"price_idr": 0, "rating": 4.0, "sold_count": 100, "seller_location": "Jakarta"},
            {"price_idr": None, "rating": 4.0, "sold_count": 100, "seller_location": "Bali"},
        ]

        ranked = rank_best_sellers(products, top_n=5)
        assert ranked == []
