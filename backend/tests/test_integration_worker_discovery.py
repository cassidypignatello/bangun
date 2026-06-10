"""
Integration tests for complete worker discovery flow.

Tests cover the full user journey:
1. Search workers by project type and location
2. View worker preview (masked contact info)
3. Initiate payment to unlock worker details
4. Receive payment confirmation (webhook simulation)
5. Access full worker details after unlock

Note: Payment tests use Midtrans sandbox environment.
Set ENV=development to use sandbox credentials.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.payment import PaymentMethod


class TestWorkerDiscoveryFlow:
    """Test complete worker discovery user journey"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)
        self.test_email = f"test-{uuid.uuid4().hex[:8]}@example.com"

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_cached_workers")
    async def test_search_workers_returns_masked_data(
        self, mock_get_cached
    ):
        """
        Step 1: User searches for workers
        Should return masked contact information in preview
        """
        # Mock cached workers (cache hit)
        mock_get_cached.return_value = [
            {
                "id": "worker-1",
                "business_name": "Bali Pool Builders",
                "specializations": ["pool", "general"],
                "gmaps_rating": 4.8,
                "gmaps_review_count": 125,
                "trust_score": 85,
                "trust_level": "HIGH",
                "trust_breakdown": {"source": 24, "reviews": 20},
                "phone": "+62812345678",
                "email": "contact@balipoolbuilders.com",
                "gmaps_address": "Jl. Sunset Road, Seminyak",
                "gmaps_place_id": "ChIJ123456",
                "last_scraped_at": datetime.now(timezone.utc).isoformat(),
                "location": "Bali",
                "source_tier": "google_maps",
                "gmaps_photos_count": 10,
            }
        ]

        # Search for pool workers
        response = self.client.post(
            "/api/v1/workers/search",
            json={
                "project_type": "pool",
                "location": "Bali",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify cache hit response
        assert data["status"] == "cache_hit"
        assert len(data["workers"]) == 1
        worker = data["workers"][0]

        # Verify WorkerPreview structure (name is masked with block chars)
        assert worker["preview_name"].startswith("B")  # "Bali Pool Builders" masked
        assert worker["trust_score"]["total_score"] == 85
        assert worker["trust_score"]["trust_level"] == "HIGH"
        assert worker["contact_locked"] is True
        assert worker["unlock_price_idr"] == 50000
        assert worker["photos_count"] == 10

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.check_worker_unlock")
    @patch("app.routes.workers_search.get_worker_by_id")
    async def test_get_worker_detail_locked_returns_payment_required(
        self, mock_get_worker, mock_check_unlock
    ):
        """
        Step 2: User tries to view worker detail (not unlocked)
        Should return 402 Payment Required
        """
        worker_id = "worker-1"

        # Mock worker exists
        mock_get_worker.return_value = {
            "id": worker_id,
            "business_name": "Bali Pool Builders",
            "phone": "+62812345678",
            "email": "contact@balipoolbuilders.com",
            "gmaps_rating": 4.8,
            "trust_score": 85,
        }

        # Mock unlock check - NOT unlocked
        mock_check_unlock.return_value = False

        # Get worker detail
        response = self.client.get(
            f"/api/v1/workers/{worker_id}/details",
            params={"user_email": self.test_email},
        )

        # Should return 402 Payment Required
        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        data = response.json()
        assert "Worker contact details are locked" in data["detail"]["message"]
        assert data["detail"]["unlock_price_idr"] == 50000

    @pytest.mark.asyncio
    @patch("app.integrations.midtrans.get_snap_client")
    @patch("app.integrations.supabase.get_supabase_client")
    async def test_initiate_unlock_payment(
        self, mock_get_supabase, mock_get_snap_client
    ):
        """
        Step 3: User initiates payment to unlock worker
        Should create Midtrans transaction and return payment URL
        """
        worker_id = "worker-1"

        # Mock Midtrans Snap client
        mock_snap = MagicMock()
        mock_get_snap_client.return_value = mock_snap
        mock_snap.create_transaction.return_value = {
            "token": "test-snap-token",
            "redirect_url": "https://app.sandbox.midtrans.com/snap/v2/vtweb/test-snap-token",
        }

        # Mock Supabase save payment (execute must return an object with .data)
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        mock_execute_result = MagicMock()
        mock_execute_result.data = []
        mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_execute_result

        # Initiate unlock payment
        response = self.client.post(
            "/api/v1/unlock",
            json={
                "worker_id": worker_id,
                "payment_method": PaymentMethod.CREDIT_CARD.value,
                "return_url": "https://example.com/payment/success",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify payment response
        assert "transaction_id" in data
        assert "payment_url" in data
        assert data["amount_idr"] == 50000
        assert "app.sandbox.midtrans.com" in data["payment_url"]

        # Verify Midtrans transaction was created with sandbox URL
        mock_snap.create_transaction.assert_called_once()
        transaction_data = mock_snap.create_transaction.call_args[0][0]
        assert transaction_data["transaction_details"]["gross_amount"] == 50000
        assert "credit_card" in transaction_data["enabled_payments"]

    @pytest.mark.asyncio
    @patch("app.routes.payments.update_payment_status")
    async def test_payment_webhook_completes_unlock(self, mock_update_payment):
        """
        Step 4: Midtrans sends webhook after successful payment
        Should update payment status
        """
        order_id = "UNLOCK-worker-1-abc123"

        # update_payment_status is mocked directly at the route level
        mock_update_payment.return_value = None

        # Calculate valid signature
        import hashlib

        status_code = "200"
        gross_amount = "50000.00"
        server_key = "test-server-key"
        raw_string = f"{order_id}{status_code}{gross_amount}{server_key}"
        signature = hashlib.sha512(raw_string.encode()).hexdigest()

        # Send webhook
        with patch("app.routes.payments.get_settings") as mock_settings:
            mock_settings.return_value.midtrans_server_key = server_key

            response = self.client.post(
                "/api/v1/webhooks/midtrans",
                json={
                    "transaction_time": "2025-12-03 12:00:00",
                    "transaction_status": "settlement",
                    "transaction_id": "midtrans-txn-123",
                    "status_code": status_code,
                    "signature_key": signature,
                    "payment_type": "credit_card",
                    "order_id": order_id,
                    "merchant_id": "test-merchant",
                    "gross_amount": gross_amount,
                    "fraud_status": "accept",
                    "currency": "IDR",
                },
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["internal_status"] == "completed"

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.check_worker_unlock")
    @patch("app.routes.workers_search.get_worker_by_id")
    async def test_get_worker_detail_unlocked_returns_full_data(
        self, mock_get_worker, mock_check_unlock
    ):
        """
        Step 5: User accesses worker detail after unlock
        Should return full unmasked contact information
        """
        worker_id = "worker-1"

        # Mock worker data
        mock_get_worker.return_value = {
            "id": worker_id,
            "business_name": "Bali Pool Builders",
            "phone": "+62812345678",
            "whatsapp": "+62812345678",
            "email": "contact@balipoolbuilders.com",
            "website": "https://balipoolbuilders.com",
            "address": "Jl. Sunset Road, Seminyak",
            "location": "Seminyak",
            "latitude": -8.6917,
            "longitude": 115.1671,
            "gmaps_url": "https://maps.google.com/?cid=123456",
            "gmaps_rating": 4.8,
            "gmaps_review_count": 125,
            "gmaps_photos_count": 25,
            "trust_score": 85,
            "trust_level": "HIGH",
            "trust_breakdown": {"source": 24, "reviews": 20},
            "source_tier": "google_maps",
            "specializations": ["pool", "general"],
            "opening_hours": "Mon-Fri: 8am-5pm",
            "gmaps_categories": ["Contractor", "Pool Builder"],
        }

        # Mock unlock check - UNLOCKED
        mock_check_unlock.return_value = True

        # Get worker detail
        response = self.client.get(
            f"/api/v1/workers/{worker_id}/details",
            params={"user_email": self.test_email},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Full contact info should be exposed (WorkerFullDetails schema)
        assert data["business_name"] == "Bali Pool Builders"
        assert data["contact"]["phone"] == "+62812345678"
        assert data["contact"]["email"] == "contact@balipoolbuilders.com"
        assert data["contact"]["website"] == "https://balipoolbuilders.com"
        assert data["location"]["address"] == "Jl. Sunset Road, Seminyak"
        assert data["trust_score"]["total_score"] == 85
        assert "negotiation_script" in data


class TestSearchCaching:
    """Test worker search caching behavior"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_cached_workers")
    async def test_search_cache_hit(self, mock_get_cached):
        """
        Cache hit: Search finds recently scraped workers in database
        Should not trigger Apify scraping
        """
        # Mock cached workers (scraped within last 7 days)
        mock_get_cached.return_value = [
            {
                "id": "worker-1",
                "business_name": "Cached Pool Builder",
                "specializations": ["pool"],
                "gmaps_rating": 4.7,
                "gmaps_review_count": 50,
                "trust_score": 80,
                "trust_level": "HIGH",
                "trust_breakdown": {},
                "source_tier": "google_maps",
                "location": "Bali",
                "last_scraped_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

        # Search should use cached data
        response = self.client.post(
            "/api/v1/workers/search",
            json={
                "project_type": "pool",
                "location": "Bali",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify cache hit
        assert data["status"] == "cache_hit"
        assert len(data["workers"]) == 1
        assert data["workers"][0]["preview_name"].startswith("C")  # "Cached Pool Builder" masked

        # Verify cache was checked
        mock_get_cached.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.routes.workers_search.get_cached_workers")
    async def test_search_cache_miss_returns_scraping_status(
        self, mock_get_cached
    ):
        """
        Cache miss: No recent workers in database
        Should return scraping status with empty results
        """
        # Mock cache miss (empty results)
        mock_get_cached.return_value = []

        # Search triggers background scraping
        response = self.client.post(
            "/api/v1/workers/search",
            json={
                "project_type": "pool",
                "location": "Bali",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify scraping response
        assert data["status"] == "scraping"
        assert data["workers"] == []
        assert data["total_count"] == 0
        assert data["estimated_scrape_time_seconds"] == 30

        # Verify cache was checked
        mock_get_cached.assert_called_once()


class TestPaymentEdgeCases:
    """Test payment flow edge cases and error handling"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    @pytest.mark.asyncio
    @patch("app.integrations.midtrans.get_snap_client")
    async def test_unlock_midtrans_error(self, mock_get_snap_client):
        """Should handle Midtrans API errors gracefully"""
        # Mock Midtrans error
        mock_snap = MagicMock()
        mock_get_snap_client.return_value = mock_snap
        mock_snap.create_transaction.side_effect = Exception("Midtrans API error")

        response = self.client.post(
            "/api/v1/unlock",
            json={
                "worker_id": "worker-1",
                "payment_method": PaymentMethod.CREDIT_CARD.value,
                "return_url": "https://example.com/return",
            },
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "Payment creation failed" in data["detail"]

    @pytest.mark.asyncio
    async def test_webhook_invalid_signature(self):
        """Should reject webhook with invalid signature"""
        order_id = "UNLOCK-worker-1-abc123"

        # Send webhook with invalid signature
        with patch("app.routes.payments.get_settings") as mock_settings:
            mock_settings.return_value.midtrans_server_key = "test-server-key"

            response = self.client.post(
                "/api/v1/webhooks/midtrans",
                json={
                    "transaction_time": "2025-12-03 12:00:00",
                    "transaction_status": "settlement",
                    "transaction_id": "midtrans-txn-123",
                    "status_code": "200",
                    "signature_key": "invalid-signature-12345",
                    "payment_type": "credit_card",
                    "order_id": order_id,
                    "merchant_id": "test-merchant",
                    "gross_amount": "50000.00",
                    "fraud_status": "accept",
                    "currency": "IDR",
                },
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert data["detail"] == "Invalid signature"

    @pytest.mark.asyncio
    @patch("app.routes.payments.update_payment_status")
    async def test_webhook_fraud_status_handling(self, mock_update_payment):
        """Should process webhooks with fraud status"""
        order_id = "UNLOCK-worker-1-abc123"

        # update_payment_status is mocked at the route level
        mock_update_payment.return_value = None

        # Calculate valid signature
        import hashlib

        status_code = "200"
        gross_amount = "50000.00"
        server_key = "test-server-key"
        raw_string = f"{order_id}{status_code}{gross_amount}{server_key}"
        signature = hashlib.sha512(raw_string.encode()).hexdigest()

        # Send webhook with fraud status
        with patch("app.routes.payments.get_settings") as mock_settings:
            mock_settings.return_value.midtrans_server_key = server_key

            response = self.client.post(
                "/api/v1/webhooks/midtrans",
                json={
                    "transaction_time": "2025-12-03 12:00:00",
                    "transaction_status": "settlement",
                    "transaction_id": "midtrans-txn-123",
                    "status_code": status_code,
                    "signature_key": signature,
                    "payment_type": "credit_card",
                    "order_id": order_id,
                    "merchant_id": "test-merchant",
                    "gross_amount": gross_amount,
                    "fraud_status": "challenge",  # Suspicious transaction
                    "currency": "IDR",
                },
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["internal_status"] == "completed"

        # Verify fraud_status was passed to update_payment_status
        mock_update_payment.assert_called_once()
        call_kwargs = mock_update_payment.call_args[1]
        assert call_kwargs.get("fraud_status") == "challenge"
