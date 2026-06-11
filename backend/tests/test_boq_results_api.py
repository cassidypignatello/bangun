"""
Tests for BoQ results API endpoint null-summary behaviour.

Verifies that when a job has no priced items (market_estimate / potential_savings
are NULL in the database), the results endpoint serialises them as JSON null
rather than coalescing to zero — which would be indistinguishable from genuine
zero savings.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.boq import BoQSummary
from tests.conftest import API_PREFIX


# ---------------------------------------------------------------------------
# Schema-level tests (no I/O required)
# ---------------------------------------------------------------------------


class TestBoQSummarySchema:
    """BoQSummary correctly accepts and serialises None for pricing fields."""

    def test_null_pricing_fields_serialise_as_none(self):
        """Unpriced job: market_estimate / potential_savings / savings_percent are None."""
        summary = BoQSummary(
            contractor_total=Decimal("5000000"),
            market_estimate=None,
            potential_savings=None,
            savings_percent=None,
            total_items=10,
            materials_count=8,
            labor_count=2,
            owner_supply_count=0,
            priced_count=0,
        )

        data = summary.model_dump()
        assert data["market_estimate"] is None
        assert data["potential_savings"] is None
        assert data["savings_percent"] is None
        # contractor_total must still be present
        assert data["contractor_total"] == Decimal("5000000")

    def test_null_fields_serialise_as_null_in_json(self):
        """Null pricing fields must appear as JSON null, not 0."""
        summary = BoQSummary(
            contractor_total=Decimal("5000000"),
            market_estimate=None,
            potential_savings=None,
            savings_percent=None,
            total_items=10,
            materials_count=8,
            labor_count=2,
            owner_supply_count=0,
            priced_count=0,
        )

        json_str = summary.model_dump_json()
        import json

        parsed = json.loads(json_str)
        assert parsed["market_estimate"] is None
        assert parsed["potential_savings"] is None
        assert parsed["savings_percent"] is None

    def test_priced_job_retains_values(self):
        """A fully-priced job should not be affected by the Optional change."""
        summary = BoQSummary(
            contractor_total=Decimal("10000000"),
            market_estimate=Decimal("8000000"),
            potential_savings=Decimal("2000000"),
            savings_percent=20.0,
            total_items=5,
            materials_count=5,
            labor_count=0,
            owner_supply_count=0,
            priced_count=5,
        )

        data = summary.model_dump()
        assert data["market_estimate"] == Decimal("8000000")
        assert data["potential_savings"] == Decimal("2000000")
        assert data["savings_percent"] == 20.0


# ---------------------------------------------------------------------------
# Route-level integration tests (mocking Supabase)
# ---------------------------------------------------------------------------

_COMPLETED_JOB_UNPRICED = {
    "id": "job-unpriced-001",
    "session_id": "sess-001",
    "filename": "test_boq.pdf",
    "file_format": "pdf",
    "status": "completed",
    "progress_percent": 100,
    "message": None,
    "error_message": None,
    "total_items_extracted": 5,
    "materials_count": 5,
    "labor_count": 0,
    "owner_supply_count": 0,
    "contractor_total": "5000000",
    # These are NULL in the DB — not priced
    "market_estimate": None,
    "potential_savings": None,
    "project_name": None,
    "contractor_name": None,
    "project_location": None,
    "extraction_warnings": [],
    "created_at": "2026-06-01T10:00:00",
    "completed_at": "2026-06-01T10:05:00",
}


class TestBoQResultsEndpointNullSummary:
    """Route returns null pricing fields for unpriced jobs."""

    def _make_supabase_mock(self, job_data, items_data=None):
        """Build a mock Supabase client that returns the given job/items."""
        from unittest.mock import MagicMock

        items_data = items_data or []

        mock_supabase = MagicMock()

        # We need to handle two sequential .table() calls:
        # first for boq_jobs, second for boq_items
        job_exec = MagicMock()
        job_exec.data = [job_data]

        items_exec = MagicMock()
        items_exec.data = items_data

        job_chain = MagicMock()
        job_chain.execute.return_value = job_exec
        job_chain.select.return_value = job_chain
        job_chain.eq.return_value = job_chain

        items_chain = MagicMock()
        items_chain.execute.return_value = items_exec
        items_chain.select.return_value = items_chain
        items_chain.eq.return_value = items_chain

        call_count = {"n": 0}

        def table_side_effect(name):
            call_count["n"] += 1
            if name == "boq_jobs":
                return job_chain
            return items_chain

        mock_supabase.table.side_effect = table_side_effect
        return mock_supabase

    def test_unpriced_job_returns_null_pricing_fields(self):
        """GET /boq/{id}/results on an unpriced job should have null market/savings."""
        client = TestClient(app)
        mock_sb = self._make_supabase_mock(_COMPLETED_JOB_UNPRICED)

        with patch("app.routes.boq.get_supabase_client", return_value=mock_sb):
            response = client.get(f"{API_PREFIX}/boq/job-unpriced-001/results")

        assert response.status_code == 200
        data = response.json()
        summary = data["summary"]

        assert summary["market_estimate"] is None, (
            "market_estimate should be null for unpriced jobs, got "
            + repr(summary["market_estimate"])
        )
        assert summary["potential_savings"] is None, (
            "potential_savings should be null for unpriced jobs"
        )
        assert summary["savings_percent"] is None, (
            "savings_percent should be null for unpriced jobs"
        )
        # contractor_total must still be present
        assert summary["contractor_total"] is not None

    def test_unpriced_job_does_not_return_zeros(self):
        """Null DB values must NOT be coalesced to 0 in the API response."""
        client = TestClient(app)
        mock_sb = self._make_supabase_mock(_COMPLETED_JOB_UNPRICED)

        with patch("app.routes.boq.get_supabase_client", return_value=mock_sb):
            response = client.get(f"{API_PREFIX}/boq/job-unpriced-001/results")

        assert response.status_code == 200
        data = response.json()
        summary = data["summary"]

        assert summary["market_estimate"] != 0, "market_estimate must not be coalesced to 0"
        assert summary["potential_savings"] != 0, "potential_savings must not be coalesced to 0"
        assert summary["savings_percent"] != 0, "savings_percent must not be coalesced to 0"
