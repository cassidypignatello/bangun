"""
Tests for BOQ pricer cache layer.

Validates the Supabase materials table cache integration:
- Cache key canonicalization
- Cache lookup with TTL
- Building matches from cache
- Writing scrape results to cache
- Pipeline integration (cache hits skip Apify)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# canonicalize_for_cache
# =============================================================================


class TestCanonicalizeForCache:
    """Tests for cache key generation."""

    def test_sorts_words_alphabetically(self):
        from app.services.boq_pricer import canonicalize_for_cache

        assert canonicalize_for_cache("granit dinding premium") == "dinding granit premium"

    def test_lowercases_input(self):
        from app.services.boq_pricer import canonicalize_for_cache

        assert canonicalize_for_cache("Granit Dinding") == "dinding granit"

    def test_preserves_numbers_and_dimensions(self):
        from app.services.boq_pricer import canonicalize_for_cache

        assert canonicalize_for_cache("granit 60x60 dinding") == "60x60 dinding granit"

    def test_same_key_regardless_of_word_order(self):
        from app.services.boq_pricer import canonicalize_for_cache

        key1 = canonicalize_for_cache("pipa pvc rucika 4 inch")
        key2 = canonicalize_for_cache("rucika pvc pipa inch 4")
        assert key1 == key2

    def test_handles_single_word(self):
        from app.services.boq_pricer import canonicalize_for_cache

        assert canonicalize_for_cache("semen") == "semen"

    def test_handles_empty_string(self):
        from app.services.boq_pricer import canonicalize_for_cache

        assert canonicalize_for_cache("") == ""


# =============================================================================
# _lookup_cache
# =============================================================================


class TestLookupCache:
    """Tests for cache query logic."""

    def test_returns_fresh_entries(self):
        from app.services.boq_pricer import _lookup_cache

        fresh_time = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()

        mock_sb = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {
                "normalized_name": "60x60 dinding granit",
                "price_median": 195000,
                "price_updated_at": fresh_time,
                "name_id": "Granit Dinding 60x60",
            },
        ]
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_result

        hits = _lookup_cache(mock_sb, ["60x60 dinding granit"])

        assert "60x60 dinding granit" in hits
        assert hits["60x60 dinding granit"]["price_median"] == 195000

    def test_excludes_stale_entries(self):
        from app.services.boq_pricer import _lookup_cache

        stale_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        mock_sb = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {
                "normalized_name": "60x60 dinding granit",
                "price_median": 195000,
                "price_updated_at": stale_time,
            },
        ]
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_result

        hits = _lookup_cache(mock_sb, ["60x60 dinding granit"])

        assert len(hits) == 0

    def test_excludes_entries_without_price_median(self):
        from app.services.boq_pricer import _lookup_cache

        fresh_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        mock_sb = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {
                "normalized_name": "60x60 dinding granit",
                "price_median": None,
                "price_updated_at": fresh_time,
            },
        ]
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_result

        hits = _lookup_cache(mock_sb, ["60x60 dinding granit"])

        assert len(hits) == 0

    def test_returns_empty_on_db_error(self):
        from app.services.boq_pricer import _lookup_cache

        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.side_effect = Exception("DB error")

        hits = _lookup_cache(mock_sb, ["some key"])

        assert hits == {}

    def test_returns_empty_for_empty_keys(self):
        from app.services.boq_pricer import _lookup_cache

        hits = _lookup_cache(MagicMock(), [])

        assert hits == {}

    def test_handles_z_suffix_timestamps(self):
        """Supabase often returns timestamps with Z suffix."""
        from app.services.boq_pricer import _lookup_cache

        fresh_time = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        mock_sb = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [
            {
                "normalized_name": "pvc pipa",
                "price_median": 72000,
                "price_updated_at": fresh_time,
            },
        ]
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_result

        hits = _lookup_cache(mock_sb, ["pvc pipa"])

        assert "pvc pipa" in hits


# =============================================================================
# _build_match_from_cache
# =============================================================================


class TestBuildMatchFromCache:
    """Tests for building MaterialPriceMatch from cache rows."""

    def test_uses_price_median_as_market_price(self):
        from app.services.boq_pricer import _build_match_from_cache

        item = {"contractor_unit_price": 250000, "quantity": 10}
        cache_row = {
            "price_median": 195000,
            "name_id": "Granit Dinding 60x60",
            "tokopedia_affiliate_url": "https://tokopedia.com/cached",
            "seller_location": "Jakarta",
            "rating_avg": 4.5,
            "count_sold_total": 500,
        }

        match = _build_match_from_cache(item, "granit dinding 60x60", cache_row)

        assert match.market_unit_price == Decimal("195000")
        assert match.market_total == Decimal("1950000")
        assert match.from_cache is True

    def test_calculates_price_difference(self):
        from app.services.boq_pricer import _build_match_from_cache

        item = {"contractor_unit_price": 100000, "quantity": 1}
        cache_row = {"price_median": 80000, "name_id": "Test"}

        match = _build_match_from_cache(item, "test", cache_row)

        assert match.price_difference == Decimal("20000")
        assert match.price_difference_pct == 20.0

    def test_sets_source_to_cached(self):
        from app.services.boq_pricer import _build_match_from_cache
        from app.integrations.marketplace import MarketplaceSource

        item = {"contractor_unit_price": 100000, "quantity": 1}
        cache_row = {"price_median": 80000, "name_id": "Test"}

        match = _build_match_from_cache(item, "test", cache_row)

        assert match.result.source == MarketplaceSource.CACHED

    def test_has_high_confidence(self):
        from app.services.boq_pricer import _build_match_from_cache

        item = {"contractor_unit_price": 100000, "quantity": 1}
        cache_row = {"price_median": 80000, "name_id": "Test"}

        match = _build_match_from_cache(item, "test", cache_row)

        assert match.match_confidence == 0.85


# =============================================================================
# _write_cache
# =============================================================================


def _make_write_cache_mock(update_results: list[list], insert_result: list | None = None):
    """
    Build a mock Supabase client for _write_cache's update → adopt → insert flow.

    Args:
        update_results: .data payloads for successive update().…execute() calls.
        insert_result: .data payload for insert().execute().

    Returns:
        (mock_client, update_mock, insert_mock)
    """
    mock_sb = MagicMock()
    table = mock_sb.table.return_value

    update_chains = []
    for data in update_results:
        chain = MagicMock()
        # Both .eq(...) and .ilike(...).is_(...) terminate in .execute()
        chain.eq.return_value.execute.return_value = MagicMock(data=data)
        chain.ilike.return_value.is_.return_value.execute.return_value = MagicMock(data=data)
        update_chains.append(chain)
    table.update.side_effect = update_chains

    table.insert.return_value.execute.return_value = MagicMock(data=insert_result or [])

    return mock_sb, table.update, table.insert


class TestWriteCache:
    """Tests for the cache write strategy (update → adopt seeded row → insert)."""

    def test_updates_existing_cache_row(self):
        """A row matched by normalized_name gets price fields updated, nothing else."""
        from app.services.boq_pricer import _write_cache

        mock_sb, update_mock, insert_mock = _make_write_cache_mock(
            update_results=[[{"id": "existing"}]],
        )

        best_product = {
            "name": "Granit Premium",
            "price_idr": 195000,
            "url": "https://tok.com/1",
            "location": "Jakarta",
        }
        candidates = [
            {"price_idr": 180000, "rating": 4.5, "sold_count": 100},
            {"price_idr": 195000, "rating": 4.7, "sold_count": 200},
            {"price_idr": 210000, "rating": 4.3, "sold_count": 50},
        ]

        _write_cache(mock_sb, "granit premium", "granit premium", best_product, candidates)

        mock_sb.table.assert_called_with("materials")
        update_mock.assert_called_once()
        insert_mock.assert_not_called()

        data = update_mock.call_args[0][0]
        assert data["price_min"] == 180000
        assert data["price_max"] == 210000
        assert data["price_median"] == 195000
        assert data["price_sample_size"] == 3
        assert data["tokopedia_search"] == "granit premium"

    def test_adopts_seeded_row_by_name(self):
        """A seeded row matched by name_id gets adopted: normalized_name is set."""
        from app.services.boq_pricer import _write_cache

        mock_sb, update_mock, insert_mock = _make_write_cache_mock(
            update_results=[[], [{"id": "seeded"}]],
        )

        _write_cache(
            mock_sb, "granit 60x60", "60x60 granit",
            {"name": "Granit", "price_idr": 150000},
            [{"price_idr": 150000}],
        )

        assert update_mock.call_count == 2
        insert_mock.assert_not_called()

        adopt_data = update_mock.call_args_list[1][0][0]
        assert adopt_data["normalized_name"] == "60x60 granit"
        assert adopt_data["price_median"] == 150000

    def test_inserts_new_row_with_required_fields(self):
        """With no matching row, inserts a full row satisfying NOT NULL constraints."""
        from app.services.boq_pricer import _write_cache

        mock_sb, update_mock, insert_mock = _make_write_cache_mock(
            update_results=[[], []],
        )

        _write_cache(
            mock_sb, "semen tiga roda 40kg", "40kg roda semen tiga",
            {"name": "Semen Tiga Roda", "price_idr": 82000},
            [{"price_idr": 82000}],
            unit="sak",
        )

        insert_mock.assert_called_once()
        data = insert_mock.call_args[0][0]

        assert data["normalized_name"] == "40kg roda semen tiga"
        assert data["name_id"] == "semen tiga roda 40kg"
        assert data["name_en"] == "semen tiga roda 40kg"
        assert data["category"] == "boq_scraped"
        assert data["unit"] == "sak"
        assert data["material_code"].startswith("BOQ")
        assert len(data["material_code"]) <= 20

    def test_material_code_is_deterministic(self):
        """The same cache key always yields the same material_code."""
        from app.services.boq_pricer import _cache_material_code

        assert _cache_material_code("40kg roda semen tiga") == _cache_material_code("40kg roda semen tiga")
        assert _cache_material_code("a") != _cache_material_code("b")

    def test_insert_defaults_unit_when_missing(self):
        """Without a unit, inserts fall back to 'unit'."""
        from app.services.boq_pricer import _write_cache

        mock_sb, _, insert_mock = _make_write_cache_mock(update_results=[[], []])

        _write_cache(
            mock_sb, "query thing", "query thing",
            {"name": "Test", "price_idr": 100},
            [{"price_idr": 100}],
        )

        assert insert_mock.call_args[0][0]["unit"] == "unit"

    def test_calculates_correct_median_even_count(self):
        from app.services.boq_pricer import _write_cache

        mock_sb, update_mock, _ = _make_write_cache_mock(
            update_results=[[{"id": "existing"}]],
        )

        best = {"name": "Test", "price_idr": 100}
        candidates = [
            {"price_idr": 100},
            {"price_idr": 200},
        ]

        _write_cache(mock_sb, "test", "test", best, candidates)

        data = update_mock.call_args[0][0]
        assert data["price_median"] == 150  # (100+200)/2

    def test_skips_if_no_best_product(self):
        from app.services.boq_pricer import _write_cache

        mock_sb = MagicMock()
        _write_cache(mock_sb, "query", "key", None, [])

        mock_sb.table.assert_not_called()

    def test_skips_if_no_prices(self):
        from app.services.boq_pricer import _write_cache

        mock_sb = MagicMock()
        _write_cache(mock_sb, "query", "key", {"name": "Test"}, [{"name": "no price"}])

        mock_sb.table.assert_not_called()

    def test_handles_write_failure_gracefully(self):
        from app.services.boq_pricer import _write_cache

        mock_sb = MagicMock()
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.side_effect = Exception("DB error")

        # Should not raise
        _write_cache(
            mock_sb, "query", "key",
            {"name": "Test", "price_idr": 100},
            [{"price_idr": 100}],
        )

    def test_median_ignores_price_outliers(self):
        """Stats are computed over candidates near the best product's price."""
        from app.services.boq_pricer import _write_cache

        mock_sb, update_mock, _ = _make_write_cache_mock(
            update_results=[[{"id": "existing"}]],
        )

        best = {"name": "Cat Kolam 1Kg", "price_idr": 78000}
        candidates = [
            {"price_idr": 75000},
            {"price_idr": 78000},
            {"price_idr": 82000},
            {"price_idr": 2900000},   # bulk-pack mismatch
            {"price_idr": 9150000},   # different product entirely
        ]

        _write_cache(mock_sb, "cat kolam", "cat kolam", best, candidates)

        data = update_mock.call_args[0][0]
        assert data["price_median"] == 78000
        assert data["price_max"] == 82000
        assert data["price_sample_size"] == 3

    def test_rating_and_sold_stats_ignore_outliers(self):
        """Outlier products' ratings/sold counts must not pollute cache aggregates."""
        from app.services.boq_pricer import _write_cache

        mock_sb, update_mock, _ = _make_write_cache_mock(
            update_results=[[{"id": "existing"}]],
        )

        best = {"name": "Cat Kolam 1Kg", "price_idr": 78000}
        candidates = [
            {"price_idr": 75000, "rating": 4.6, "sold_count": 100},
            {"price_idr": 78000, "rating": 4.8, "sold_count": 200},
            {"price_idr": 9150000, "rating": 1.0, "sold_count": 99999},  # mismatched product
        ]

        _write_cache(mock_sb, "cat kolam", "cat kolam", best, candidates)

        data = update_mock.call_args[0][0]
        assert data["rating_avg"] == pytest.approx(4.7)
        assert data["rating_sample_size"] == 2
        assert data["count_sold_total"] == 300


# =============================================================================
# Pipeline Integration: Cache + Scrape
# =============================================================================


class TestBatchPriceMaterialsWithCache:
    """Test that batch_price_materials integrates the cache layer correctly."""

    def test_uses_cache_for_fresh_entries(self):
        """Items with fresh cache should NOT trigger marketplace scrape."""
        from app.services.boq_pricer import batch_price_materials

        items = [
            {"description": "Granit Dinding Premium 60x60", "item_type": "material",
             "quantity": 10, "contractor_unit_price": 250000, "is_owner_supply": True},
        ]

        fresh_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

        mock_sb = MagicMock()
        cache_result = MagicMock()
        cache_result.data = [
            {
                "normalized_name": "60x60 dinding granit premium",
                "price_median": 195000,
                "price_updated_at": fresh_time,
                "name_id": "Granit Dinding Premium",
            },
        ]
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = cache_result

        provider = MagicMock()

        matches = batch_price_materials(
            items=items,
            provider=provider,
            supabase_client=mock_sb,
            max_lookups=20,
        )

        # Provider should NOT be called (everything from cache)
        provider.batch_search_sync.assert_not_called()

        assert len(matches) == 1
        item, match = matches[0]
        assert item["description"] == "Granit Dinding Premium 60x60"
        assert match.from_cache is True
        assert match.market_unit_price == Decimal("195000")

    def test_scrapes_only_cache_misses(self):
        """Only uncached items should trigger marketplace scrape."""
        from app.services.boq_pricer import batch_price_materials

        items = [
            {"description": "Granit Dinding Premium 60x60", "item_type": "material",
             "quantity": 10, "contractor_unit_price": 250000, "is_owner_supply": True},
            {"description": "Pipa PVC Rucika 4 inch", "item_type": "material",
             "quantity": 5, "contractor_unit_price": 85000, "is_owner_supply": False},
        ]

        fresh_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

        mock_sb = MagicMock()
        cache_result = MagicMock()
        # Only granit is cached
        cache_result.data = [
            {
                "normalized_name": "60x60 dinding granit premium",
                "price_median": 195000,
                "price_updated_at": fresh_time,
                "name_id": "Granit Dinding Premium",
            },
        ]
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = cache_result

        provider = MagicMock()
        provider.batch_search_sync.return_value = {
            "pipa pvc rucika 4 inch": [
                {"name": "Pipa PVC Rucika 4 inch", "price_idr": 72000, "url": "", "shop": "", "location": "", "rating": 4.5, "sold_count": 100},
            ],
        }

        def mock_rank(results):
            scored = []
            for r in results:
                score = MagicMock()
                score.product = r
                score.total_score = 0.7
                scored.append(score)
            return scored

        provider.rank_results.side_effect = mock_rank

        matches = batch_price_materials(
            items=items,
            provider=provider,
            supabase_client=mock_sb,
            max_lookups=20,
        )

        # Provider should be called only with the uncached query
        provider.batch_search_sync.assert_called_once()
        queried = provider.batch_search_sync.call_args[0][0]
        assert "pipa pvc rucika 4 inch" in queried
        assert len(queried) == 1  # Only the PVC pipe

        assert len(matches) == 2
        # Find which is cached vs scraped
        cached = [m for _, m in matches if m.from_cache]
        scraped = [m for _, m in matches if not m.from_cache]
        assert len(cached) == 1
        assert len(scraped) == 1

    def test_writes_scrape_results_to_cache(self):
        """After scraping, results should be upserted into materials table."""
        from app.services.boq_pricer import batch_price_materials

        items = [
            {"description": "Semen Tiga Roda 40kg", "item_type": "material",
             "quantity": 5, "contractor_unit_price": 90000, "is_owner_supply": False},
        ]

        mock_sb = MagicMock()
        # No cache hits
        cache_result = MagicMock()
        cache_result.data = []
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = cache_result

        provider = MagicMock()
        provider.batch_search_sync.return_value = {
            "semen tiga roda 40kg": [
                {"name": "Semen Tiga Roda 40kg", "price_idr": 82000, "url": "https://tok.com/1", "location": "Jakarta", "rating": 4.8, "sold_count": 500},
            ],
        }

        def mock_rank(results):
            scored = []
            for r in results:
                score = MagicMock()
                score.product = r
                score.total_score = 0.9
                scored.append(score)
            return scored

        provider.rank_results.side_effect = mock_rank

        batch_price_materials(
            items=items,
            provider=provider,
            supabase_client=mock_sb,
            max_lookups=20,
        )

        # Verify the cache write went to the materials table
        # (step 1 of the write strategy: update by normalized_name)
        update_calls = mock_sb.table.return_value.update.call_args_list
        assert len(update_calls) >= 1

        update_data = update_calls[0][0][0]
        assert update_data["price_median"] == 82000
        assert update_data["tokopedia_search"] == "semen tiga roda 40kg"

        eq_call = mock_sb.table.return_value.update.return_value.eq.call_args
        assert eq_call[0] == ("normalized_name", "40kg roda semen tiga")

    def test_progress_callback_with_mixed_cache(self):
        """Progress should cover both cache (40-55%) and scrape (55-85%) ranges."""
        from app.services.boq_pricer import batch_price_materials

        items = [
            {"description": "Granit Dinding Premium", "item_type": "material",
             "quantity": 1, "contractor_unit_price": 200000, "is_owner_supply": True},
            {"description": "Pipa PVC Besar", "item_type": "material",
             "quantity": 1, "contractor_unit_price": 100000, "is_owner_supply": False},
        ]

        fresh_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        mock_sb = MagicMock()
        cache_result = MagicMock()
        cache_result.data = [
            {
                "normalized_name": "dinding granit premium",
                "price_median": 180000,
                "price_updated_at": fresh_time,
                "name_id": "Granit Dinding",
            },
        ]
        mock_sb.table.return_value.select.return_value.in_.return_value.execute.return_value = cache_result

        provider = MagicMock()
        provider.batch_search_sync.return_value = {"pipa pvc besar": []}

        progress_values = []
        batch_price_materials(
            items=items,
            provider=provider,
            supabase_client=mock_sb,
            max_lookups=20,
            progress_callback=lambda pct: progress_values.append(pct),
        )

        # Should have progress values in both ranges
        assert len(progress_values) >= 2
        assert all(40 <= v <= 85 for v in progress_values)
