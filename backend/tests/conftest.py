"""
Pytest configuration and shared fixtures for testing
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """
    FastAPI test client fixture

    Usage:
        def test_health(client):
            response = client.get("/health")
            assert response.status_code == 200
    """
    return TestClient(app)


@pytest.fixture
def mock_settings():
    """
    Mock settings for testing without environment variables

    Returns:
        Settings: Mock settings instance
    """
    from app.config import Settings

    return Settings(
        env="development",
        debug=True,
        supabase_url="https://test.supabase.co",
        supabase_service_key="test_key",
        openai_api_key="sk-test",
        apify_token="apify_test",
        midtrans_server_key="SB-test",
        midtrans_client_key="SB-test-client",
        field_encryption_key="test_encryption_key",
        sentry_dsn=None,
    )


@pytest.fixture
def sample_project_input():
    """
    Sample project input for testing (simplified - only description required)

    Returns:
        dict: Valid project input data
    """
    return {
        "description": "Modern 3x4m bathroom renovation with ceramic tiles, walk-in shower, and new fixtures in Canggu",
    }


@pytest.fixture
def sample_bom_item():
    """
    Sample BOM item for testing

    Returns:
        dict: Valid BOM item data
    """
    return {
        "material_name": "Ceramic Tiles 40x40cm",
        "quantity": 10.0,
        "unit": "m2",
        "unit_price_idr": 150000,
        "total_price_idr": 1500000,
        "source": "tokopedia",
        "confidence": 0.95,
        "marketplace_url": "https://tokopedia.com/test",
    }


@pytest.fixture
def sample_worker():
    """
    Sample worker data for testing

    Returns:
        dict: Valid worker data
    """
    return {
        "worker_id": "wrk_test123",
        "full_name": "Ahmad Suryanto",
        "specialization": "Mason",
        "location": "Canggu",
        "hourly_rate_idr": 75000,
        "daily_rate_idr": 500000,
        "project_count": 47,
        "avg_rating": 4.8,
        "license_verified": True,
        "insurance_verified": True,
        "background_check": True,
        "years_experience": 12,
        "portfolio_images": [],
        "certifications": ["Licensed Mason"],
        "languages": ["Indonesian", "English"],
    }


@pytest.fixture
def mock_openai_response():
    """
    Mock OpenAI API response for BOM generation

    Returns:
        list[dict]: Mock BOM items
    """
    return [
        {
            "material_name": "Ceramic Tiles 40x40cm",
            "quantity": 10.0,
            "unit": "m2",
            "category": "finishing",
            "notes": "For bathroom flooring",
        },
        {
            "material_name": "Cement 50kg",
            "quantity": 5.0,
            "unit": "pcs",
            "category": "structural",
            "notes": "For tile installation",
        },
    ]


@pytest.fixture
def mock_tokopedia_products():
    """
    Mock Tokopedia scraping results

    Returns:
        list[dict]: Mock product listings
    """
    return [
        {
            "name": "Ceramic Tiles Premium 40x40",
            "price_idr": 150000,
            "url": "https://tokopedia.com/product1",
            "seller": "Test Seller",
            "rating": 4.8,
            "sold_count": 150,
        },
        {
            "name": "Ceramic Tiles Standard 40x40",
            "price_idr": 140000,
            "url": "https://tokopedia.com/product2",
            "seller": "Test Seller 2",
            "rating": 4.5,
            "sold_count": 100,
        },
    ]
