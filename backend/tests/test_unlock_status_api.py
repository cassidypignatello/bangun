"""
Tests for the GET /unlock/status endpoint (F8).

Verifies that the endpoint correctly reports whether a worker has been
unlocked by querying the worker_unlocks table, following the same
mocking pattern as test_boq_results_api.py.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import API_PREFIX


def _make_supabase_with_unlocks(records: list) -> MagicMock:
    """Build a Supabase mock that returns the given worker_unlocks rows."""
    mock_response = MagicMock()
    mock_response.data = records

    chain = MagicMock()
    chain.execute.return_value = mock_response
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain

    mock_supabase = MagicMock()
    mock_supabase.table.return_value = chain
    return mock_supabase


class TestUnlockStatusEndpoint:
    """GET /unlock/status?worker_id=... returns correct unlock state."""

    def test_returns_unlocked_true_when_record_exists(self):
        """Should return unlocked=True when a worker_unlocks row is found."""
        client = TestClient(app)
        mock_sb = _make_supabase_with_unlocks([
            {"worker_id": "wrk-123", "unlocked_at": "2026-06-01T10:00:00"}
        ])

        with patch("app.routes.payments.get_supabase_client", return_value=mock_sb):
            response = client.get(f"{API_PREFIX}/unlock/status?worker_id=wrk-123")

        assert response.status_code == 200
        data = response.json()
        assert data["unlocked"] is True
        assert data["unlocked_at"] == "2026-06-01T10:00:00"
        assert data["ok"] is True

    def test_returns_unlocked_false_when_no_record(self):
        """Should return unlocked=False when no worker_unlocks row is found."""
        client = TestClient(app)
        mock_sb = _make_supabase_with_unlocks([])

        with patch("app.routes.payments.get_supabase_client", return_value=mock_sb):
            response = client.get(f"{API_PREFIX}/unlock/status?worker_id=wrk-999")

        assert response.status_code == 200
        data = response.json()
        assert data["unlocked"] is False
        assert data["unlocked_at"] is None
        assert data["ok"] is True

    def test_requires_worker_id_param(self):
        """Should return 422 when worker_id query param is missing."""
        client = TestClient(app)

        response = client.get(f"{API_PREFIX}/unlock/status")

        assert response.status_code == 422

    def test_returns_500_on_supabase_error(self):
        """Should return 500 when Supabase raises an exception."""
        client = TestClient(app)

        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = RuntimeError("DB connection failed")

        with patch("app.routes.payments.get_supabase_client", return_value=mock_supabase):
            response = client.get(f"{API_PREFIX}/unlock/status?worker_id=wrk-123")

        assert response.status_code == 500
        assert "Unlock status lookup failed" in response.json()["detail"]
