"""
Tests for Supabase integration layer
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestGetSupabaseClient:
    """Tests for get_supabase_client function"""

    def test_returns_client(self):
        """Should return a configured Supabase client"""
        with patch("app.integrations.supabase.create_client") as mock_create:
            with patch("app.integrations.supabase.get_settings") as mock_settings:
                mock_settings.return_value.supabase_url = "https://test.supabase.co"
                mock_settings.return_value.supabase_service_key = "test_key"
                mock_create.return_value = MagicMock()

                # Clear the lru_cache to ensure fresh call
                from app.integrations.supabase import get_supabase_client
                get_supabase_client.cache_clear()

                client = get_supabase_client()

                mock_create.assert_called_once_with(
                    "https://test.supabase.co", "test_key"
                )
                assert client is not None


class TestProjectOperations:
    """Tests for project CRUD operations"""

    @pytest.mark.asyncio
    async def test_save_project(self):
        """Should insert project and return with ID"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [{"id": "uuid-123", "project_type": "pool"}]
            mock_client.return_value.table.return_value.insert.return_value.execute.return_value = mock_response

            from app.integrations.supabase import save_project

            result = await save_project({"project_type": "pool"})

            assert result["id"] == "uuid-123"
            mock_client.return_value.table.assert_called_with("projects")

    @pytest.mark.asyncio
    async def test_get_project(self):
        """Should retrieve project by ID"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [{"id": "uuid-123", "project_type": "pool"}]
            mock_client.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_project

            result = await get_project("uuid-123")

            assert result["id"] == "uuid-123"

    @pytest.mark.asyncio
    async def test_get_project_not_found(self):
        """Should return None for non-existent project"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_project

            result = await get_project("non-existent")

            assert result is None

    @pytest.mark.asyncio
    async def test_update_project_status(self):
        """Should update project status"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            from app.integrations.supabase import update_project_status

            await update_project_status("uuid-123", "estimated", bom={"items": []})

            mock_client.return_value.table.return_value.update.assert_called_once()
            call_args = mock_client.return_value.table.return_value.update.call_args[0][0]
            assert call_args["status"] == "estimated"
            assert "bom" in call_args


class TestMaterialOperations:
    """Tests for material CRUD operations"""

    @pytest.mark.asyncio
    async def test_get_material_by_code(self):
        """Should retrieve material by code"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [{"id": "mat-123", "material_code": "MAT001"}]
            mock_client.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_material_by_code

            result = await get_material_by_code("MAT001")

            assert result["material_code"] == "MAT001"

    @pytest.mark.asyncio
    async def test_search_materials(self):
        """Should search materials by name"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [
                {"name_id": "Semen Portland", "name_en": "Portland Cement"},
                {"name_id": "Semen Putih", "name_en": "White Cement"},
            ]
            mock_client.return_value.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_response

            from app.integrations.supabase import search_materials

            result = await search_materials("semen")

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_search_materials_empty(self):
        """Should return empty list for no matches"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = []
            mock_client.return_value.table.return_value.select.return_value.or_.return_value.limit.return_value.execute.return_value = mock_response

            from app.integrations.supabase import search_materials

            result = await search_materials("nonexistent")

            assert result == []


class TestWorkerOperations:
    """Tests for worker CRUD operations"""

    @pytest.mark.asyncio
    async def test_get_worker_by_id(self):
        """Should retrieve worker by ID"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [{"id": "wrk-123", "name": "Ahmad"}]
            mock_client.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_worker_by_id

            result = await get_worker_by_id("wrk-123")

            assert result["name"] == "Ahmad"

    @pytest.mark.asyncio
    async def test_save_worker(self):
        """Should insert new worker"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [{"id": "wrk-new", "name": "Budi", "source": "manual"}]
            mock_client.return_value.table.return_value.insert.return_value.execute.return_value = mock_response

            from app.integrations.supabase import save_worker

            result = await save_worker({"name": "Budi", "source": "manual"})

            assert result["id"] == "wrk-new"


class TestPaymentOperations:
    """Tests for payment CRUD operations"""

    @pytest.mark.asyncio
    async def test_save_payment(self):
        """Should insert payment record"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [{"id": "pay-123", "amount": 50000}]
            mock_client.return_value.table.return_value.insert.return_value.execute.return_value = mock_response

            from app.integrations.supabase import save_payment

            result = await save_payment({"amount": 50000, "project_id": "proj-123"})

            assert result["id"] == "pay-123"
            mock_client.return_value.table.assert_called_with("payments")

    @pytest.mark.asyncio
    async def test_get_payment_by_gateway_id(self):
        """Should retrieve payment by Midtrans transaction ID"""
        with patch("app.integrations.supabase.get_supabase_client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [{"id": "pay-123", "gateway_transaction_id": "MT-123"}]
            mock_client.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

            from app.integrations.supabase import get_payment_by_gateway_id

            result = await get_payment_by_gateway_id("MT-123")

            assert result["gateway_transaction_id"] == "MT-123"


