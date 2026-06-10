"""
Unit tests for worker detail endpoint with unlock verification.

Tests cover:
- Worker exists check (404 if not found)
- Unlock verification (402 if not unlocked)
- Full details transformation with contacts
- Negotiation tips generation
- Contact information unmasking
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app
from app.routes.workers_search import (
    generate_negotiation_tips,
    get_worker_details,
    transform_to_full_details,
)


class TestWorkerDetailsEndpoint:
    """Test worker detail endpoint with unlock verification"""

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_worker_by_id")
    @patch("app.routes.workers_search.limiter.limit")
    async def test_returns_404_when_worker_not_found(
        self, mock_limit, mock_get_worker
    ):
        """Should return 404 when worker doesn't exist"""
        mock_limit.return_value = lambda func: func
        mock_get_worker.return_value = None

        request_mock = MagicMock(spec=Request)
        request_mock.client = MagicMock()
        request_mock.client.host = "127.0.0.1"

        with pytest.raises(Exception) as exc_info:
            await get_worker_details(
                request_mock,
                worker_id="nonexistent-id",
                user_email="user@example.com"
            )

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_worker_by_id")
    @patch("app.routes.workers_search.check_worker_unlock")
    @patch("app.routes.workers_search.limiter.limit")
    async def test_returns_402_when_worker_not_unlocked(
        self, mock_limit, mock_check_unlock, mock_get_worker
    ):
        """Should return 402 Payment Required when worker not unlocked"""
        mock_limit.return_value = lambda func: func

        # Worker exists
        mock_get_worker.return_value = {
            "id": "worker-1",
            "business_name": "Test Worker",
        }

        # But not unlocked
        mock_check_unlock.return_value = False

        request_mock = MagicMock(spec=Request)
        request_mock.client = MagicMock()
        request_mock.client.host = "127.0.0.1"

        with pytest.raises(Exception) as exc_info:
            await get_worker_details(
                request_mock,
                worker_id="worker-1",
                user_email="user@example.com"
            )

        assert exc_info.value.status_code == 402
        assert "locked" in str(exc_info.value.detail).lower() or "payment" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_worker_by_id")
    @patch("app.routes.workers_search.check_worker_unlock")
    @patch("app.routes.workers_search.limiter.limit")
    async def test_returns_full_details_when_unlocked(
        self, mock_limit, mock_check_unlock, mock_get_worker
    ):
        """Should return full worker details when unlocked"""
        mock_limit.return_value = lambda func: func

        # Worker exists with full data
        mock_get_worker.return_value = {
            "id": "worker-1",
            "business_name": "Pak Wayan Pool Service",
            "trust_score": 85,
            "trust_level": "HIGH",
            "trust_breakdown": {"source": 24, "reviews": 20},
            "source_tier": "google_maps",
            "gmaps_review_count": 50,
            "gmaps_rating": 4.8,
            "phone": "+62361234567",
            "whatsapp": "+62812345678",
            "email": "pakwayan@example.com",
            "website": "https://pakwayanpool.com",
            "location": "Canggu",
            "address": "Jl. Raya Canggu No. 123",
            "latitude": -8.6500,
            "longitude": 115.1333,
            "gmaps_url": "https://maps.google.com/...",
            "specializations": ["pool"],
            "gmaps_photos_count": 15,
            "opening_hours": "Mon-Sat 8AM-5PM",
            "gmaps_categories": ["Pool contractor", "Construction"],
            "preview_review": "Excellent pool work, finished on time - Sarah M.",
        }

        # Worker is unlocked
        mock_check_unlock.return_value = True

        request_mock = MagicMock(spec=Request)
        request_mock.client = MagicMock()
        request_mock.client.host = "127.0.0.1"

        result = await get_worker_details(
            request_mock,
            worker_id="worker-1",
            user_email="user@example.com"
        )

        # Verify contact information is unmasked
        assert result.contact.phone == "+62361234567"
        assert result.contact.whatsapp == "+62812345678"
        assert result.contact.email == "pakwayan@example.com"
        assert result.contact.website == "https://pakwayanpool.com"

        # Verify business name is NOT masked
        assert result.business_name == "Pak Wayan Pool Service"

        # Verify location details
        assert result.location.address == "Jl. Raya Canggu No. 123"
        assert result.location.latitude == -8.6500
        assert result.location.longitude == 115.1333

        # Verify trust score
        assert result.trust_score.total_score == 85
        assert result.trust_score.trust_level.value == "HIGH"

        # Verify negotiation script exists
        assert result.negotiation_script is not None
        assert len(result.negotiation_script) > 0


class TestTransformToFullDetails:
    """Test worker to full details transformation"""

    def test_unmasks_all_contact_information(self):
        """Should unmask all contact fields"""
        worker = {
            "id": "worker-1",
            "business_name": "Pak Wayan Pool Service",
            "trust_score": 85,
            "trust_level": "HIGH",
            "trust_breakdown": {},
            "source_tier": "google_maps",
            "gmaps_review_count": 50,
            "phone": "+62361234567",
            "whatsapp": "+62812345678",
            "email": "test@example.com",
            "website": "https://example.com",
            "location": "Canggu",
            "specializations": ["pool"],
        }

        details = transform_to_full_details(worker)

        assert details.contact.phone == "+62361234567"
        assert details.contact.whatsapp == "+62812345678"
        assert details.contact.email == "test@example.com"
        assert details.contact.website == "https://example.com"

    def test_includes_full_location_details(self):
        """Should include complete location information"""
        worker = {
            "id": "worker-1",
            "business_name": "Test Worker",
            "trust_score": 75,
            "trust_level": "HIGH",
            "trust_breakdown": {},
            "source_tier": "google_maps",
            "gmaps_review_count": 20,
            "location": "Canggu",
            "address": "Jl. Raya Canggu No. 123",
            "latitude": -8.6500,
            "longitude": 115.1333,
            "gmaps_url": "https://maps.google.com/place/...",
            "specializations": ["pool"],
        }

        details = transform_to_full_details(worker)

        assert details.location.area == "Canggu"
        assert details.location.address == "Jl. Raya Canggu No. 123"
        assert details.location.latitude == -8.6500
        assert details.location.longitude == 115.1333
        assert details.location.maps_url == "https://maps.google.com/place/..."

    def test_includes_negotiation_script(self):
        """Should generate negotiation tips"""
        worker = {
            "id": "worker-1",
            "business_name": "Test Worker",
            "trust_score": 87,
            "trust_level": "VERIFIED",
            "trust_breakdown": {},
            "source_tier": "google_maps",
            "gmaps_review_count": 100,
            "gmaps_rating": 4.8,
            "location": "Canggu",
            "specializations": ["pool"],
        }

        details = transform_to_full_details(worker)

        assert details.negotiation_script is not None
        assert "VERIFIED" in details.negotiation_script
        assert "87" in details.negotiation_script
        assert "100" in details.negotiation_script  # review count

    def test_includes_reviews_from_preview(self):
        """Should include review from preview_review field"""
        worker = {
            "id": "worker-1",
            "business_name": "Test Worker",
            "trust_score": 75,
            "trust_level": "HIGH",
            "trust_breakdown": {},
            "source_tier": "google_maps",
            "gmaps_review_count": 50,
            "gmaps_rating": 4.5,
            "location": "Canggu",
            "specializations": ["pool"],
            "preview_review": "Excellent work, highly recommend!",
        }

        details = transform_to_full_details(worker)

        assert len(details.reviews) == 1
        assert details.reviews[0].text == "Excellent work, highly recommend!"
        assert details.reviews[0].rating == 4  # int(4.5)
        assert details.reviews[0].source == "google_maps"

    def test_handles_missing_contact_fields(self):
        """Should handle workers with missing contact information"""
        worker = {
            "id": "worker-1",
            "business_name": "Minimal Worker",
            "trust_score": 50,
            "trust_level": "MEDIUM",
            "trust_breakdown": {},
            "source_tier": "google_maps",
            "gmaps_review_count": 10,
            "location": "Bali",
            "specializations": [],
        }

        details = transform_to_full_details(worker)

        assert details.contact.phone is None
        assert details.contact.whatsapp is None
        assert details.contact.email is None
        assert details.contact.website is None


class TestGenerateNegotiationTips:
    """Test negotiation tips generation"""

    def test_verified_contractor_tips(self):
        """Should provide premium contractor guidance for VERIFIED"""
        worker = {
            "trust_score": 87,
            "trust_level": "VERIFIED",
            "gmaps_review_count": 100,
            "gmaps_rating": 4.8,
        }

        tips = generate_negotiation_tips(worker)

        assert "VERIFIED" in tips
        assert "87" in tips
        assert "100" in tips
        assert "premium pricing" in tips.lower()
        assert "warranty" in tips.lower()

    def test_high_trust_contractor_tips(self):
        """Should provide solid contractor guidance for HIGH"""
        worker = {
            "trust_score": 70,
            "trust_level": "HIGH",
            "gmaps_review_count": 50,
            "gmaps_rating": 4.5,
        }

        tips = generate_negotiation_tips(worker)

        assert "HIGH" in tips
        assert "70" in tips
        assert "50" in tips
        assert "fair pricing" in tips.lower()

    def test_low_trust_contractor_warnings(self):
        """Should provide caution warnings for LOW trust"""
        worker = {
            "trust_score": 30,
            "trust_level": "LOW",
            "gmaps_review_count": 5,
            "gmaps_rating": 3.5,
        }

        tips = generate_negotiation_tips(worker)

        assert "LOW" in tips
        assert "30" in tips
        assert "caution" in tips.lower() or "exercise" in tips.lower()
        assert "references" in tips.lower() or "verify" in tips.lower()

    def test_includes_pricing_guidance_when_available(self):
        """Should include OLX pricing if available"""
        worker = {
            "trust_score": 75,
            "trust_level": "HIGH",
            "gmaps_review_count": 30,
            "olx_price_idr": 500000,
        }

        tips = generate_negotiation_tips(worker)

        assert "500,000" in tips or "500000" in tips
        assert "IDR" in tips

    def test_includes_rating_insights(self):
        """Should include rating-based insights"""
        worker_excellent = {
            "trust_score": 80,
            "trust_level": "VERIFIED",
            "gmaps_review_count": 50,
            "gmaps_rating": 4.7,
        }

        tips = generate_negotiation_tips(worker_excellent)

        assert "4.7" in tips
        assert "excellent" in tips.lower() or "quality" in tips.lower()

    def test_includes_general_negotiation_tactics(self):
        """Should always include general negotiation advice"""
        worker = {
            "trust_score": 60,
            "trust_level": "MEDIUM",
            "gmaps_review_count": 20,
        }

        tips = generate_negotiation_tips(worker)

        assert "warranty" in tips.lower()
        assert "timeline" in tips.lower()
        assert "payment" in tips.lower()
        assert "quotes" in tips.lower()


class TestWorkerDetailsIntegration:
    """Integration tests using TestClient"""

    def test_detail_endpoint_requires_user_email(self):
        """Should require user_email query parameter"""
        client = TestClient(app)

        response = client.get("/api/v1/workers/worker-123/details")

        assert response.status_code == 422  # Validation error - missing user_email

    def test_detail_endpoint_with_unlocked_worker(self):
        """Should return full details when worker is unlocked"""
        client = TestClient(app)

        with patch("app.routes.workers_search.get_worker_by_id") as mock_get, \
             patch("app.routes.workers_search.check_worker_unlock") as mock_check:

            mock_get.return_value = {
                "id": "worker-1",
                "business_name": "Test Worker",
                "trust_score": 75,
                "trust_level": "HIGH",
                "trust_breakdown": {},
                "source_tier": "google_maps",
                "gmaps_review_count": 30,
                "phone": "+62361234567",
                "location": "Canggu",
                "specializations": ["pool"],
            }
            mock_check.return_value = True

            response = client.get(
                "/api/v1/workers/worker-1/details?user_email=user@example.com"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["business_name"] == "Test Worker"
            assert "contact" in data
            assert data["contact"]["phone"] == "+62361234567"
            assert "negotiation_script" in data
