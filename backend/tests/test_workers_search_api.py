"""
Unit tests for worker search API endpoint.

Tests cover:
- Cache hit scenario (returns workers immediately)
- Cache miss scenario (triggers background scrape)
- Worker ranking and deduplication integration
- Contact masking for privacy
- Background task execution
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from app.main import app
from app.routes.workers_search import (
    WorkerSearchRequest,
    background_scrape_and_save,
    search_workers,
    transform_to_preview,
)


class TestSearchWorkersEndpoint:
    """Test worker search API endpoint"""

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_cached_workers")
    @patch("app.routes.workers_search.deduplicate_workers")
    @patch("app.routes.workers_search.rank_workers")
    async def test_cache_hit_returns_workers(
        self, mock_rank, mock_dedupe, mock_get_cached
    ):
        """Should return workers immediately when cache hit"""
        # Mock cached workers
        mock_get_cached.return_value = [
            {
                "id": "worker-1",
                "business_name": "Bali Pool Service",
                "trust_score": 85,
                "trust_level": "HIGH",
                "location": "Canggu",
                "specializations": ["pool"],
                "last_scraped_at": (
                    datetime.now(timezone.utc) - timedelta(hours=24)
                ).isoformat(),
            }
        ]

        # Mock deduplication (returns same list)
        mock_dedupe.return_value = mock_get_cached.return_value

        # Mock ranking (returns same list with ranking_score)
        mock_rank.return_value = [
            {**mock_get_cached.return_value[0], "ranking_score": 90.0}
        ]

        request_mock = MagicMock()
        search_request = WorkerSearchRequest(
            project_type="pool",
            location="Canggu",
            min_trust_score=60,
            max_results=10
        )
        background_tasks = BackgroundTasks()

        result = await search_workers(request_mock, search_request, background_tasks)

        assert result.status == "cache_hit"
        assert len(result.workers) == 1
        assert result.total_count == 1
        assert result.cache_age_hours == 24
        mock_get_cached.assert_called_once_with(
            specialization="pool",
            max_age_hours=168
        )

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_cached_workers")
    async def test_cache_miss_triggers_background_scrape(self, mock_get_cached):
        """Should trigger background scrape when cache miss"""
        # Mock cache miss
        mock_get_cached.return_value = None

        request_mock = MagicMock()
        search_request = WorkerSearchRequest(
            project_type="pool",
            location="Canggu"
        )
        background_tasks = BackgroundTasks()

        result = await search_workers(request_mock, search_request, background_tasks)

        assert result.status == "scraping"
        assert len(result.workers) == 0
        assert result.total_count == 0
        assert result.estimated_scrape_time_seconds == 30

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_cached_workers")
    @patch("app.routes.workers_search.deduplicate_workers")
    @patch("app.routes.workers_search.rank_workers")
    async def test_respects_min_trust_score_filter(
        self, mock_rank, mock_dedupe, mock_get_cached
    ):
        """Should filter workers by minimum trust score"""
        mock_get_cached.return_value = [
            {"id": "w1", "trust_score": 85},
            {"id": "w2", "trust_score": 45},
        ]
        mock_dedupe.return_value = mock_get_cached.return_value
        mock_rank.return_value = [{"id": "w1", "trust_score": 85}]  # w2 filtered out

        request_mock = MagicMock()
        search_request = WorkerSearchRequest(
            project_type="pool",
            location="Bali",
            min_trust_score=60
        )
        background_tasks = BackgroundTasks()

        result = await search_workers(request_mock, search_request, background_tasks)

        # Verify rank_workers was called with min_trust_score
        mock_rank.assert_called_once()
        call_kwargs = mock_rank.call_args[1]
        assert call_kwargs["min_trust_score"] == 60

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_cached_workers")
    @patch("app.routes.workers_search.deduplicate_workers")
    @patch("app.routes.workers_search.rank_workers")
    async def test_limits_max_results(
        self, mock_rank, mock_dedupe, mock_get_cached
    ):
        """Should limit results to max_results parameter"""
        mock_get_cached.return_value = [{"id": f"w{i}"} for i in range(20)]
        mock_dedupe.return_value = mock_get_cached.return_value
        mock_rank.return_value = mock_get_cached.return_value[:5]

        request_mock = MagicMock()
        search_request = WorkerSearchRequest(
            project_type="pool",
            location="Bali",
            max_results=5
        )
        background_tasks = BackgroundTasks()

        result = await search_workers(request_mock, search_request, background_tasks)

        assert len(result.workers) == 5
        mock_rank.assert_called_once()
        call_kwargs = mock_rank.call_args[1]
        assert call_kwargs["max_results"] == 5


class TestBackgroundScrapeAndSave:
    """Test background scraping task"""

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.scrape_google_maps_workers")
    @patch("app.routes.workers_search.deduplicate_workers")
    @patch("app.routes.workers_search.calculate_trust_score")
    @patch("app.routes.workers_search.bulk_insert_workers")
    @patch("app.routes.workers_search.update_worker_scraped_timestamp")
    async def test_successful_scrape_workflow(
        self,
        mock_update_timestamp,
        mock_bulk_insert,
        mock_calculate_trust,
        mock_dedupe,
        mock_scrape
    ):
        """Should complete full scrape → dedupe → trust → save workflow"""
        # Mock scraping results
        mock_scrape.return_value = [
            {"gmaps_place_id": "ChIJ1", "business_name": "Bali Pool"},
            {"gmaps_place_id": "ChIJ2", "business_name": "Pool Pro"},
        ]

        # Mock deduplication
        mock_dedupe.return_value = mock_scrape.return_value

        # Mock trust calculation
        mock_calculate_trust.return_value = MagicMock(
            score=85,
            level=MagicMock(value="HIGH"),
            breakdown={"source": 24, "reviews": 20}
        )

        # Mock database save
        mock_bulk_insert.return_value = [
            {"id": "worker-1", "gmaps_place_id": "ChIJ1"},
            {"id": "worker-2", "gmaps_place_id": "ChIJ2"},
        ]

        await background_scrape_and_save("pool", "Canggu")

        # Verify workflow steps
        mock_scrape.assert_called_once_with(
            project_type="pool",
            location="Canggu",
            max_results_per_search=20,
            min_rating=4.0
        )
        mock_dedupe.assert_called_once()
        assert mock_calculate_trust.call_count == 2
        mock_bulk_insert.assert_called_once()
        mock_update_timestamp.assert_called_once_with(["worker-1", "worker-2"])

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.scrape_google_maps_workers")
    async def test_handles_empty_scrape_results(self, mock_scrape):
        """Should handle empty scrape results gracefully"""
        mock_scrape.return_value = []

        # Should not raise exception
        await background_scrape_and_save("pool", "Canggu")

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.scrape_google_maps_workers")
    async def test_handles_scrape_errors_gracefully(self, mock_scrape):
        """Should not raise exception on scrape failure (background task)"""
        mock_scrape.side_effect = Exception("Apify API error")

        # Should not raise exception (prints error instead)
        await background_scrape_and_save("pool", "Canggu")


class TestTransformToPreview:
    """Test worker to preview transformation"""

    def test_masks_business_name(self):
        """Should mask business name for privacy"""
        worker = {
            "id": "worker-1",
            "business_name": "Pak Wayan Pool Service",
            "trust_score": 85,
            "trust_level": "HIGH",
            "location": "Canggu",
            "specializations": ["pool"],
        }

        preview = transform_to_preview(worker)

        assert preview.preview_name != "Pak Wayan Pool Service"
        assert "***" in preview.preview_name or len(preview.preview_name) < len("Pak Wayan Pool Service")

    def test_sets_contact_locked_true(self):
        """Should always set contact_locked to True for previews"""
        worker = {
            "id": "worker-1",
            "business_name": "Test Worker",
            "phone": "+62812345678",  # Should be hidden
            "email": "test@example.com",  # Should be hidden
        }

        preview = transform_to_preview(worker)

        assert preview.contact_locked is True
        assert preview.unlock_price_idr == 50000

    def test_includes_trust_score_detailed(self):
        """Should include detailed trust score breakdown"""
        worker = {
            "id": "worker-1",
            "business_name": "Test Worker",
            "trust_score": 85,
            "trust_level": "HIGH",
            "trust_breakdown": {
                "source": 24,
                "reviews": 20,
                "rating": 18,
                "verification": 15,
                "freshness": 8
            }
        }

        preview = transform_to_preview(worker)

        assert preview.trust_score_detailed["score"] == 85
        assert preview.trust_score_detailed["level"] == "HIGH"
        assert preview.trust_score_detailed["breakdown"]["source"] == 24

    def test_handles_missing_fields(self):
        """Should handle missing optional fields gracefully"""
        worker = {
            "id": "worker-1",
            "business_name": "Minimal Worker",
            # All other fields missing
        }

        preview = transform_to_preview(worker)

        assert preview.id == "worker-1"
        assert preview.location == "Bali"  # Default
        assert preview.specializations == []
        assert preview.trust_score_detailed["score"] == 0


class TestWorkerSearchIntegration:
    """Integration tests using TestClient"""

    def test_search_endpoint_exists(self):
        """Should respond to POST /workers/search"""
        client = TestClient(app)

        # Mock the dependencies
        with patch("app.routes.workers_search.get_cached_workers", return_value=None):
            response = client.post(
                "/workers/search",
                json={
                    "project_type": "pool",
                    "location": "Canggu"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "workers" in data

    def test_validates_request_body(self):
        """Should validate required fields in request body"""
        client = TestClient(app)

        response = client.post(
            "/workers/search",
            json={}  # Missing project_type
        )

        assert response.status_code == 422  # Validation error
