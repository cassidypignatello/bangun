"""
Tests for the GET /unlock/status endpoint (F8 + authorization fix).

Verifies that the endpoint reports unlock state scoped to a specific user:
unlock records are filtered by BOTH worker_id and user_email, so one user's
payment never unlocks the worker for anyone else. Follows the mocking
pattern of test_boq_results_api.py, with a filter-aware fake query so the
per-user scoping is actually exercised (a plain MagicMock chain would
return the same rows regardless of filters).
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import API_PREFIX


class _FakeUnlocksQuery:
    """Supabase query fake that honours .eq() filters against seeded rows."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}

    def select(self, *args, **kwargs):
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, n):
        return self

    def execute(self):
        response = MagicMock()
        response.data = [
            row
            for row in self._rows
            if all(row.get(col) == val for col, val in self._filters.items())
        ]
        return response


def _make_supabase_with_unlocks(rows: list) -> MagicMock:
    """Build a Supabase mock whose worker_unlocks queries filter like the DB."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = lambda name: _FakeUnlocksQuery(rows)
    return mock_supabase


_ALICE_UNLOCK = {
    "worker_id": "wrk-123",
    "user_email": "alice@example.com",
    "unlocked_at": "2026-06-01T10:00:00",
}


class TestUnlockStatusEndpoint:
    """GET /unlock/status?worker_id=...&user_email=... returns per-user state."""

    def test_returns_unlocked_true_for_the_paying_user(self):
        """The user who unlocked the worker sees unlocked=True."""
        client = TestClient(app)
        mock_sb = _make_supabase_with_unlocks([_ALICE_UNLOCK])

        with patch("app.routes.payments.get_supabase_client", return_value=mock_sb):
            response = client.get(
                f"{API_PREFIX}/unlock/status",
                params={"worker_id": "wrk-123", "user_email": "alice@example.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["unlocked"] is True
        assert data["unlocked_at"] == "2026-06-01T10:00:00"
        assert data["ok"] is True

    def test_other_user_does_not_see_anothers_unlock(self):
        """User B gets unlocked=False for a worker user A paid to unlock."""
        client = TestClient(app)
        mock_sb = _make_supabase_with_unlocks([_ALICE_UNLOCK])

        with patch("app.routes.payments.get_supabase_client", return_value=mock_sb):
            response = client.get(
                f"{API_PREFIX}/unlock/status",
                params={"worker_id": "wrk-123", "user_email": "bob@example.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["unlocked"] is False
        assert data["unlocked_at"] is None

    def test_returns_unlocked_false_when_no_record(self):
        """Should return unlocked=False when no worker_unlocks row matches."""
        client = TestClient(app)
        mock_sb = _make_supabase_with_unlocks([])

        with patch("app.routes.payments.get_supabase_client", return_value=mock_sb):
            response = client.get(
                f"{API_PREFIX}/unlock/status",
                params={"worker_id": "wrk-999", "user_email": "alice@example.com"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["unlocked"] is False
        assert data["unlocked_at"] is None
        assert data["ok"] is True

    def test_requires_worker_id_param(self):
        """Should return 422 when worker_id query param is missing."""
        client = TestClient(app)

        response = client.get(
            f"{API_PREFIX}/unlock/status",
            params={"user_email": "alice@example.com"},
        )

        assert response.status_code == 422

    def test_requires_user_email_param(self):
        """Should return 422 when user_email query param is missing."""
        client = TestClient(app)

        response = client.get(
            f"{API_PREFIX}/unlock/status",
            params={"worker_id": "wrk-123"},
        )

        assert response.status_code == 422

    def test_returns_500_with_generic_detail_on_supabase_error(self):
        """Should return 500 without leaking the exception message."""
        client = TestClient(app)

        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = RuntimeError(
            "DB connection failed: secret-host:5432"
        )

        with patch("app.routes.payments.get_supabase_client", return_value=mock_supabase):
            response = client.get(
                f"{API_PREFIX}/unlock/status",
                params={"worker_id": "wrk-123", "user_email": "alice@example.com"},
            )

        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail == "Unlock status lookup failed"
        # The underlying exception text must NOT be exposed to the client
        assert "secret-host" not in detail
