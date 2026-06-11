"""
Tests for health check endpoints
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import API_PREFIX


client = TestClient(app)


class TestHealthCheck:
    """Tests for basic health check endpoint"""

    def test_health_check_returns_200(self):
        """Should return 200 OK"""
        response = client.get(f"{API_PREFIX}/health/")

        assert response.status_code == 200

    def test_health_check_response_body(self):
        """Should return healthy status"""
        response = client.get(f"{API_PREFIX}/health/")

        data = response.json()
        assert data["status"] == "healthy"
        assert data["ok"] is True


class TestReadinessCheck:
    """Tests for readiness check endpoint"""

    def test_readiness_returns_200(self):
        """Should return 200 even when not ready"""
        with patch("app.routes.health.get_supabase_client") as mock_client:
            # Simulate database failure
            mock_client.return_value.table.return_value.select.return_value.limit.return_value.execute.side_effect = Exception("DB Error")

            response = client.get(f"{API_PREFIX}/health/ready")

            assert response.status_code == 200

    def test_readiness_all_checks_pass(self):
        """Should return ready when all checks pass"""
        with patch("app.routes.health.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.return_value.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_response

            response = client.get(f"{API_PREFIX}/health/ready")

            data = response.json()
            assert data["status"] == "ready"
            assert data["ok"] is True
            assert data["checks"]["api"] is True
            assert data["checks"]["config"] is True
            assert data["checks"]["database"] is True

    def test_readiness_database_failure(self):
        """Should return not_ready when database fails"""
        with patch("app.routes.health.get_supabase_client") as mock_client:
            mock_client.return_value.table.return_value.select.return_value.limit.return_value.execute.side_effect = Exception("Connection refused")

            response = client.get(f"{API_PREFIX}/health/ready")

            data = response.json()
            assert data["status"] == "not_ready"
            assert data["ok"] is False
            assert data["checks"]["database"] is False
            assert data["checks"]["api"] is True


class TestMetricsEndpoint:
    """Tests for metrics endpoint"""

    def test_metrics_returns_200(self):
        """Should return 200 OK"""
        response = client.get(f"{API_PREFIX}/health/metrics")

        assert response.status_code == 200

    def test_metrics_includes_environment(self):
        """Should include environment info"""
        response = client.get(f"{API_PREFIX}/health/metrics")

        data = response.json()
        assert "environment" in data
        assert "version" in data
        assert data["ok"] is True
